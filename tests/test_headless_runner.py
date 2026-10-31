"""CPU protocol tests. Synthetic facts do not certify native event geometry."""
from copy import deepcopy
import json
import math
import random
import sys
from types import ModuleType

import numpy as np
import pytest

from benchmark.remaining_goals.headless.runner import run_episode
from benchmark.remaining_goals.headless.schema import validate_result, EVENTS, canonical_hash
from benchmark.remaining_goals.headless.metrics import score_episode, summarize, render_report
from benchmark.remaining_goals.headless.evidence import HeadlessEvidence, validate_evidence


@pytest.fixture(autouse=True)
def synthetic_measurement_validator(monkeypatch):
    """Only physical truth production is fake; runner/schema/file checks are real."""
    module = ModuleType("benchmark.remaining_goals.headless.environment")
    def static(value, episode=None):
        assert value["synthetic"] is True
        if episode is not None and value["model_xml_sha256"] != episode["model_xml_sha256"]:
            raise ValueError("synthetic static source differs")
        return deepcopy(value)
    module.validate_measurement_static = static
    module.validate_evaluator_evidence = lambda facts, frozen: deepcopy(facts)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def episode(**changes):
    value = {"episode_id": "basket_s000_10", "task_id": "basket", "suite": "libero_10",
             "instruction": "put both original objects in the basket", "initial_mask": [True, False],
             "initial_state_index": 0, "seed": 0, "state_sha256": "a" * 64,
             "model_xml_sha256": "b" * 64, "bddl_sha256": "c" * 64}
    value.update(changes)
    return value


def observation(step):
    return {"agentview_image": np.full((2, 3, 3), step, np.uint8),
            "robot0_eye_in_hand_image": np.full((3, 2, 3), step + 5, np.uint8),
            "proprio": np.array([step, -0., 0, 0, 0, 0, .01, -.01], np.float64)}


class Env:
    def __init__(self, *, complete=2, regression=(), candidate=None, release=None, tcp=None, fail=None, initial=None):
        self.complete, self.regression, self.candidate = complete, regression, candidate
        self.release, self.tcp, self.fail, self.initial = release, tcp, fail, initial
        self.steps, self.actions, self.reads = 0, [], 0

    def reset(self, ep):
        self.ep, self.steps = deepcopy(ep), 0
        return observation(0)

    def measurement_static(self):
        return {"synthetic": True, "model_xml_sha256": self.ep["model_xml_sha256"]}

    def evaluator_state(self):
        self.reads += 1
        if self.fail == ("evaluator", self.steps):
            raise RuntimeError("synthetic measurement field missing")
        goals = [self.steps not in self.regression, self.complete is not None and self.steps >= self.complete]
        if self.steps == 0 and self.initial is not None:
            goals = self.initial
        released = self.release(self.steps) if self.release else True
        position = self.tcp(self.steps) if self.tcp else [self.steps / 10, 0., 0.]
        events = {kind: {"extra": self.candidate(kind, self.steps) if self.candidate else False} for kind in EVENTS}
        return {"goals": goals, "released": released,
            "tcp": {"site_id": 7, "site_name": "robot0_tcp", "frame": "world", "position": position},
            "objects": {"target": {"role": "target", "position": [1., 0., 0.], "released": released, "release_evidence": {"synthetic": True}},
                        "extra": {"role": "distractor", "position": [0., 0., 1.], "released": True, "release_evidence": {"synthetic": True}}},
            "event_candidates": events,
            "event_evidence": {kind: {"extra": {"synthetic": True, "observed_step": self.steps}} for kind in EVENTS}}

    def step(self, action):
        if self.fail == ("step", self.steps + 1):
            raise RuntimeError("synthetic control failure")
        if self.fail == ("interrupt", self.steps + 1):
            raise KeyboardInterrupt("synthetic interruption")
        self.actions.append(action.copy())
        self.steps += 1
        return observation(self.steps)

    def begin_hold(self):
        pytest.fail("headless must not begin W150 or open gripper")

    def hold_action(self):
        pytest.fail("headless has no scripted hold")


class Policy:
    def __init__(self, result=None, *, fail=False):
        self.calls, self.resets, self.inputs = 0, 0, []
        self.result, self.fail = result, fail

    def reset(self):
        self.resets += 1

    def predict(self, observation, instruction):
        self.calls += 1
        self.inputs.append((deepcopy(observation), instruction))
        if self.fail:
            raise RuntimeError("synthetic worker error")
        if self.result is not None:
            return self.result()
        actions = np.arange(56, dtype=np.float64).reshape(8, 7) / 100
        actions[:, 1] = -0.
        return actions


