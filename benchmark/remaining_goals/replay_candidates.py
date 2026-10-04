"""Replay unreviewed candidates through the formal LIBERO reset adapter.

This is an independent technical check, not a benchmark run or release step.
It never changes ``construction.legal=False`` and never calls a policy. One
LiberoGoalEnv instance is reused across masks and repeated passes, including
the 11 -> 00 transition that can reveal persistent simulator/visual state.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from copy import deepcopy
import hashlib
import io
import itertools
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import numpy as np

from .build import CandidateAuditEnv, HOLD, _image, _state, _write
from .libero_env import LiberoGoalEnv, model_xml_hash
from .schema import SCHEMA_VERSION, manifest_hash, verify_state_file
from .observation_artifact import load_observation_artifact, save_observation_artifact
from .validation import compare_observations, validate_candidate, RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_LIMITATION, RGB_QUANTIZATION_RULE


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)


def _audit_path(base, raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("candidate needs a construction.technical_audit path")
    portable, windows = PurePosixPath(raw.replace("\\", "/")), PureWindowsPath(raw)
    if (windows.drive or windows.root or portable.is_absolute() or ".." in portable.parts
            or any(":" in part or part.endswith((" ", ".")) for part in portable.parts)
            or portable.suffix != ".json"):
        raise ValueError("technical audit path must be a contained relative JSON path")
    resolved = (base / Path(*portable.parts)).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("technical audit path escaped candidate pack")
    return resolved


def _candidate_pack(path):
    """Validate this builder's candidate format without impersonating a release.

    The evaluation schema intentionally rejects legal=False. This dedicated
    preflight checks hashes, complete paired masks and exact saved components
    without rewriting the declaration or invoking an evaluation loader.
    The formal adapter independently verifies the official task and scene.
    """
    path = Path(path)
    manifest = _read_json(path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported candidate schema version")
    if manifest.get("content_hash") != manifest_hash(manifest):
        raise ValueError("candidate manifest content_hash mismatch")
    if manifest.get("environment", {}).get("name") != "libero":
        raise ValueError("candidate replay requires a real LIBERO environment")
    if not isinstance(manifest["environment"].get("fingerprint"), str) or not manifest["environment"]["fingerprint"]:
        raise ValueError("candidate environment needs an explicit fingerprint")
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("candidate pack must contain complete nonempty groups")
    groups, seen_ids, states, hashes = OrderedDict(), set(), {}, {}
    group_fields = ("task_id", "suite", "libero_task_id", "task_name", "instruction", "goal_specs",
                    "seed", "initial_state_index", "split", "horizon", "retention_steps",
                    "bddl_sha256", "model_xml_sha256", "reference_robot_qpos")
    for episode in episodes:
        for field in ("episode_id", "task_id", "suite", "task_name", "instruction", "source_id", "pose_id",
                      "bddl_sha256", "model_xml_sha256"):
            if not isinstance(episode.get(field), str) or not episode[field].strip():
                raise ValueError(f"candidate episode needs {field}")
        for field in ("libero_task_id", "initial_state_index", "seed", "horizon", "retention_steps"):
            if type(episode.get(field)) is not int:
                raise ValueError(f"candidate {field} must be an integer")
        if (episode["libero_task_id"] < 0 or episode["initial_state_index"] < 0
                or min(episode["horizon"], episode["retention_steps"]) < 1):
            raise ValueError("candidate indices/budgets are out of range")
        if episode.get("split") not in ("train", "val", "test"):
            raise ValueError("candidate split must be explicit")
        identifier = episode["episode_id"]
        if identifier in seen_ids:
            raise ValueError("duplicate candidate episode_id")
        seen_ids.add(identifier)
        goals, mask = episode.get("goal_specs"), episode.get("initial_mask")
        if (not isinstance(goals, list) or len(goals) not in (2, 3) or not isinstance(mask, list)
                or len(mask) != len(goals) or any(type(bit) is not bool for bit in mask)):
            raise ValueError("candidate needs two/three goals and an exact boolean mask")
        goal_ids = set()
        for goal in goals:
            if not isinstance(goal, dict) or any(not isinstance(goal.get(key), str) or not goal[key].strip()
                                                  for key in ("id", "language")):
                raise ValueError("candidate goal needs id and language")
            if goal["id"] in goal_ids:
                raise ValueError("duplicate candidate goal id")
            goal_ids.add(goal["id"])
            predicates = goal.get("predicates")
            if (not isinstance(predicates, list) or not predicates or any(
                    not isinstance(p, list) or len(p) not in (2, 3)
                    or any(not isinstance(token, str) or not token
                           or any(ch.isspace() or ch in "()" for ch in token) for token in p)
                    for p in predicates)):
                raise ValueError("candidate predicates must be flat atomic tokens")
        construction = episode.get("construction", {})
        if construction.get("legal") is not False:
            raise ValueError("this CLI accepts explicitly unreviewed legal=False candidates only")
        if construction.get("components_exactly_matched") is not True:
            raise ValueError("candidate must declare matched goal components for independent verification")
        state_path = verify_state_file(episode, path.parent)
        raw = state_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != episode["state_sha256"]:
            raise ValueError("candidate state changed after verification")
        state = np.load(io.BytesIO(raw), allow_pickle=False)
        states[identifier] = state.copy()
        audit = _read_json(_audit_path(path.parent, construction.get("technical_audit")))
        if audit.get("technical_acceptance") is not True or not audit.get("trace"):
            raise ValueError("candidate lacks a passing construction audit")
        initial = audit["trace"][0]
        if (initial.get("step") != 0 or initial.get("goals") != mask
                or not np.array_equal(np.asarray(initial.get("state")), state)):
            raise ValueError("construction audit step 0 differs from saved candidate state/mask")
        observation_hash = initial.get("observation_check", {}).get("returned_sha256")
        if (not isinstance(observation_hash, str) or len(observation_hash) != 64
                or any(ch not in "0123456789abcdef" for ch in observation_hash)):
            raise ValueError("construction audit needs an exact initial observation hash")
        load_observation_artifact(path.parent, episode.get("initial_observation"), expected_digest=observation_hash)
        hashes[identifier] = observation_hash
        key = (episode["task_id"], episode["source_id"], episode["pose_id"])
        group = groups.setdefault(key, [])
        if group and any(group[0].get(field) != episode.get(field) for field in group_fields):
            raise ValueError("candidate group has inconsistent task, scene identity, or budget")
        if any(prior["initial_mask"] == mask for prior in group):
            raise ValueError("duplicate candidate mask in group")
        group.append(episode)
    for group in groups.values():
        n_goals = len(group[0]["goal_specs"])
        if {tuple(e["initial_mask"]) for e in group} != set(itertools.product((False, True), repeat=n_goals)):
            raise ValueError("candidate group lacks complete masks")
        group.sort(key=lambda e: sum(int(bit) << i for i, bit in enumerate(e["initial_mask"])))
        base = states[group[0]["episode_id"]]
        components = group[0]["construction"].get("selected_components")
        if not isinstance(components, list) or len(components) != n_goals:
            raise ValueError("candidate must record one actual component per goal")
        occupied = set()
        for i, component in enumerate(components):
            if component.get("goal_index") != i:
                raise ValueError("candidate component order does not match goals")
            indices, values = component.get("indices"), np.asarray(component.get("values"))
            if (not isinstance(indices, list) or not indices
                    or any(type(index) is not int or not 0 <= index < len(base) for index in indices)
                    or len(set(indices)) != len(indices) or occupied.intersection(indices)
                    or values.shape != (len(indices),) or values.dtype.kind not in "fiu"
                    or not np.isfinite(values).all()):
                raise ValueError("candidate component indices/values are invalid or overlap")
            occupied.update(indices)
            if hashlib.sha256(values.astype("<f8").tobytes()).hexdigest() != component.get("values_sha256"):
                raise ValueError("candidate component hash mismatch")
        for episode in group:
            if episode["construction"].get("selected_components") != components:
                raise ValueError("candidate components differ across masks")
            expected = base.copy()
            for bit, component in zip(episode["initial_mask"], components):
                if bit:
                    expected[component["indices"]] = component["values"]
            if not np.array_equal(states[episode["episode_id"]], expected):
                raise ValueError("saved four-mask states do not have exactly matched components")
    return manifest, list(groups.values()), states, hashes


class ReplayAuditEnv:
    """Use the real evaluator reset/step path while exposing auditor snapshots."""
    def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir):
        self.adapter, self.expected_state = adapter, state
        self.expected_observation_hash, self.frames_dir = observation_hash, frames_dir
        self.reset_checks = {}
        self.manifest_dir = Path(manifest_dir)
        self.reset_observation_comparison = None
        self.reset_initial_observation = None
        self.post_restore_xml_sha256 = None

    def restore_candidate(self, episode):
        self.steps = 0
        self.reset_checks = {}
        self.reset_observation_comparison = None
        self.reset_initial_observation = None
        expected_observation = load_observation_artifact(self.manifest_dir, episode.get("initial_observation"),
                                                         expected_digest=self.expected_observation_hash)
        observation = self.adapter.reset(deepcopy(episode))
        # Retain independent live reset evidence for offline pixel comparison.
        # This reference is relative to this audit's own directory.
        self.reset_initial_observation = save_observation_artifact(self.frames_dir, "initial_observation.npz", observation)
        actual = _state(self.adapter.env)
        saved_state_exact = (actual.shape == self.expected_state.shape
                             and bool(np.array_equal(actual.view(np.uint64), self.expected_state.view(np.uint64))))
        # XML is already checked by the formal adapter. The initial state must
        # match exactly before this cross-render RGB-only rule is eligible.
        check = compare_observations(observation, expected_observation, atol=0,
                                     require_non_rgb_exact=True,
                                     refresh_state_unchanged=saved_state_exact, **RGB_QUANTIZATION_AUDIT)
        self.reset_observation_comparison = check
        self.reset_checks = {
            "saved_state_exact": saved_state_exact,
            "initial_mask_exact": self.adapter.goal_values() == episode["initial_mask"],
            "construction_observation_matches": check["matches"],
            "initial_non_rgb_exact": check["non_rgb_bit_exact"],
        }
        self.post_restore_xml_sha256 = model_xml_hash(self.adapter.env)
        _image(self.frames_dir / "start.png", observation)
        if not all(self.reset_checks.values()):
            raise ValueError(f"formal reset differs from construction: {self.reset_checks}")
        self.native = CandidateAuditEnv(self.adapter.env, self.expected_state, episode["goal_specs"])
        return observation

    def step(self, action):
        observation = self.adapter.step(action)
        self.steps += 1
        if self.steps % 50 == 0:
            _image(self.frames_dir / f"step_{self.steps:04d}.png", observation)
        return observation

    def validation_snapshot(self):
        snapshot = self.native.validation_snapshot()
        snapshot["goals"] = self.adapter.goal_values()
        return snapshot


def replay(manifest_path: Path, output: Path, *, steps=150, repeats=2, image_size=256,
           velocity_tolerance=0.01, robot_tolerance=0.002):
    if any(type(value) is not int or value < 1 for value in (steps, repeats, image_size)):
        raise ValueError("replay steps, repeats and image_size must be positive integers")
    manifest_path, output = Path(manifest_path), Path(output)
    manifest, groups, states, hashes = _candidate_pack(manifest_path)
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "candidate_formal_adapter_replay", "policy_called": False, "release_authorized": False,
              "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "source_content_hash": manifest["content_hash"], "steps": steps, "repeats": repeats,
              "observation_audit_limits": dict(RGB_QUANTIZATION_AUDIT),
              "observation_audit_limitation": RGB_QUANTIZATION_LIMITATION,
              "observation_audit_rule": dict(RGB_QUANTIZATION_RULE),
              "hold_action": HOLD.tolist(), "technical_acceptance": False, "episodes": [], "error": None}
    control_freq = manifest["environment"].get("lock", {}).get("control_freq", 20)
    adapter = None
    try:
        adapter = LiberoGoalEnv({"manifest_dir": str(manifest_path.parent), "environment": manifest["environment"],
                                "control_freq": control_freq, "image_size": image_size})
        for group_index, group in enumerate(groups):
            for repetition in range(repeats):
                for episode_index, episode in enumerate(group):
                    identifier = episode["episode_id"]
                    relative = Path(f"group_{group_index:03d}") / f"repeat_{repetition:02d}" / f"mask_{episode_index:02d}"
                    wrapper = ReplayAuditEnv(adapter, states[identifier], hashes[identifier], frames_dir=output / relative,
                                             manifest_dir=manifest_path.parent)
                    audit = validate_candidate(wrapper, episode, steps=steps, hold_action=HOLD,
                                               velocity_tolerance=velocity_tolerance,
                                               robot_position_tolerance=robot_tolerance, **RGB_QUANTIZATION_AUDIT)
                    audit["formal_reset_checks"] = wrapper.reset_checks
                    audit["reset_observation_comparison"] = wrapper.reset_observation_comparison
                    audit["reset_initial_observation"] = wrapper.reset_initial_observation
                    audit["post_restore_model_xml_sha256"] = wrapper.post_restore_xml_sha256
                    audit["expected_reset_model_xml_sha256"] = episode["model_xml_sha256"]
                    _write(output / relative / "audit.json", audit)
                    entry = {"episode_id": identifier, "group": group_index, "repetition": repetition,
                             "initial_mask": episode["initial_mask"], "source_legal": episode["construction"]["legal"],
                             "technical_acceptance": audit["technical_acceptance"], "reset_checks": wrapper.reset_checks,
                             "checks": audit["checks"], "error": audit["error"],
                             "audit_path": (relative / "audit.json").as_posix()}
                    report["episodes"].append(entry)
                    _write(output / "replay_report.json", report)
                    print(f"{identifier} replay {repetition}: technical_acceptance={entry['technical_acceptance']}", flush=True)
        report["technical_acceptance"] = bool(report["episodes"]) and all(
            item["technical_acceptance"] for item in report["episodes"])
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        if adapter is not None:
            adapter.close()
        _write(output / "replay_report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--velocity-tolerance", type=float, default=.01)
    parser.add_argument("--robot-tolerance", type=float, default=.002)
    args = parser.parse_args(argv)
    report = replay(args.manifest, args.out, steps=args.steps, repeats=args.repeats, image_size=args.image_size,
                    velocity_tolerance=args.velocity_tolerance, robot_tolerance=args.robot_tolerance)
    if not report["technical_acceptance"]:
        raise SystemExit("Candidate replay failed technical acceptance; inspect replay_report.json")


if __name__ == "__main__":
    main()
