"""Synthetic file-only sources; real audit arithmetic and typed codecs, no native."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from benchmark.remaining_goals.headless import source_acceptance as module
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.observation_artifact import save_observation_artifact
from benchmark.remaining_goals.validation import validate_candidate, compare_observations, RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_RULE
from benchmark.remaining_goals.task_catalog import TASKS


HOLD = [0., 0., 0., 0., 0., 0., -1.]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def observation(state):
    return {"agentview_image": np.full((2, 2, 3), int(state[2] * 10 + state[3] * 20), np.uint8),
            "robot0_joint_pos": np.array([state[1]])}


class SyntheticAudit:
    def __init__(self, state): self.start = state.copy()
    def restore_candidate(self, episode):
        self.state = self.start.copy()
        return observation(self.state)
    def step(self, action):
        self.state[0] += .05
        return observation(self.state)
    def validation_snapshot(self):
        return {"state": self.state.copy(), "state_before_refresh": self.state.copy(), "qvel": [0.],
                "robot_qpos": [self.state[1]], "goals": [bool(v) for v in self.state[2:]],
                "object_positions": {"a": [self.state[2], 0., 0.], "b": [self.state[3], 0., 0.]},
                "penetrations": [], "fresh_observation": observation(self.state)}


def make_source(directory, task="basket"):
    """40 source declarations, 20 real fake-audit passes, 60 explicit other-mask failures."""
    root, replay = directory / "bank", directory / "replay"
    manifest = {"schema_version": "remaining-goals-v0.1", "environment": {"name": "libero", "fingerprint": "synthetic-no-runtime"}, "episodes": []}
    components = [{"goal_index": i, "indices": [i + 2], "values": [1.],
                   "values_sha256": hashlib.sha256(np.array([1.], dtype="<f8").tobytes()).hexdigest()} for i in range(2)]
    report = {"kind": "candidate_formal_adapter_replay", "policy_called": False, "release_authorized": False,
              "steps": 150, "repeats": 2, "technical_acceptance": False, "error": None, "episodes": [],
              "observation_audit_rule": RGB_QUANTIZATION_RULE, "observation_audit_limits": RGB_QUANTIZATION_AUDIT, "hold_action": HOLD}
    selected_template = None
    for index in range(10):
        for bits in ("00", "10", "01", "11"):
            identifier = f"{task}_s{index:03d}_{bits}"
            state = np.array([0., .4, *map(float, bits)])
            state_path = root / "states" / f"{identifier}.npy"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(state_path, state)
            episode = {"episode_id": identifier, "task_id": task, "suite": TASKS[task]["suite"], "task_name": TASKS[task]["name"],
                "libero_task_id": 0, "instruction": "synthetic fixture original instruction", "goal_specs": deepcopy(TASKS[task]["goals"]),
                "initial_mask": [b == "1" for b in bits], "source_id": f"{task}_official_{index}", "initial_state_index": index,
                "seed": index, "split": "val", "pose_id": "matched_settled_base", "horizon": 520, "retention_steps": 150,
                "state_path": state_path.relative_to(root).as_posix(), "state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                "bddl_sha256": "a" * 64, "model_xml_sha256": "b" * 64, "reference_robot_qpos": [.4],
                "construction": {"legal": False, "method": "synthetic matched components", "reviewed_by": "pending",
                    "components_exactly_matched": True, "selected_components": deepcopy(components),
                    "technical_audit": f"validation/{identifier}/audit.json"}}
            episode["initial_observation"] = save_observation_artifact(root, f"validation/{identifier}/initial_observation.npz", observation(state))
            if bits == "10":
                if selected_template is None:
                    selected_template = validate_candidate(SyntheticAudit(state), episode, steps=150, hold_action=HOLD, **RGB_QUANTIZATION_AUDIT)
                audit = deepcopy(selected_template)
                audit["episode_id"] = identifier
                audit["initial_observation"] = deepcopy(episode["initial_observation"])
            else:
                audit = {"technical_acceptance": True, "trace": [{"step": 0, "state": state.tolist(), "goals": episode["initial_mask"],
                        "observation_check": compare_observations(observation(state), observation(state))}]}
            write(root / episode["construction"]["technical_audit"], audit)
            manifest["episodes"].append(episode)
            for repeat in range(2):
                audit_relative = f"group_{index:03d}/repeat_{repeat:02d}/mask_{bits}/audit.json"
                if bits == "10":
                    repeated = deepcopy(audit)
                    actual = save_observation_artifact(replay / Path(audit_relative).parent, "initial_observation.npz", observation(state))
                    comparison = compare_observations(observation(state), observation(state), atol=0,
                        require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
                    reset = {"saved_state_exact": True, "initial_mask_exact": True,
                             "construction_observation_matches": True, "initial_non_rgb_exact": True}
                    repeated.update(formal_reset_checks=reset, reset_observation_comparison=comparison,
                        reset_initial_observation=actual, expected_reset_model_xml_sha256=episode["model_xml_sha256"],
                        post_restore_model_xml_sha256="c" * 64)
                    row = {"episode_id": identifier, "repetition": repeat, "initial_mask": episode["initial_mask"], "source_legal": False,
                           "technical_acceptance": True, "reset_checks": reset, "checks": repeated["checks"], "error": None, "audit_path": audit_relative}
                else:
                    repeated = {"technical_acceptance": False, "error": {"phase": "synthetic_unselected", "message": "explicit other-mask failure"}}
                    row = {"episode_id": identifier, "repetition": repeat, "initial_mask": episode["initial_mask"], "source_legal": False,
                           "technical_acceptance": False, "reset_checks": {}, "checks": {}, "error": repeated["error"], "audit_path": audit_relative}
                write(replay / audit_relative, repeated)
                report["episodes"].append(row)
    manifest["content_hash"] = manifest_hash(manifest)
    mp, rp = root / "manifest.candidates.json", replay / "replay_report.json"
    write(mp, manifest)
    report.update(source_manifest_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(), source_content_hash=manifest["content_hash"])
    write(rp, report)
    return mp, rp, manifest, report


@pytest.fixture
def source(tmp_path):
    return make_source(tmp_path)


def tree_hash(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob("*") if p.is_file()}


def test_only_selected_acceptance_does_not_promote_original_global_failure(source, tmp_path):
    mp, rp, manifest, report = source
    before = tree_hash(tmp_path)
    actual, raw, replay_raw, evidence = module.load_mask10_source("basket", mp, rp)
    assert actual == manifest and raw == mp.read_bytes() and replay_raw == rp.read_bytes()
    assert evidence["status"] == "mask10_ready" and evidence["acceptance_scope"] == "mask10"
    assert len(evidence["episodes"]) == 10 and all(len(e["replays"]) == 2 for e in evidence["episodes"])
    assert evidence["global_report_diagnostic"] == {"technical_acceptance": False, "error": None}
    assert len(evidence["unselected_failures"]) == 60
    assert tree_hash(tmp_path) == before and report["technical_acceptance"] is False
    from benchmark.remaining_goals.pilot import _source
    with pytest.raises(ValueError, match="passing independent replay"):
        _source(mp, rp)


def test_missing_unselected_files_and_running_report_are_not_scope_gates(source):
    mp, rp, manifest, report = source
    for episode in manifest["episodes"]:
        if episode["initial_mask"] != [True, False]:
            (mp.parent / episode["state_path"]).unlink()
            (mp.parent / episode["construction"]["technical_audit"]).unlink()
            (mp.parent / episode["initial_observation"]["path"]).unlink()
    for row in report["episodes"]:
        if row["initial_mask"] != [True, False]: (rp.parent / row["audit_path"]).unlink()
    report["error"] = {"message": "unselected failure retained"}
    write(rp, report)
    evidence = module.load_mask10_source("basket", mp, rp)[3]
    assert evidence["status"] == "mask10_ready" and evidence["global_report_diagnostic"]["error"] == report["error"]


@pytest.mark.parametrize("fault", ["state_bytes", "construction_empty", "construction_cached_true", "construction_initial_state",
    "construction_missing", "replay_missing", "replay_prefix", "replay_cached_true", "replay_reset", "replay_xml",
    "replay_pixels", "initial_artifact", "duplicate_repeat", "missing_repeat", "selected_failed", "source_binding", "velocity_layout"])
def test_selected_corruption_incompletion_or_failure_rejected(source, fault):
    mp, rp, manifest, report = source
    episode = next(e for e in manifest["episodes"] if e["initial_mask"] == [True, False])
    row = next(r for r in report["episodes"] if r["episode_id"] == episode["episode_id"])
    cp, ap = mp.parent / episode["construction"]["technical_audit"], rp.parent / row["audit_path"]
    if fault == "state_bytes": (mp.parent / episode["state_path"]).write_bytes(b"changed")
    elif fault == "construction_missing": cp.unlink()
    elif fault == "replay_missing": ap.unlink()
    elif fault == "initial_artifact": (mp.parent / episode["initial_observation"]["path"]).write_bytes(b"changed")
    elif fault in {"duplicate_repeat", "missing_repeat", "selected_failed", "source_binding"}:
        if fault == "duplicate_repeat": report["episodes"].append(deepcopy(row))
        elif fault == "missing_repeat": report["episodes"].remove(row)
        elif fault == "selected_failed": row["technical_acceptance"] = False
        else: report["source_manifest_sha256"] = "e" * 64
        write(rp, report)
    else:
        path = cp if fault.startswith("construction") else ap
        audit = json.loads(path.read_text())
        if fault == "construction_empty": audit["trace"] = []
        elif fault in {"construction_cached_true", "replay_cached_true"}: audit["trace"][1]["qvel"] = [.9]
        elif fault == "construction_initial_state": audit["trace"][0]["state"][0] = -0.
        elif fault == "replay_prefix": audit["trace"].pop()
        elif fault == "replay_reset": audit["formal_reset_checks"]["saved_state_exact"] = False
        elif fault == "replay_xml": audit["expected_reset_model_xml_sha256"] = "d" * 64
        elif fault == "replay_pixels": audit["reset_observation_comparison"]["max_abs_error"] = 1
        elif fault == "velocity_layout": audit["trace"][1]["qvel"] = [0., 0.]
        write(path, audit)
    with pytest.raises((OSError, ValueError)):
        module.load_mask10_source("basket", mp, rp)


def test_archived_selected_dependencies_revalidate_without_original_directories(source, tmp_path):
    mp, rp, _, _ = source
    evidence = module.load_mask10_source("basket", mp, rp)[3]
    roots = {"manifest": mp.parent, "replay": rp.parent}
    archive = tmp_path / "archive"
    for item in evidence["selected_files"]:
        out = archive / item["root"] / item["path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(roots[item["root"]] / item["path"], out)
    # Remove only checked fixture roots, never user data.
    assert mp.parent.resolve().is_relative_to(tmp_path.resolve()) and mp.parent.name == "bank"
    assert rp.parent.resolve().is_relative_to(tmp_path.resolve()) and rp.parent.name == "replay"
    shutil.rmtree(mp.parent)
    shutil.rmtree(rp.parent)
    archived_mp, archived_rp = archive / "manifest" / mp.name, archive / "replay" / rp.name
    result = module.validate_mask10_snapshot("basket", archived_mp, archived_rp, evidence)
    assert result[3] == evidence
    bad = deepcopy(evidence)
    bad["selected_episode_ids"].pop()
    with pytest.raises(ValueError): module.validate_mask10_snapshot("basket", archived_mp, archived_rp, bad)


def test_source_changes_during_validation_are_rejected(source, monkeypatch):
    mp, rp, _, report = source
    real = module._audit
    def changed(*args, **kwargs):
        report["error"] = {"message": "writer updated report"}
        write(rp, report)
        return real(*args, **kwargs)
    monkeypatch.setattr(module, "_audit", changed)
    with pytest.raises(ValueError, match="hash mismatch|changed during"):
        module.load_mask10_source("basket", mp, rp)


def test_selected_reset_recomputes_existing_rgb_allowance_from_real_typed_arrays(source):
    mp, rp, manifest, report = source
    episode = next(e for e in manifest["episodes"] if e["initial_mask"] == [True, False])
    row = next(r for r in report["episodes"] if r["episode_id"] == episode["episode_id"])
    path = rp.parent / row["audit_path"]
    audit = json.loads(path.read_text())
    state = np.load(mp.parent / episode["state_path"], allow_pickle=False)
    frozen, actual = observation(state), observation(state)
    actual["agentview_image"][0, 0, 0] += 1
    # The original codec forbids overwriting; remove only this known fixture file.
    artifact_path = path.parent / audit["reset_initial_observation"]["path"]
    assert artifact_path.resolve().is_relative_to(rp.parent.resolve())
    artifact_path.unlink()
    audit["reset_initial_observation"] = save_observation_artifact(path.parent, "initial_observation.npz", actual)
    audit["reset_observation_comparison"] = compare_observations(actual, frozen, atol=0,
        require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    audit["trace"][0]["observation_check"] = compare_observations(actual, actual, atol=0,
        require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    write(path, audit)
    evidence = module.load_mask10_source("basket", mp, rp)[3]
    assert evidence["status"] == "mask10_ready"
    assert audit["reset_observation_comparison"]["bit_exact"] is False