class Video:
    def __init__(self, fail=None):
        self.frames, self.closed, self.fail = [], 0, fail

    def capture(self, observation, *, step):
        self.frames.append((step, deepcopy(observation)))
        if self.fail == ("capture", step):
            raise OSError("synthetic encoder capture failure")

    def close(self):
        self.closed += 1
        if self.fail == "close":
            raise OSError("synthetic encoder finalization failure")
        return {"status": "saved", "path": "synthetic.mp4", "synthetic": True, "frame_steps": [x[0] for x in self.frames]}


def execute(env=None, policy=None, *, horizon=16, video=None, ep=None, evidence=None, identity=None):
    env, policy, ep = env or Env(), policy or Policy(), ep or episode()
    result = run_episode(env, policy, ep, horizon=horizon, recorder=video, evidence=evidence, identity=identity)
    validate_result(result, ep, identity)
    return env, policy, result


def test_middle_chunk_confirmation_has_no_extra_action_query_hold_or_frame():
    video = Video()
    before_python, before_numpy = random.getstate(), np.random.get_state()
    env, policy, result = execute(video=video)
    assert result["status"] == "completed" and result["exit_reason"] == "goal_confirmed"
    assert result["goal_completion_step"] == 2 and result["goal_confirmed_step"] == 6
    assert env.steps == result["n_steps"] == 6 and policy.calls == 1
    assert result["queries"][0]["accepted_chunk_length"] == 8
    assert result["queries"][0]["executed_steps"] == list(range(1, 7))
    assert video.closed == 1 and [x[0] for x in video.frames] == list(range(7))
    assert result["trace"][-1]["chunk_index"] == 5
    assert score_episode(episode(), result)["success"] is True
    for actual, candidate in zip(env.actions, result["queries"][0]["accepted_actions"]):
        assert actual.dtype == np.float64 and actual.tobytes() == np.asarray(candidate, np.float64).tobytes()
    assert random.getstate() == before_python
    assert np.random.get_state()[0] == before_numpy[0] and np.random.get_state()[2:] == before_numpy[2:]
    np.testing.assert_array_equal(np.random.get_state()[1], before_numpy[1])


@pytest.mark.parametrize("complete,horizon,endpoint", [(4, 8, "goal_confirmed"), (5, 8, "horizon"), (None, 8, "horizon")])
def test_horizon_inclusive_confirmation_never_queries_at_or_after_h(complete, horizon, endpoint):
    env, policy, result = execute(Env(complete=complete), horizon=horizon)
    assert result["exit_reason"] == endpoint and env.steps == 8 and policy.calls == 1
    assert len(result["trace"]) == 9


def test_unknown_release_resets_confirmation_without_becoming_false():
    _, _, result = execute(Env(release=lambda step: None if step == 4 else True))
    assert result["goal_completion_step"] == 5 and result["goal_confirmed_step"] == 9
    assert result["release_unknown_steps"] == [4]
    assert score_episode(episode(), result)["success"] is True


@pytest.mark.parametrize("kind", EVENTS)
def test_confirmed_wrong_event_remains_failure_after_event_resolves(kind):
    env = Env(complete=8, candidate=lambda candidate, step: candidate == kind and 1 <= step <= 5)
    _, _, result = execute(env)
    assert result["goal_confirmed_step"] == 12
    assert result["confirmed_events"] == [{"event": kind, "object": "extra", "start_step": 1, "confirmation_step": 5}]
    row = score_episode(episode(), result)
    assert row["classification"] == "failure" and kind in row["failure_reasons"]


def test_single_goal_a_regression_is_sticky_even_after_recovery():
    _, _, result = execute(Env(regression=[3]))
    assert result["goal_confirmed_step"] == 8 and result["goal_regression"]
    assert score_episode(episode(), result)["failure_reasons"] == ["goal_regression"]


def test_short_event_attempt_and_nonviolating_motion_do_not_fail():
    _, _, result = execute(Env(candidate=lambda kind, step: 1 <= step <= 4))
    assert result["confirmed_events"] == [] and score_episode(episode(), result)["success"]


