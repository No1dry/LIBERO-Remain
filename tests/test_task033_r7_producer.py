"""R7 producer/replay wiring, with only native physics replaced by CPU doubles."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import selected_build as builder, selected_replay
from benchmark.remaining_goals.validation import V6_PROFILE
from tests.test_task033_r5_builder import r5_seam
from tests.test_task033_r2_settle import TASK

PROFILE = "active-free-object-pose-stability-v7"


def run_r7(tmp_path, **options):
    return builder.build(tmp_path / "output", task=TASK, index=0, protocol="nine-mask10",
        construction_method=builder.METHOD_R5, observation_profile=V6_PROFILE,
        stability_profile=PROFILE, **options)


@pytest.mark.parametrize("override", [
    {"task": "two_pots"}, {"protocol": "nine-normal00"}, {"index": True}, {"index": 10},
    {"construction_method": builder.METHOD_R2}, {"observation_profile": None},
    {"stability_profile": "unknown"}, {"max_candidates": 25},
])
def test_r7_invalid_scope_stays_before_output_and_backend(monkeypatch, tmp_path, override):
    monkeypatch.setattr(builder, "_backend", lambda: pytest.fail("invalid scope reached native backend"))
    options = dict(task=TASK, index=0, protocol="nine-mask10", construction_method=builder.METHOD_R5,
                   observation_profile=V6_PROFILE, stability_profile=PROFILE)
    options.update(override)
    with pytest.raises(ValueError):
        builder.build(tmp_path / "output", **options)
    assert not (tmp_path / "output").exists()


def test_r7_replay_requires_explicit_source_profile_before_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(selected_replay, "_backend", lambda: pytest.fail("profile mismatch reached native backend"))
    # This must reject before even asking the file-only candidate reader to inspect sources.
    monkeypatch.setattr(selected_replay, "_candidate", lambda *a, **k: pytest.fail("invalid scope reached reader"))
    with pytest.raises(ValueError):
        selected_replay.replay(tmp_path / "absent.json", tmp_path / "replay", task="two_pots", index=0,
            protocol="nine-mask10", observation_profile=V6_PROFILE, stability_profile=PROFILE)
    assert not (tmp_path / "replay").exists()


def r7_seam(monkeypatch, tmp_path, *, mode=None):
    """Keep the real wrapper, settling, auditor and artifact writers; replace native IO."""
    from benchmark.remaining_goals import build, construction
    backend, env, calls, base, quaternion = r5_seam(monkeypatch, tmp_path, stable_after=401)
    env.sim.data = SimpleNamespace(ncon=0, contact=[])
    env.env.parsed_problem["objects"] = {"mug": ["white_yellow_mug_1"]}
    env.env.objects_dict = {}
    env.env.fixtures_dict = {key: SimpleNamespace(root_body="microwave")
        for key in ("microwave_1", "microwave_1_heating_region")}
    env.sim.model.body_name2id = lambda name: 0
    monkeypatch.setattr(construction, "_collision_geoms", lambda *a: [])
    robot = lambda state, layout, n: np.array([state[1]] + [0.] * 8)
    monkeypatch.setattr(build.ms, "get_robot_qpos", robot)
    backend.ms.get_robot_qpos = robot
    def observation(actual):
        return {"agentview_image": np.full((16, 16, 3), 10, np.uint8),
                "robot0_eye_in_hand_image": np.full((16, 16, 3), 20, np.uint8),
                "robot0_joint_pos": actual.state[1:2].copy()}
    native_step, native_restore = backend._step, backend.restore_raw_state
    def step(actual, action):
        native_step(actual, action)
        if actual.phase == "candidate":
            if mode == "non_a_velocity": actual.state[11] = .02
            if mode == "signflip" and actual.elapsed % 2: actual.state[6:10] *= -1
            if mode == "rotation":
                angle = actual.elapsed * .002
                actual.state[6:10] = [np.cos(angle / 2), 0., np.sin(angle / 2), 0.]
            if mode == "position": actual.state[3] = 1 + actual.elapsed * .0004
        return observation(actual)
    def restore(actual, state):
        native_restore(actual, state)
        return observation(actual)
    for name, value in {"_step": step, "restore_raw_state": restore,
                        "_state": backend._state, "fresh_observation": observation,
                        "model_xml_hash": backend.model_xml_hash}.items():
        monkeypatch.setattr(build, name, value)
    backend._step, backend.restore_raw_state = step, restore
    backend.CandidateAuditEnv = build.CandidateAuditEnv
    backend._audit_state = build._audit_state
    return backend, env, calls, base, quaternion, observation


@pytest.mark.parametrize("mode", [None, "signflip"])
def test_r7_high_active_velocity_keeps_measured_pose_and_complete_settle_evidence(monkeypatch, tmp_path, mode):
    _, _, calls, base, seed_quaternion, _ = r7_seam(monkeypatch, tmp_path, mode=mode)
    report = run_r7(tmp_path)
    assert report["complete"], report
    assert calls["steps"] == 80 + 80 + 150
    episode = json.loads((tmp_path / "output/manifest.candidates.json").read_text())["episodes"][0]
    state = np.load(tmp_path / "output" / episode["state_path"])
    assert state[16] == pytest.approx(.1969393956621151)
    assert np.array_equal(state[[1, 2, 10, 11]], base[[1, 2, 10, 11]])
    assert not np.array_equal(state[6:10], seed_quaternion)
    assert state[6:10] == pytest.approx([np.cos(.05), 0., np.sin(.05), 0.])
    assert report["stability_profile"] == episode["stability_profile"] == PROFILE
    assert report["observation_profile"] == episode["observation_profile"] == V6_PROFILE
    assert report["candidate_settle_contract"]["stability_profile"] == PROFILE
    assert report["candidate_settle_contract"]["velocity_limit_scope"] == "non_active_qvel_only"
    settle = report["groups"][0]["attempts"][0]["candidate_settle"]
    assert settle["completed_steps"] == 80 and settle["required_stable_observations"] == 20
    assert len(settle["samples"]) == 80
    assert settle["stability_binding"] == episode["stability_binding"] == report["stability_binding"]
    for row in settle["samples"]:
        assert len(row["state"]) == 18 and len(row["qvel"]) == 8
        assert row["qvel"][6] == pytest.approx(.1969393956621151)
        assert row["stability_binding"] == episode["stability_binding"]
        assert row["observation_check"]["matches"] is True
        assert row["penetrations"] == [] and row["goal_facts"]["required_open_values"] == [True]
    audit = json.loads((tmp_path / "output" / episode["construction"]["technical_audit"]).read_text())
    assert audit["technical_acceptance"] and audit["completed_steps"] == 150
    assert len(audit["trace"]) == 151
    assert all(row["qvel"][6] == pytest.approx(.1969393956621151) for row in audit["trace"])


@pytest.mark.parametrize("mode", ["non_a_velocity", "rotation", "position"])
def test_r7_settle_retains_non_a_and_pose_bounds_and_stops_at400(monkeypatch, tmp_path, mode):
    _, _, calls, _, _, _ = r7_seam(monkeypatch, tmp_path, mode=mode)
    report = run_r7(tmp_path)
    assert not report["complete"]
    assert calls["steps"] == 80 + 400
    settle = report["groups"][0]["attempts"][0]["candidate_settle"]
    assert settle["completed_steps"] == 400 and not settle["converged"]
    assert len(settle["samples"]) == 400


@pytest.mark.parametrize("difference,accepted,steps", [(5e-9, True, 80), (2e-8, False, 400)])
def test_r7_dynamic_settle_keeps_v6_non_rgb_tolerance(monkeypatch, tmp_path, difference, accepted, steps):
    from benchmark.remaining_goals import build
    _, _, calls, _, _, _ = r7_seam(monkeypatch, tmp_path)
    native_snapshot = build.CandidateAuditEnv.validation_snapshot
    def snapshot(self):
        result = native_snapshot(self)
        if self.frames_dir is None:  # The preparation observer; formal step0 stays exact.
            result["fresh_observation"]["robot0_joint_pos"][0] += difference
        return result
    monkeypatch.setattr(build.CandidateAuditEnv, "validation_snapshot", snapshot)
    report = run_r7(tmp_path)
    assert report["complete"] is accepted, report
    settle = report["groups"][0]["attempts"][0]["candidate_settle"]
    assert settle["completed_steps"] == steps
    assert calls["steps"] == 80 + steps + (150 if accepted else 0)
    assert all(row["observation_check"]["matches"] is accepted for row in settle["samples"])
    assert all(row["observation_check"]["non_rgb_bit_exact"] is False for row in settle["samples"])


def test_r7_settle_refresh_cannot_change_only_state_signed_zero(monkeypatch, tmp_path):
    from benchmark.remaining_goals import build
    _, _, calls, _, _, _ = r7_seam(monkeypatch, tmp_path)
    native_snapshot = build.CandidateAuditEnv.validation_snapshot
    def snapshot(self):
        result = native_snapshot(self)
        if self.frames_dir is None:
            assert result["state"][7] == 0.
            result["state_before_refresh"][7] = -0.
        return result
    monkeypatch.setattr(build.CandidateAuditEnv, "validation_snapshot", snapshot)
    report = run_r7(tmp_path)
    assert not report["complete"]
    assert calls["steps"] == 80 + 400
    settle = report["groups"][0]["attempts"][0]["candidate_settle"]
    assert all(not row["eligible"] for row in settle["samples"])


def complete_v7_fake_source(monkeypatch, tmp_path, *, replay_model_mismatch=False):
    """Produce artifacts with real construction150, ReplayAuditEnv and 2x150 auditor."""
    import hashlib
    from benchmark.remaining_goals import replay_candidates
    from benchmark.remaining_goals.nine_catalog import read_goal_facts
    backend, env, calls, _, _, observation = r7_seam(monkeypatch, tmp_path)
    built = run_r7(tmp_path)
    assert built["complete"], built
    construction_steps = calls["steps"]
    manifest_path = tmp_path / "output/manifest.candidates.json"
    manifest = json.loads(manifest_path.read_text())
    episode = manifest["episodes"][0]
    state = np.load(manifest_path.parent / episode["state_path"])
    resets = []
    class Adapter:
        def __init__(self, config): self.env = env
        def reset(self, source):
            self.task_semantics = source["task_semantics"]
            resets.append(deepcopy(source))
            return backend.restore_raw_state(self.env, state)
        def goal_values(self): return [True, False]
        def goal_facts(self):
            return read_goal_facts(self.env.env._eval_predicate, False, self.task_semantics)
        def step(self, action): return backend._step(self.env, action)
        def close(self): pass
    monkeypatch.setattr(replay_candidates, "LiberoGoalEnv", Adapter)
    monkeypatch.setattr(replay_candidates, "_state", backend._state)
    monkeypatch.setattr(replay_candidates, "model_xml_hash",
        (lambda actual: "e" * 64) if replay_model_mismatch else backend.model_xml_hash)
    replay = selected_replay.replay(manifest_path, tmp_path / "replay", task=TASK, index=0,
        protocol="nine-mask10", observation_profile=V6_PROFILE, stability_profile=PROFILE)
    if replay_model_mismatch:
        assert not replay["technical_acceptance"]
        assert calls["steps"] == construction_steps
        return replay
    assert replay["technical_acceptance"], replay
    assert len(resets) == 2
    assert calls["steps"] == 80 + 80 + 150 + 300
    for item in replay["episodes"]:
        audit = json.loads((tmp_path / "replay" / item["audit_path"]).read_text())
        assert audit["completed_steps"] == 150 and len(audit["trace"]) == 151
        assert audit["stability_profile"] == PROFILE
        assert audit["stability_binding"] == episode["stability_binding"]
        assert audit["formal_reset_checks"]["stability_binding_matches_compiled_model"]
        assert all(row["qvel"][6] == pytest.approx(.1969393956621151) for row in audit["trace"])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    replay_path = tmp_path / "replay/replay_report.json"
    return {"manifest": str(manifest_path.resolve()), "manifest_sha256": sha(manifest_path),
        "content_hash": manifest["content_hash"], "candidate_replay": str(replay_path.resolve()),
        "replay_sha256": sha(replay_path), "stability_profile": PROFILE}


def test_r7_full_producer_and_actual_replay_wrapper_write_two_complete_windows(monkeypatch, tmp_path):
    from benchmark.remaining_goals.headless import scoped_sources
    origin = complete_v7_fake_source(monkeypatch, tmp_path)
    plan = scoped_sources.resolve_source("nine-mask10", TASK, 0, origin)
    assert plan["status"] == "ready"
    assert plan["episodes"][0]["stability_profile"] == PROFILE
    scoped_sources.archive_source(tmp_path / "archive", plan)
    scoped_sources.validate_snapshot(tmp_path / "archive", plan)


def test_r7_actual_restored_model_binding_mismatch_rejects_without_hold(monkeypatch, tmp_path):
    report = complete_v7_fake_source(monkeypatch, tmp_path, replay_model_mismatch=True)
    assert all(not item["reset_checks"]["stability_binding_matches_compiled_model"] for item in report["episodes"])


def test_r7_replay_cannot_silently_use_v6_when_explicit_profile_is_omitted(monkeypatch, tmp_path):
    complete_v7_fake_source(monkeypatch, tmp_path)
    monkeypatch.setattr(selected_replay, "_backend", lambda: pytest.fail("missing profile reached backend"))
    with pytest.raises(ValueError):
        selected_replay.replay(tmp_path / "output/manifest.candidates.json", tmp_path / "omitted", task=TASK,
            index=0, protocol="nine-mask10", observation_profile=V6_PROFILE)
    assert not (tmp_path / "omitted").exists()
