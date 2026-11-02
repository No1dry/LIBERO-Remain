"""R5 microwave producer contract; native boundaries are CPU doubles only."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

from benchmark.remaining_goals import selected_build as builder
from benchmark.remaining_goals.build import HOLD, _write
from benchmark.remaining_goals.validation import V6_PROFILE, RGB_QUANTIZATION_RULE
from tests.test_task033_r2_settle import TASK, source_seam


METHOD_R5 = "microwave_gravity_support_pose_transplant_v3"
FROZEN_READER = "06817e61e07975279b4f3c4b29f410edc2357172"


def r5_seam(monkeypatch, tmp_path, *, count=1, mutation=None, **options):
    backend, env, calls, base = source_seam(monkeypatch, tmp_path, **options)
    env.sim.data = object()
    seed_quaternion = np.array([np.cos(.4), 0., 0., np.sin(.4)])
    calls["geometry"] = []
    def candidates(original, model, data, *, max_candidates):
        assert data is env.sim.data and model is env.sim.model
        calls["geometry"].append(max_candidates)
        values = []
        for number in range(count):
            state = original.copy()
            state[3] = 1.
            state[6:10] = seed_quaternion
            item = {"state": state, "allowed_indices": list(range(3, 10)) + list(range(12, 18)),
                    "diagnostics": {"method": METHOD_R5, "orientation_index": number,
                                    "floor_geom": "synthetic_floor", "seed_quaternion_wxyz": seed_quaternion.tolist()}}
            if mutation == "door": state[2] += .1
            if mutation == "velocity": state[12] = 0.
            if mutation == "whitelist": item["allowed_indices"] += [2]
            values.append(item)
        return values
    monkeypatch.setattr(builder, "_microwave_candidates", candidates, raising=False)
    backend._per_goal = lambda *a, **k: pytest.fail("R5 must not use legacy candidate generation")
    backend.combine_goal_candidates = lambda *a, **k: pytest.fail("R5 must not recombine pose seeds")
    return backend, env, calls, base, seed_quaternion


def run_r5(tmp_path, **options):
    return builder.build(tmp_path / "output", task=TASK, index=0, protocol="nine-mask10",
                         construction_method=METHOD_R5, observation_profile=V6_PROFILE, **options)


@pytest.mark.parametrize("override", [
    {"task": "bowl_drawer_close"}, {"task": "two_pots"}, {"protocol": "nine-normal00"},
    {"protocol": "selected-mask10"}, {"index": 10}, {"index": True},
    {"observation_profile": None}, {"observation_profile": RGB_QUANTIZATION_RULE["rule_id"]},
    {"max_candidates": 25},
])
def test_r5_scope_rejected_before_output_or_backend(monkeypatch, tmp_path, override):
    monkeypatch.setattr(builder, "_backend", lambda: pytest.fail("invalid R5 scope must stay file-only"))
    options = dict(task=TASK, index=0, protocol="nine-mask10", construction_method=METHOD_R5,
                   observation_profile=V6_PROFILE)
    options.update(override)
    with pytest.raises(ValueError):
        builder.build(tmp_path / "output", **options)
    assert not (tmp_path / "output").exists()


def test_r5_preserves_seed_pose_base_velocities_and_transplants_measured_full_a(monkeypatch, tmp_path):
    _, env, calls, base, quaternion = r5_seam(monkeypatch, tmp_path)
    report = run_r5(tmp_path)
    assert report["complete"], report
    assert calls["geometry"] == [24]
    assert calls["steps"] == 80 + 109
    seed = calls["restores"][1]
    assert np.array_equal(seed[6:10], quaternion)
    assert np.array_equal(seed[10:], base[10:])
    exported, episode, options = calls["audit"][0]
    assert np.array_equal(exported[6:10], env.state[6:10])
    assert not np.array_equal(exported[6:10], quaternion)
    assert not np.array_equal(exported[6:10], base[6:10])
    assert exported[16] == .005 and exported[16] != base[16]
    assert np.array_equal(exported[[1, 2, 10, 11]], base[[1, 2, 10, 11]])
    assert exported[0] == pytest.approx(4.)  # Settled base time is also frozen.
    assert options == {"validation_steps": 150, "velocity_tolerance": .01,
                       "robot_tolerance": .002, "observation_profile": V6_PROFILE}
    assert episode["construction"]["method"] == report["method"] == METHOD_R5
    assert episode["pose_id"] == "microwave_gravity_support_pose_transplant_v3"
    assert report["candidate_settle_contract"] == builder.BOUNDED_SETTLE
    assert "microwave_candidates.py" in report["builder_sources_sha256"]
    evidence = report["groups"][0]["attempts"][0]["candidate_settle"]
    assert evidence["completed_steps"] == 109 and evidence["required_stable_observations"] == 20
    assert evidence["velocity_limit"] == .01 and evidence["position_span_limit"] == .005


@pytest.mark.parametrize("mutation", ["door", "velocity", "whitelist"])
def test_r5_geometry_cannot_expand_a_seed_or_transplant_whitelist(monkeypatch, tmp_path, mutation):
    _, _, calls, _, _ = r5_seam(monkeypatch, tmp_path, mutation=mutation)
    result = run_r5(tmp_path)
    assert result["complete"] is False
    assert calls["steps"] == 80 and len(calls["restores"]) == 1
    assert calls["audit"] == []
    assert "R5" in result["groups"][0]["error"]


def test_r5_all_24_candidates_still_stop_at400_without_export(monkeypatch, tmp_path):
    _, _, calls, _, _ = r5_seam(monkeypatch, tmp_path, stable_after=401, count=24)
    result = run_r5(tmp_path)
    assert result["complete"] is False and calls["audit"] == []
    assert calls["steps"] == 80 + 24 * 400
    assert len(result["groups"][0]["attempts"]) == 24
    assert all(row["candidate_settle"]["completed_steps"] == 400
               and row["candidate_settle"]["stop_reason"] == "bounded_settle_not_converged"
               for row in result["groups"][0]["attempts"])
    assert json.loads((tmp_path / "output/manifest.candidates.json").read_text())["episodes"] == []


def test_r5_generator_cannot_exceed_requested_candidate_budget(monkeypatch, tmp_path):
    _, _, calls, _, _ = r5_seam(monkeypatch, tmp_path, count=2)
    result = run_r5(tmp_path, max_candidates=1)
    assert result["complete"] is False
    assert calls["steps"] == 80 and calls["audit"] == []


def complete_v6_fake_source(monkeypatch, tmp_path):
    """Actual producer/auditor/replayer writes artifacts; only physics is fake."""
    from benchmark.remaining_goals import selected_replay, replay_candidates
    from benchmark.remaining_goals.nine_catalog import read_goal_facts
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.validation import validate_candidate, compare_observations
    backend, _, calls, _, _ = r5_seam(monkeypatch, tmp_path)
    counts = {"construction": 0, "replay": 0}
    def observation(state):
        return {"agentview_image": np.full((16, 16, 3), 10, np.uint8),
                "robot0_eye_in_hand_image": np.full((16, 16, 3), 20, np.uint8),
                "robot0_joint_pos": state[1:2].copy()}
    class Audit:
        def __init__(self, state, semantics, stage):
            self.start, self.semantics, self.stage = state.copy(), semantics, stage
        def restore_candidate(self, episode):
            self.state = self.start.copy()
            return observation(self.state)
        def step(self, action):
            assert np.array_equal(action, HOLD)
            counts[self.stage] += 1
            self.state[0] += .05
            return observation(self.state)
        def validation_snapshot(self):
            return {"state": self.state.copy(), "state_before_refresh": self.state.copy(),
                    "qvel": self.state[10:], "robot_qpos": self.state[1:2],
                    "object_positions": {"mug": self.state[3:6]}, "penetrations": [],
                    "fresh_observation": observation(self.state),
                    **read_goal_facts(lambda p: p[0] in ("in", "open"), False, self.semantics)}
    def audit(env, state, episode, output, relative, **options):
        result = validate_candidate(Audit(state, episode["task_semantics"], "construction"), episode,
            steps=options["validation_steps"], hold_action=HOLD, observation_profile=options["observation_profile"],
            velocity_tolerance=options["velocity_tolerance"], robot_position_tolerance=options["robot_tolerance"])
        episode["initial_observation"] = save_observation_artifact(output,
            str(relative / "initial_observation.npz"), observation(state))
        result["initial_observation"] = episode["initial_observation"]
        _write(output / relative / "audit.json", result)
        return {"technical_acceptance": result["technical_acceptance"]}
    backend._audit_state = audit
    built = run_r5(tmp_path)
    assert built["complete"], built
    manifest_path = tmp_path / "output/manifest.candidates.json"
    manifest = json.loads(manifest_path.read_text())
    semantics = manifest["episodes"][0]["task_semantics"]
    class Replay(Audit):
        def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir, observation_profile):
            assert observation_profile == V6_PROFILE
            super().__init__(state, semantics, "replay")
            self.reset_checks = {"saved_state_exact": True, "initial_mask_exact": True,
                "construction_observation_matches": True, "initial_non_rgb_exact": True}
            self.reset_observation_comparison = compare_observations(observation(state), observation(state),
                atol=0, require_non_rgb_exact=True, refresh_state_unchanged=True, observation_profile=V6_PROFILE)
            self.reset_initial_observation = save_observation_artifact(frames_dir, "initial_observation.npz", observation(state))
            self.post_restore_xml_sha256 = "b" * 64
    monkeypatch.setattr(replay_candidates, "LiberoGoalEnv", lambda config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(replay_candidates, "ReplayAuditEnv", Replay)
    replay = selected_replay.replay(manifest_path, tmp_path / "replay", task=TASK, index=0,
        protocol="nine-mask10", observation_profile=V6_PROFILE)
    assert replay["technical_acceptance"], replay
    assert counts == {"construction": 150, "replay": 300}
    assert replay["steps"] == 150 and replay["repeats"] == 2
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    replay_path = tmp_path / "replay/replay_report.json"
    return {"manifest": str(manifest_path.resolve()), "manifest_sha256": sha(manifest_path),
            "content_hash": manifest["content_hash"], "candidate_replay": str(replay_path.resolve()),
            "replay_sha256": sha(replay_path)}


def test_new_v6_source_is_readable_by_unmodified_frozen_06817e61(monkeypatch, tmp_path):
    origin = complete_v6_fake_source(monkeypatch, tmp_path)
    # Use an isolated package snapshot, never a mutable/frozen deployment directory.
    git = shutil.which("git")
    assert git is not None, "git is required for the pinned-reader compatibility check"
    archived = subprocess.run([git, "archive", "--format=zip", FROZEN_READER, "benchmark"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, check=True)
    package = tmp_path / "frozen_reader"
    with zipfile.ZipFile(io.BytesIO(archived.stdout)) as stream:
        stream.extractall(package)
    origin_path = tmp_path / "fake_origin.json"
    origin_path.write_text(json.dumps(origin), encoding="utf-8")
    script = '''
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from benchmark.remaining_goals.headless import scoped_sources
assert pathlib.Path(scoped_sources.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve())
origin = json.loads(pathlib.Path(sys.argv[2]).read_text())
plan = scoped_sources.resolve_source("nine-mask10", "mug_microwave_close", 0, origin)
assert plan["status"] == "ready"
scoped_sources.archive_source(pathlib.Path(sys.argv[3]), plan)
scoped_sources.validate_snapshot(pathlib.Path(sys.argv[3]), plan)
# The same frozen reader must not accept a missing independent replay window.
report_path = pathlib.Path(origin["candidate_replay"])
report = json.loads(report_path.read_text())
missing = report_path.parent / report["episodes"][1]["audit_path"]
raw = missing.read_bytes()
missing.unlink()
try:
    try:
        scoped_sources.resolve_source("nine-mask10", "mug_microwave_close", 0, origin)
    except (ValueError, FileNotFoundError):
        pass
    else:
        raise AssertionError("frozen reader accepted missing replay evidence")
finally:
    missing.write_bytes(raw)
print("06817e61: R5 v6 ready, archive valid, missing replay rejected")
'''
    checked = subprocess.run([sys.executable, "-I", "-c", script, str(package.resolve()),
        str(origin_path.resolve()), str((tmp_path / "frozen_archive").resolve())],
        cwd=package, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "R5 v6 ready, archive valid, missing replay rejected" in checked.stdout
