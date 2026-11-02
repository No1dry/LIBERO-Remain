"""R2 candidate settling must converge physically before state transplantation."""
from copy import deepcopy
import json
import re
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import selected_build as builder
from benchmark.remaining_goals.build import HOLD, _write
from benchmark.remaining_goals.nine_catalog import get_task
from benchmark.states import mujoco_state as ms


R2_METHOD = "selected_A_only_bounded_settle_component_transplant_v2"
TASK = "mug_microwave_close"


def source_seam(monkeypatch, tmp_path, *, stable_after=90, drift=False, fail_after=None, invalidate=False):
    """Only physics/native boundaries are replaced; real producer/layout writes artifacts."""
    model = SimpleNamespace(nq=9, nv=8, na=0, njnt=3,
        joint_names=["robot0_joint1", "microwave_1_joint0", "white_yellow_mug_1_joint0"],
        jnt_type=np.array([3, 3, 0]), jnt_qposadr=np.array([0, 1, 2]), jnt_dofadr=np.array([0, 1, 2]))
    base = np.array([0., .4, .7, .1, .2, .3, 1., 0., 0., 0., .004, .002, .003, .004, .005, .006, .007, .008])
    env = SimpleNamespace(state=base.copy(), sim=SimpleNamespace(model=model), phase="base", elapsed=0)
    calls = {"steps": 0, "audit": [], "restores": [], "profiles": []}
    profile = get_task(TASK)
    env.seed = lambda value: None
    env.close = lambda: None
    env.env = SimpleNamespace(parsed_problem={"goal_state": deepcopy(profile["official_goal_predicates"])})
    def evaluate(p):
        if p[0] == "in": return bool(env.state[3] > .5 and not (invalidate and env.elapsed >= 50))
        if p[0] == "open": return True
        if p[0] == "close": return False
        raise AssertionError(p)
    env.env._eval_predicate = evaluate
    env.check_success = lambda: False
    def restore(actual, state):
        actual.state = state.copy()
        actual.elapsed = 0
        actual.phase = "candidate" if state[3] > .5 else "base"
        calls["restores"].append(state.copy())
    def step(actual, action):
        assert np.array_equal(action, HOLD)
        calls["steps"] += 1
        actual.elapsed += 1
        if actual.phase == "candidate":
            if actual.elapsed == fail_after:
                raise RuntimeError("synthetic uncertain step")
            actual.state[16] = .005 if actual.elapsed >= stable_after else .1969393956621151
            actual.state[3] = 1. + (.0004 * actual.elapsed if drift else .00001 * min(actual.elapsed, stable_after))
            # Real final orientation must survive; the seed orientation is not restored.
            actual.state[6:10] = [np.cos(.05), 0., np.sin(.05), 0.]
        actual.state[0] += .05
    def per_goal(actual, original, active, limit):
        calls["profiles"].append(deepcopy(active))
        candidate = original.copy()
        candidate[3] = 1.
        # The inherited geometry seed clears velocity. R2 must undo that before
        # native restore, retaining actual base velocities rather than zeros.
        candidate[10:] = 0.
        return [[{"state": candidate, "allowed_indices": list(range(3, 10)) + list(range(12, 18)),
                   "diagnostics": {"clearance": .002, "seed_orientation_preserved": True}}]]
    def audit(actual, state, episode, output, relative, **kwargs):
        calls["audit"].append((state.copy(), deepcopy(episode), kwargs))
        assert max(abs(state[10:])) <= .01
        assert kwargs["validation_steps"] == 150
        episode["initial_observation"] = {"sha256": "c" * 64, "observation_sha256": "d" * 64}
        return {"technical_acceptance": True, "audit_path": str(relative / "audit.json")}
    bddl = tmp_path / "fixture.bddl"
    bddl.write_text("synthetic official microwave fixture")
    task = SimpleNamespace(name=profile["name"], language=re.split(r"SCENE\d+_", profile["name"])[1].replace("_", " "))
    state_helpers = SimpleNamespace(StateLayout=ms.StateLayout, resolve_free_joint=ms.resolve_free_joint,
        get_robot_qpos=lambda state, layout, n: state[1:2].copy())
    backend = SimpleNamespace(_write=_write, HOLD=HOLD, ms=state_helpers,
        create_scene=lambda *a, **k: (env, task, bddl), environment_identity=lambda freq: {"name": "libero", "fingerprint": "fake"},
        _official_initial_states=lambda *a: [base.copy()] * 10, reset_scene=lambda actual: None,
        model_xml_hash=lambda actual: "b" * 64, restore_raw_state=restore, _step=step,
        _state=lambda actual: actual.state.copy(), _goals=lambda actual, goals: [evaluate(g["predicates"][0]) for g in goals],
        _per_goal=per_goal, combine_goal_candidates=lambda original, model, goal, mask, **k: goal[0],
        state_diff_whitelist=lambda original, state, model, indices: {"valid": all(original[i] == state[i] for i in range(len(state)) if i not in indices)},
        _audit_state=audit)
    monkeypatch.setattr(builder, "_backend", lambda: backend)
    monkeypatch.setattr(builder, "_suite", lambda profile: SimpleNamespace(n_tasks=10,
        get_task=lambda i: task if i == 9 else SimpleNamespace(name="other")))
    monkeypatch.setattr(builder, "_official_asset", lambda *a: {"asset": "fixture.init", "sha256": "a" * 64})
    return backend, env, calls, base