def test_unknown_event_breaks_confirmation_but_cannot_certify_success():
    _, _, result = execute(Env(candidate=lambda kind, step: None if kind == "wrong_grasp" and step == 3 else False))
    assert result["confirmed_events"] == [] and result["goal_confirmed_step"] == 6
    row = score_episode(episode(), result)
    assert row["classification"] == "unknown" and row["success"] is None


def test_goal_endpoint_does_not_change_policy_inputs_or_returned_actions():
    _, left, a = execute(Env(candidate=lambda kind, step: kind == "wrong_grasp" and 1 <= step <= 5))
    _, right, b = execute()
    assert a["goal_confirmed_step"] == b["goal_confirmed_step"] == 6
    assert a["executed_actions"] == b["executed_actions"]
    for (obs_a, instruction_a), (obs_b, instruction_b) in zip(left.inputs, right.inputs):
        assert instruction_a == instruction_b == episode()["instruction"] and set(obs_a) == set(observation(0))
        for key in obs_a:
            assert obs_a[key].dtype == obs_b[key].dtype and obs_a[key].tobytes() == obs_b[key].tobytes()


def test_true_tcp_polyline_length_is_not_action_norm():
    points = [[0., 0., 0.], [3., 0., 0.], [3., 4., 0.], [3., 4., 12.]]
    _, _, result = execute(Env(tcp=lambda step: points[min(step, 3)]))
    assert result["path_length_m"] == 19.
    assert [row["path_increment_m"] for row in result["trace"]] == [0., 3., 4., 12., 0., 0., 0.]


@pytest.mark.parametrize("fault", ["missing_step", "site", "nan", "path", "state", "source_index", "action", "endpoint"])
def test_offline_rejects_tcp_source_action_and_endpoint_tampering(fault):
    _, _, result = execute()
    if fault == "missing_step":
        result["trace"].pop(2)
    elif fault == "site":
        result["trace"][2]["tcp"]["site_id"] = 8
    elif fault == "nan":
        result["trace"][2]["tcp"]["position"][0] = float("nan")
    elif fault == "path":
        result["path_length_m"] = 0.
    elif fault == "state":
        result["state_sha256"] = "d" * 64
    elif fault == "source_index":
        result["initial_state_index"] = 1
    elif fault == "action":
        result["executed_actions"][0]["action"][1] = 0.
    else:
        result["goal_confirmed_step"] = 5
    with pytest.raises(ValueError):
        validate_result(result, episode())


@pytest.mark.parametrize("initial", [[False, False], [True, True], [False, True]])
def test_t0_mask_is_actual_required_and_no_query_executes(initial):
    env, policy, result = execute(Env(initial=initial))
    assert result["status"] == "invalid_initial_state" and result["n_steps"] == policy.calls == env.steps == 0
    assert score_episode(episode(), result)["classification"] == "technical_error"


@pytest.mark.parametrize("policy", [lambda: Policy(lambda: None), lambda: Policy(fail=True), lambda: Policy(lambda: np.full((8, 7), np.nan))])
def test_stop_and_worker_failure_are_technical_without_hold_or_goal_success(policy):
    _, p, result = execute(policy=policy())
    assert result["status"] == "runtime_error" and result["exit_reason"] == "technical_error"
    assert result["n_steps"] == 0 and p.calls == 1 and result["goal_confirmed_step"] is None


@pytest.mark.parametrize("failure", [("step", 3), ("evaluator", 3), ("interrupt", 3)])
def test_failure_keeps_actual_prefix_and_video_uses_already_returned_frame(failure):
    video = Video()
    env, _, result = execute(Env(fail=failure), video=video)
    assert result["status"] == "runtime_error" and video.closed == 1
    assert result["n_steps"] == (3 if failure[0] == "evaluator" else 2)
    assert len(video.frames) == result["n_steps"] + 1
    assert result["path_length_m"] == .2
    assert score_episode(episode(), result)["classification"] == "technical_error"


def test_technical_label_cannot_hide_multiple_missing_physical_observations():
    from benchmark.remaining_goals.headless.schema import analyze_trace
    _, _, result = execute(Env(fail=("evaluator", 3)))
    result["trace"] = result["trace"][:1]
    result.update({key: value for key, value in analyze_trace(result["trace"]).items() if key != "frames"})
    with pytest.raises(ValueError, match="observation count"):
        validate_result(result, episode())


