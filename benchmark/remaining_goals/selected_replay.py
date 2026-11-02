"""Formal-adapter replay of exactly one selected original candidate, 2 x 150.

Preflight reads only the chosen source's dependencies. The report retains the
original full manifest raw-byte hash; no reduced manifest or all-mask pass exists.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path

import numpy as np
from .nine_catalog import NEW_TASKS

SELECTED_TASKS = ("frypan_stove9", "cabinet_close_top_bowl")


def _backend():
    from . import replay_candidates
    return replay_candidates


def _candidate(task, index, manifest_path, *, protocol=None):
    from .headless.scoped_sources import inspect_candidate
    return inspect_candidate(task, index, manifest_path, protocol=protocol)


def replay(manifest_path, output, *, task, index, protocol="selected-mask10"):
    """Replay one source in a fresh formal adapter with fixed physical rules."""
    nine = protocol == "nine-mask10"
    if (protocol not in ("selected-mask10", "nine-mask10") or task not in (NEW_TASKS if nine else SELECTED_TASKS)
            or type(index) is not int or index not in range(10)):
        raise ValueError("selected replay requires a fixed task and source index 0..9")
    manifest_path, output = Path(manifest_path).resolve(), Path(output)
    candidate = _candidate(task, index, manifest_path, protocol=protocol) if nine else _candidate(task, index, manifest_path)
    episode, manifest = candidate["episode"], candidate["manifest"]
    original_raw = manifest_path.read_bytes()
    if hashlib.sha256(original_raw).hexdigest() != candidate["source_manifest_sha256"]:
        raise ValueError("original manifest changed after selected preflight")
    b = _backend()
    state_path = b.verify_state_file(episode, manifest_path.parent)
    state_raw = state_path.read_bytes()
    if hashlib.sha256(state_raw).hexdigest() != episode["state_sha256"]:
        raise ValueError("selected saved state changed after preflight")
    state = np.load(io.BytesIO(state_raw), allow_pickle=False)
    observation_hash = episode["initial_observation"]["observation_sha256"]
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "candidate_formal_adapter_replay", "protocol": protocol,
              "selected_replay_version": "single_source_formal_adapter_v1",
              "adapter_lifetime": "one fresh formal adapter for this source and both repeats",
              "policy_called": False, "release_authorized": False,
              "source_manifest_sha256": candidate["source_manifest_sha256"],
              "source_content_hash": candidate["source_content_hash"],
              "steps": 150, "repeats": 2, "hold_action": b.HOLD.tolist(),
              "observation_audit_limits": dict(b.RGB_QUANTIZATION_AUDIT),
              "observation_audit_limitation": b.RGB_QUANTIZATION_LIMITATION,
              "observation_audit_rule": dict(b.RGB_QUANTIZATION_RULE),
              "technical_acceptance": False, "episodes": [], "error": None}
    adapter = None
    try:
        adapter = b.LiberoGoalEnv({"manifest_dir": str(manifest_path.parent), "environment": manifest["environment"],
                                  "control_freq": 20, "image_size": 256})
        for repetition in range(2):
            relative = Path("group_000") / f"repeat_{repetition:02d}" / "mask_00"
            wrapper = b.ReplayAuditEnv(adapter, state, observation_hash, frames_dir=output / relative,
                                        manifest_dir=manifest_path.parent)
            audit = b.validate_candidate(wrapper, episode, steps=150, hold_action=b.HOLD,
                                          velocity_tolerance=.01, robot_position_tolerance=.002,
                                          **b.RGB_QUANTIZATION_AUDIT)
            audit.update(formal_reset_checks=wrapper.reset_checks,
                         reset_observation_comparison=wrapper.reset_observation_comparison,
                         reset_initial_observation=wrapper.reset_initial_observation,
                         post_restore_model_xml_sha256=wrapper.post_restore_xml_sha256,
                         expected_reset_model_xml_sha256=episode["model_xml_sha256"])
            b._write(output / relative / "audit.json", audit)
            report["episodes"].append({"episode_id": episode["episode_id"], "group": 0, "repetition": repetition,
                                       "initial_mask": episode["initial_mask"], "source_legal": episode["construction"]["legal"],
                                       "technical_acceptance": audit["technical_acceptance"], "reset_checks": wrapper.reset_checks,
                                       "checks": audit["checks"], "error": audit.get("error"),
                                       "audit_path": (relative / "audit.json").as_posix()})
            b._write(output / "replay_report.json", report)
        report["technical_acceptance"] = all(row["technical_acceptance"] for row in report["episodes"])
        if manifest_path.read_bytes() != original_raw:
            raise ValueError("original manifest changed during selected replay")
    except Exception as error:
        report["technical_acceptance"] = False
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception as error:
                report["close_error"] = f"{type(error).__name__}: {error}"
        b._write(output / "replay_report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--task", required=True, choices=(*SELECTED_TASKS, *NEW_TASKS))
    parser.add_argument("--protocol", choices=("selected-mask10", "nine-mask10"), default="selected-mask10")
    parser.add_argument("--index", required=True, type=int)
    args = parser.parse_args(argv)
    if not replay(args.manifest, args.out, task=args.task, index=args.index, protocol=args.protocol)["technical_acceptance"]:
        raise SystemExit("source replay failed; inspect replay_report.json")


if __name__ == "__main__":
    main()