def run_r2(tmp_path):
    return builder.build(tmp_path / "output", task=TASK, index=0, protocol="nine-mask10",
                         construction_method=R2_METHOD)


def test_unstable_after80_waits_for20_real_converged_frames_and_copies_full_component(monkeypatch, tmp_path):
    _, env, calls, base = source_seam(monkeypatch, tmp_path)
    result = run_r2(tmp_path)
    assert result["complete"] is True
    assert calls["steps"] == 80 + 109  # Candidate steps90..109 are the first20 stable samples.
    assert len(calls["audit"]) == 1
    exported, episode, _ = calls["audit"][0]
    assert exported[16] == .005 and exported[16] != 0.
    assert np.array_equal(exported[6:10], env.state[6:10])
    assert np.array_equal(exported[[1, 2, 10, 11]], base[[1, 2, 10, 11]])
    assert np.array_equal(calls["restores"][1][10:], base[10:])
    evidence = result["groups"][0]["attempts"][0]["candidate_settle"]
    assert evidence["converged"] and evidence["completed_steps"] == 109
    assert evidence["max_steps"] == 400 and evidence["required_stable_observations"] == 20
    assert evidence["samples"][79]["max_abs_qvel"] == pytest.approx(.1969393956621151)
    assert evidence["samples"][-1]["selected_qvel"][-2] == .005
    assert episode["construction"]["method"] == R2_METHOD
    assert len(json.loads((tmp_path / "output/manifest.candidates.json").read_text())["episodes"]) == 1


@pytest.mark.parametrize("case", ["velocity", "drift", "predicate"])
def test_unconverged_candidate_is_bounded_failed_without_transplant_or_audit(monkeypatch, tmp_path, case):
    _, _, calls, _ = source_seam(monkeypatch, tmp_path,
        stable_after=401 if case == "velocity" else 1, drift=case == "drift", invalidate=case == "predicate")
    result = run_r2(tmp_path)
    assert result["complete"] is False
    assert calls["steps"] == 80 + 400
    assert calls["audit"] == []
    attempt = result["groups"][0]["attempts"][0]
    assert attempt["technical_acceptance"] is False
    assert attempt["candidate_settle"]["stop_reason"] == "bounded_settle_not_converged"
    assert attempt["candidate_settle"]["completed_steps"] == 400
    assert json.loads((tmp_path / "output/manifest.candidates.json").read_text())["episodes"] == []