@pytest.mark.parametrize("fault", [("capture", 3), "close"])
def test_video_failure_does_not_claim_complete(fault):
    _, _, result = execute(video=Video(fault))
    assert result["status"] == "runtime_error" and result["exit_reason"] == "technical_error"


def test_real_input_archives_bind_run_source_queries_and_trace(tmp_path):
    identity = {"episode_id": episode()["episode_id"], "state_sha256": "a" * 64,
                "model_runtime_sha256": "f" * 64, "track": "libero_10",
                "model_identity": {"checkpoint": "synthetic-sog10", "normalization_key": "libero_10"}}
    recorder = HeadlessEvidence(tmp_path / "evidence" / "ep", identity)
    _, _, result = execute(evidence=recorder, identity=identity)
    assert validate_evidence(tmp_path, result, episode(), identity)["verified"]
    changed = deepcopy(result)
    changed["model_identity"]["normalization_key"] = "fabricated_libero_90"
    with pytest.raises(ValueError, match="model/checkpoint/normalization"):
        validate_evidence(tmp_path, changed, episode(), identity)
    reference = result["execution_evidence"]
    assert (tmp_path / "evidence/ep/initial.npz").is_file()
    assert (tmp_path / "evidence/ep/query_0001.npz").is_file()
    result["video"] = {"path": "videos/new-run-relative.mp4", "sha256": "0" * 64}
    assert validate_evidence(tmp_path, result, episode(), identity)["verified"]
    wrong_identity = {**identity, "track": "libero_90"}
    with pytest.raises(ValueError):
        validate_evidence(tmp_path, result, episode(), wrong_identity)
    path = tmp_path / "evidence/ep/query_0001.npz"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        validate_evidence(tmp_path, result, episode(), identity)


def test_fixed_100_denominator_track_task_weighting_and_no_success_path_na():
    planned = [episode(episode_id=f"task{task}_{index}", task_id=f"task{task}",
                       suite="libero_10" if task < 6 else "libero_90", initial_state_index=index, seed=index)
               for task in range(10) for index in range(10)]
    _, _, success = execute(ep=planned[0])
    _, _, failure = execute(Env(complete=None), horizon=8, ep=planned[10])
    _, _, technical = execute(policy=Policy(fail=True), ep=planned[20])
    _, _, unknown = execute(Env(candidate=lambda kind, step: None), ep=planned[30])
    report = summarize(planned, [success, failure, technical, unknown])
    assert report["counts"]["expected"] == 100
    assert report["counts"]["classification_counts"] == {"success": 1, "failure": 1, "technical_error": 1, "unknown": 1, "missing": 96}
    assert report["mixed_batch"]["success_percent"] == 1.
    assert report["tracks"][0]["expected"] == 60 and report["tracks"][1]["expected"] == 40
    assert math.isclose(report["tracks"][0]["success_percent"], 100 / 60)
    assert report["tracks"][1]["success_conditional_mean_path_m"] is None
    assert report["tasks"][0]["success_conditional_mean_path_m"] == success["path_length_m"]
    assert report["tasks"][1]["success_conditional_mean_path_m"] is None
    rendered = render_report(report)
    assert "N/A" in rendered and "Equal-task summaries" in rendered
    assert "Mixed batch (descriptive)" in rendered and "| 1/6 | 1/60 |" in rendered
    assert "Official goals achieved" in rendered and "goal_not_confirmed_by_horizon: 1" in rendered
    assert "event_evidence_unknown: 1" in rendered
    minimal = [{key: row[key] for key in ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")} for row in planned]
    assert summarize(minimal, [success, failure, technical, unknown])["counts"] == report["counts"]


@pytest.mark.parametrize("method", ["begin_episode", "capture_initial", "capture_query_input", "finish"])
def test_evidence_failure_preserves_partial_without_claiming_verified(tmp_path, monkeypatch, method):
    identity = {"episode_id": episode()["episode_id"], "state_sha256": "a" * 64}
    recorder = HeadlessEvidence(tmp_path / "evidence" / "ep", identity)
    def failure(*args, **kwargs):
        raise OSError("synthetic evidence filesystem error")
    monkeypatch.setattr(recorder, method, failure)
    video = Video()
    _, _, result = execute(evidence=recorder, identity=identity, video=video)
    assert result["status"] == "runtime_error" and result["error_phase"].startswith("evidence")
    report = validate_evidence(tmp_path, result, episode(), identity)
    assert report["verified"] is False and report["status"] == "evidence_error"
    assert video.closed == 1
