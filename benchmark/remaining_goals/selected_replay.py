"""Formal-adapter replay of exactly one selected original candidate, 2 x 150.

Preflight reads only the chosen source's dependencies. The report retains the
original full manifest raw-byte hash; no reduced manifest or all-mask pass exists.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import io
from pathlib import Path

import numpy as np
from .nine_catalog import NEW_TASKS
from .validation import observation_profile_config, V6_PROFILE

SELECTED_TASKS = ("frypan_stove9", "cabinet_close_top_bowl")


def _backend():
    from . import replay_candidates
    return replay_candidates


def _candidate(task, index, manifest_path, *, protocol=None, rgb_certificate=None, stability_profile=None):
    from .headless.scoped_sources import inspect_candidate
    options = {"rgb_certificate": rgb_certificate} if rgb_certificate is not None else {}
    if stability_profile is not None:
        options["stability_profile"] = stability_profile
    return inspect_candidate(task, index, manifest_path, protocol=protocol, **options)


def replay(manifest_path, output, *, task, index, protocol="selected-mask10", observation_profile=None,
           rgb_certificate=None, stability_profile=None):
    """Replay one source in a fresh formal adapter with fixed physical rules."""
    nine = protocol == "nine-mask10"
    observation_config = observation_profile_config(observation_profile)
    if observation_profile == V6_PROFILE and not nine:
        raise ValueError("v6 source replay is limited to the nine-mask10 protocol")
    if (protocol not in ("selected-mask10", "nine-mask10") or task not in (NEW_TASKS if nine else SELECTED_TASKS)
            or type(index) is not int or index not in range(10)):
        raise ValueError("selected replay requires a fixed task and source index 0..9")
    if stability_profile is not None:
        from .stability import PROFILE
        if (stability_profile != PROFILE or not nine or task != "mug_microwave_close"
                or observation_profile != V6_PROFILE):
            raise ValueError("R7 stability replay requires nine-mask10/mug_microwave_close and explicit v6")
    manifest_path, output = Path(manifest_path).resolve(), Path(output)
    options = {"protocol": protocol} if nine else {}
    if stability_profile is not None:
        options["stability_profile"] = stability_profile
    if rgb_certificate is not None:
        if not nine:
            raise ValueError("RGB evidence certificate is limited to the nine-mask10 source protocol")
        options["rgb_certificate"] = rgb_certificate
    candidate = _candidate(task, index, manifest_path, **options)
    episode, manifest = candidate["episode"], candidate["manifest"]
    if (episode.get("stability_profile") != stability_profile
            or manifest.get("stability_profile") != stability_profile):
        raise ValueError("source stability profile must match the explicit replay profile")
    if stability_profile is not None:
        from .stability import validate_scope
        binding = validate_scope(episode)
        if manifest.get("stability_binding") != binding:
            raise ValueError("source manifest stability binding differs from its episode")
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
              "observation_audit_limits": observation_config["limits"],
              "observation_audit_limitation": observation_config["limitation"],
              "observation_audit_rule": observation_config["rule"],
              "technical_acceptance": False, "episodes": [], "error": None}
    profile_options = {"observation_profile": observation_profile} if observation_profile is not None else {}
    if observation_profile is not None:
        report["observation_profile"] = observation_profile
    if stability_profile is not None:
        profile_options["stability_profile"] = stability_profile
        report.update(stability_profile=stability_profile, stability_binding=deepcopy(binding))
    if rgb_certificate is not None:
        certificate_path = Path(rgb_certificate).resolve()
        report.update(rgb_certificate=str(certificate_path),
                      rgb_certificate_sha256=hashlib.sha256(certificate_path.read_bytes()).hexdigest())
    adapter = None
    try:
        adapter = b.LiberoGoalEnv({"manifest_dir": str(manifest_path.parent), "environment": manifest["environment"],
                                  "control_freq": 20, "image_size": 256})
        for repetition in range(2):
            relative = Path("group_000") / f"repeat_{repetition:02d}" / "mask_00"
            wrapper = b.ReplayAuditEnv(adapter, state, observation_hash, frames_dir=output / relative,
                                        manifest_dir=manifest_path.parent, **profile_options)
            audit = b.validate_candidate(wrapper, episode, steps=150, hold_action=b.HOLD,
                                          velocity_tolerance=.01, robot_position_tolerance=.002,
                                          **observation_config["limits"], **profile_options)
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
    from .validation import V6_PROFILE, RGB_QUANTIZATION_RULE
    parser.add_argument("--observation-profile", choices=(RGB_QUANTIZATION_RULE["rule_id"], V6_PROFILE))
    from .stability import PROFILE
    parser.add_argument("--stability-profile", choices=(PROFILE,))
    parser.add_argument("--rgb-certificate", type=Path,
                        help="Immutable v6 recorded-evidence certificate for the selected original candidate")
    args = parser.parse_args(argv)
    if not replay(args.manifest, args.out, task=args.task, index=args.index, protocol=args.protocol,
                  observation_profile=args.observation_profile, rgb_certificate=args.rgb_certificate,
                  stability_profile=args.stability_profile)["technical_acceptance"]:
        raise SystemExit("source replay failed; inspect replay_report.json")


if __name__ == "__main__":
    main()