def test_settle_exception_preserves_partial_control_count_and_never_exports(monkeypatch, tmp_path):
    _, _, calls, _ = source_seam(monkeypatch, tmp_path, fail_after=83)
    result = run_r2(tmp_path)
    assert result["complete"] is False and calls["audit"] == []
    evidence = result["groups"][0]["attempts"][0]["candidate_settle"]
    assert evidence["attempted_steps"] == 83 and evidence["completed_steps"] == 82
    assert evidence["exception_calls"] == 1 and evidence["stop_reason"] == "step_exception"
    assert "synthetic uncertain step" in result["groups"][0]["error"]


@pytest.mark.parametrize("protocol,task", [("nine-normal00", TASK), ("selected-mask10", "frypan_stove9")])
def test_r2_method_cannot_change_00_or_legacy_construction(monkeypatch, tmp_path, protocol, task):
    monkeypatch.setattr(builder, "_backend", lambda: pytest.fail("native backend should not load"))
    with pytest.raises(ValueError):
        builder.build(tmp_path / "out", task=task, index=0, protocol=protocol, construction_method=R2_METHOD)


@pytest.mark.parametrize("fail_after", [None, 83])
def test_existing_control_ledger_counts_actual_adaptive_steps(monkeypatch, tmp_path, fail_after):
    from benchmark.remaining_goals.headless.selected_preparation import _run_counted
    backend, _, calls, _ = source_seam(monkeypatch, tmp_path, fail_after=fail_after)
    result, ledger = _run_counted(lambda: run_r2(tmp_path), backend, "_step", tmp_path / "ledger.json", {"operation": "build"})
    if fail_after is None:
        assert ledger["attempted"] == ledger["completed"] == ledger["actual_control_steps"] == 189
        assert result["complete"]
    else:
        assert ledger["attempted"] == 163 and ledger["completed"] == 162
        assert ledger["actual_control_steps"] is None and ledger["count_status"] == "partial_unknown"
        assert result["complete"] is False
    assert ledger["hook_restored"]


def test_r2_converged_source_roundtrips_real_file_candidate_acceptance(monkeypatch, tmp_path):
    from benchmark.remaining_goals.validation import validate_candidate, RGB_QUANTIZATION_AUDIT
    from benchmark.remaining_goals.nine_catalog import read_goal_facts
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.headless.scoped_sources import inspect_candidate
    backend, _, _, _ = source_seam(monkeypatch, tmp_path)
    def observation(state):
        return {"agentview_image": np.full((2, 2, 3), 10, np.uint8), "robot0_joint_pos": state[1:2].copy()}
    class Audit:
        def __init__(self, state, semantics): self.start, self.semantics = state.copy(), semantics
        def restore_candidate(self, episode):
            self.state = self.start.copy()
            return observation(self.state)
        def step(self, action):
            self.state[0] += .05
            return observation(self.state)
        def validation_snapshot(self):
            return {"state": self.state.copy(), "state_before_refresh": self.state.copy(), "qvel": self.state[10:],
                "robot_qpos": self.state[1:2], "object_positions": {"mug": self.state[3:6]}, "penetrations": [],
                "fresh_observation": observation(self.state),
                **read_goal_facts(lambda p: p[0] in ("in", "open"), False, self.semantics)}
    def audit(env, state, episode, output, relative, **options):
        result = validate_candidate(Audit(state, episode["task_semantics"]), episode, steps=options["validation_steps"],
            hold_action=HOLD, **RGB_QUANTIZATION_AUDIT)
        episode["initial_observation"] = save_observation_artifact(output, str(relative / "initial_observation.npz"), observation(state))
        result["initial_observation"] = episode["initial_observation"]
        _write(output / relative / "audit.json", result)
        return {"technical_acceptance": result["technical_acceptance"]}
    backend._audit_state = audit
    result = run_r2(tmp_path)
    assert result["complete"], result
    candidate = inspect_candidate(TASK, 0, tmp_path / "output/manifest.candidates.json", protocol="nine-mask10")
    assert candidate["episode"]["construction"]["method"] == R2_METHOD
    assert candidate["construction"]["steps"] == 150
