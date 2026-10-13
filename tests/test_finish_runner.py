"""Synthetic CPU FINISH protocol tests, not model or physical validation."""
from copy import deepcopy
import math

import numpy as np
import pytest

from benchmark.remaining_goals.finish.runner import run_finish_episode
from benchmark.remaining_goals.finish.schema import (FEATURE_VERSION, INPUT_SCHEMA, POLICY_SCHEMA,
    validate_finish_result, validate_policy_result, validate_input_evidence, input_sha256)
from benchmark.remaining_goals.runner import run_episode


def episode(mask=None):
    return {"episode_id": "synthetic_finish", "task_id": "synthetic", "suite": "synthetic",
            "task_name": "synthetic basket", "instruction": "put both original objects in the basket",
            "initial_mask": [False, False] if mask is None else mask, "seed": 7,
            "state_sha256": "a" * 64, "horizon": 9, "retention_steps": 2,
            "goal_specs": [{"id": "a", "predicates": [["in", "a", "basket"]]},
                           {"id": "b", "predicates": [["in", "b", "basket"]]}]}


def observation(step):
    return {"agentview_image": np.full((4, 5, 3), step % 256, np.uint8),
            "robot0_eye_in_hand_image": np.full((3, 6, 3), (step + 10) % 256, np.uint8),
            "proprio": np.array([step, -0., 0, 0, 0, 0, 0], dtype=np.float32)}


def inputs(step=0):
    return {"schema_version": INPUT_SCHEMA,
            "tensors": {"input_ids": np.array([[1, 3, 7]], np.int64),
                        "attention_mask": np.ones((1, 3), np.int64),
                        "pixel_values": np.full((1, 6, 2, 2), step / 100, np.float32),
                        "proprio": np.full(7, step, np.float64)},
            "tensor_dtypes": {"input_ids": "torch.int64", "attention_mask": "torch.int64",
                              "pixel_values": "torch.float32", "proprio": "numpy.float64"},
            "crops": {"agentview": np.full((2, 3, 3), step % 256, np.uint8),
                      "wrist": np.full((3, 2, 3), (step + 20) % 256, np.uint8)}}


def envelope(finish=False, step=0):
    logit = 4.0 if finish else -4.0
    return {"schema_version": POLICY_SCHEMA, "candidate_actions": np.arange(56, dtype=float).reshape(8, 7) / 100 + step,
            "logit": logit, "p": 1 / (1 + math.exp(-logit)), "threshold": .5,
            "head_decision": "finish" if finish else "continue",
            "head_identity": {"artifact_sha256": "b" * 64, "base_identity_sha256": "c" * 64,
                              "feature_version": FEATURE_VERSION}, "input_evidence": inputs(step)}


class Env:
    def __init__(self, *, fail_step=None, fail_evaluator=None, fail_hold=False, wrong_initial=False):
        self.steps = self.resets = self.holds = self.begins = self.evaluations = 0
        self.actions = []
        self.fail_step, self.fail_evaluator = fail_step, fail_evaluator
        self.fail_hold, self.wrong_initial = fail_hold, wrong_initial

    def reset(self, ep):
        self.resets += 1
        self.mask = deepcopy(ep["initial_mask"])
        return observation(0)

    def evaluator_state(self):
        self.evaluations += 1
        if self.steps == self.fail_evaluator:
            raise RuntimeError("synthetic evaluator failure")
        goals = [True, True] if self.wrong_initial else self.mask
        return {"goals": deepcopy(goals), "released": True, "objects": {
            "a": {"role": "target", "in_basket": goals[0], "released": True,
                  "release_evidence": {"method": "synthetic_no_contact"}},
            "b": {"role": "target", "in_basket": goals[1], "released": True,
                  "release_evidence": {"method": "synthetic_no_contact"}}}}

    def goal_values(self):
        return self.mask

    def step(self, action):
        if self.steps + 1 == self.fail_step:
            raise RuntimeError("synthetic step failure")
        self.steps += 1
        self.actions.append(action.copy())
        return observation(self.steps)

    def begin_hold(self):
        self.begins += 1
        return {"version": "synthetic-only", "gripper": "unchanged", "pose": "latched"}

    def hold_action(self):
        self.holds += 1
        if self.fail_hold:
            raise RuntimeError("synthetic hold failure")
        return np.array([0, 0, 0, 0, 0, 0, .25], dtype=float)


class Policy:
    def __init__(self, finish_at=None, invalid=None, fail_query=None):
        self.finish_at, self.invalid, self.fail_query = finish_at, invalid, fail_query
        self.calls, self.resets, self.inputs = 0, 0, []

    def reset(self):
        self.resets += 1

    def predict(self, obs, instruction):
        self.calls += 1
        self.inputs.append((deepcopy(obs), instruction))
        if self.calls == self.fail_query:
            raise RuntimeError("synthetic model failure")
        step = int(obs["proprio"][0])
        result = envelope(self.finish_at is not None and step >= self.finish_at, step)
        return self.invalid(result) if self.invalid else result


def run(env=None, policy=None, ep=None, **kwargs):
    env, policy, ep = env or Env(), policy or Policy(), ep or episode()
    result = run_finish_episode(env, policy, ep, horizon=kwargs.pop("horizon", 9),
                                retention_steps=kwargs.pop("retention_steps", 2), **kwargs)
    return env, policy, ep, result


@pytest.mark.parametrize("mask", [[False, False], [True, False], [False, True], [True, True]])
def test_t0_finish_holds_even_when_truth_says_incomplete(mask):
    env, policy, ep, result = run(policy=Policy(finish_at=0), ep=episode(mask))
    assert result["status"] == "completed" and result["finish_step"] == 0
    assert result["timeout_step"] is None and result["exit_reason"] == "finish"
    assert policy.calls == 1 and env.begins == 1 and env.holds == env.steps == 2
    assert [row["step"] for row in result["trace"]] == [0, 1, 2]
    assert result["queries"][0]["accepted_chunk_length"] == 0
    assert all(row["hold_cause"] == "finish" for row in result["executed_actions"])
    assert validate_finish_result(result, ep)["verified"]


@pytest.mark.parametrize("mode,finish,reason", [("active", 9, "finish"), ("active", None, "timeout"), ("shadow", 0, "timeout")])
def test_horizon_query_precedence_and_nondivisible_chunk(mode, finish, reason):
    env, policy, ep, result = run(mode=mode, policy=Policy(finish_at=finish))
    assert result["status"] == "completed" and result["exit_reason"] == reason
    assert [q["observation_step"] for q in result["queries"]] == [0, 8, 9]
    assert [q["accepted_chunk_length"] for q in result["queries"]] == [8, 1, 0]
    assert policy.calls == 3 and env.steps == 11 and env.holds == 2
    assert result["queries"][-1]["candidate_actions"] and not result["queries"][-1]["executed_steps"]
    assert all(event["hold_cause"] == reason for event in result["executed_actions"][-2:])
    assert validate_finish_result(result, ep)["verified"]


def test_shadow_never_applies_high_finish_and_preserves_candidate_prefix():
    env, policy, ep, result = run(mode="shadow", policy=Policy(finish_at=0), max_chunk_steps=4)
    assert [q["observation_step"] for q in result["queries"]] == [0, 4, 8, 9]
    assert [q["head_decision"] for q in result["queries"]] == ["finish"] * 4
    assert [q["applied_decision"] for q in result["queries"]] == ["continue"] * 3 + ["timeout"]
    expected = np.vstack([envelope(True, step)["candidate_actions"][:count] for step, count in [(0, 4), (4, 4), (8, 1)]])
    np.testing.assert_array_equal(np.array(env.actions[:9]), expected)
    assert result["finish_step"] is None
    assert validate_finish_result(result, ep)["verified"]


def test_terminal_mask_gets_full_h_budget_and_gt_never_reaches_policy():
    left = run(ep=episode([False, False]))
    right = run(ep=episode([True, True]))
    assert left[3]["n_steps"] == right[3]["n_steps"] == 11
    assert len(left[1].inputs) == len(right[1].inputs) == 3
    for (a, instruction_a), (b, instruction_b) in zip(left[1].inputs, right[1].inputs):
        assert instruction_a == instruction_b == episode()["instruction"]
        assert set(a) == set(observation(0))
        for key in a:
            np.testing.assert_array_equal(a[key], b[key])


@pytest.mark.parametrize("change", [
    lambda x: None, lambda x: x["candidate_actions"],
    lambda x: {**x, "p": float("nan")}, lambda x: {**x, "p": 1.1},
    lambda x: {**x, "p": .5}, lambda x: {**x, "threshold": 0},
    lambda x: {**x, "head_decision": "finish"},
    lambda x: {**x, "candidate_actions": np.zeros((0, 7))},
    lambda x: {**x, "schema_version": "legacy"},
    lambda x: {**x, "head_identity": {**x["head_identity"], "feature_version": "wrong"}},
])
def test_bad_finish_envelope_is_technical_failure_without_fallback(change):
    env, policy, ep, result = run(policy=Policy(invalid=change))
    assert result["status"] == "runtime_error" and result["error_phase"] == "validate_policy_result"
    assert env.steps == env.holds == env.begins == 0 and policy.calls == 1
    assert validate_finish_result(result, ep)["verified"]


@pytest.mark.parametrize("env,policy,phase,steps,queries", [
    (Env(fail_step=2), Policy(), "policy_step", 1, 1),
    (Env(fail_evaluator=1), Policy(), "evaluator_state", 1, 1),
    (Env(fail_hold=True), Policy(finish_at=0), "hold_action", 0, 1),
    (Env(), Policy(fail_query=2), "policy_predict", 8, 2),
])
def test_partial_error_ledgers_keep_real_actions(env, policy, phase, steps, queries):
    _, _, ep, result = run(env=env, policy=policy)
    assert result["status"] == "runtime_error" and result["error_phase"] == phase
    assert result["n_steps"] == len(result["executed_actions"]) == steps
    assert result["policy_queries"] == queries
    assert validate_finish_result(result, ep)["verified"]


def test_initial_mismatch_never_queries_and_missing_hold_fails_before_reset():
    env, policy, _, result = run(env=Env(wrong_initial=True))
    assert result["status"] == "runtime_error" and policy.calls == 0
    env = Env()
    env.begin_hold = None
    _, policy, _, result = run(env=env)
    assert result["status"] == "runtime_error" and env.resets == policy.calls == 0


def test_h0_still_queries_and_hold_unknown_is_not_inferred_released():
    env = Env()
    original = env.evaluator_state
    def unknown():
        truth = original()
        truth["released"] = None
        return truth
    env.evaluator_state = unknown
    _, policy, ep, result = run(env=env, horizon=0)
    assert policy.calls == 1 and result["timeout_step"] == 0 and result["n_steps"] == 2
    assert all(row["released"] is None for row in result["trace"])
    assert validate_finish_result(result, ep)["verified"]


@pytest.mark.parametrize("payload", [[], {"status": "saved", "bad": np.ones(1)}, {"status": "video_error", "path": None}])
def test_video_failure_is_explicit_technical_error_not_score_success(payload):
    class Recorder:
        def capture(self, obs, *, step):
            pass
        def close(self):
            return payload
    _, _, ep, result = run(policy=Policy(finish_at=0), recorder=Recorder())
    assert result["status"] == "runtime_error" and result["error_phase"] == "video_finalize"
    assert result["n_steps"] == 2
    assert validate_finish_result(result, ep)["verified"]


def test_captured_last_frame_exists_when_evaluator_fails():
    class Recorder:
        def __init__(self):
            self.steps = []
        def capture(self, obs, *, step):
            self.steps.append(step)
        def close(self):
            return {"status": "saved", "path": "synthetic.mp4"}
    recorder = Recorder()
    _, _, _, result = run(env=Env(fail_evaluator=1), recorder=recorder)
    assert recorder.steps == [0, 1] and result["n_steps"] == 1


def test_legacy_runner_keeps_legacy_schema_and_terminal_budget():
    class LegacyPolicy(Policy):
        def predict(self, obs, instruction):
            self.calls += 1
            return np.zeros((8, 7))
    result = run_episode(Env(), LegacyPolicy(), episode([True, True]))
    assert result["n_steps"] == 2 and "schema_version" not in result and "queries" not in result
    with pytest.raises(ValueError, match="legacy"):
        validate_finish_result(result)


def test_bf16_bits_and_dtype_are_preserved_and_illegal_fields_rejected():
    value = inputs()
    value["tensors"]["pixel_values"] = np.full((1, 6, 2, 2), 0x3F80, dtype=np.uint16)
    value["tensor_dtypes"]["pixel_values"] = "torch.bfloat16"
    checked = validate_input_evidence(value)
    np.testing.assert_array_equal(checked["tensors"]["pixel_values"], value["tensors"]["pixel_values"])
    first = input_sha256(value)
    value["tensor_dtypes"]["pixel_values"] = "numpy.uint16"
    assert input_sha256(value) != first
    value["tensors"]["goals"] = np.ones(2)
    with pytest.raises(ValueError, match="four model tensors"):
        validate_input_evidence(value)


def test_bf16_nonfinite_and_wrong_dtype_rejected():
    value = inputs()
    value["tensors"]["pixel_values"] = np.full((1, 6, 2, 2), 0x7FC0, dtype=np.uint16)
    value["tensor_dtypes"]["pixel_values"] = "torch.bfloat16"
    with pytest.raises(ValueError, match="NaN"):
        validate_input_evidence(value)
    value = envelope()
    value["input_evidence"]["tensor_dtypes"]["proprio"] = "numpy.float32"
    with pytest.raises(ValueError, match="bytes"):
        validate_policy_result(value)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(timeout_step=None, finish_step=9, exit_reason="finish"),
    lambda r: r["queries"][-1].update(applied_decision="continue"),
    lambda r: r["executed_actions"][-1].update(hold_cause="finish"),
    lambda r: r["queries"][1].update(observation_step=7),
    lambda r: r["queries"][0]["accepted_actions"][0].__setitem__(0, 999),
])
def test_rescore_rejects_deadline_and_action_relabeling(mutate):
    _, _, ep, result = run()
    mutate(result)
    with pytest.raises(ValueError):
        validate_finish_result(result, ep)


def test_completed_result_cannot_relabel_initial_mask_or_boolean_exit_step():
    _, _, ep, result = run(policy=Policy(finish_at=0))
    changed = deepcopy(result)
    changed["trace"][0]["goals"] = [True, True]
    with pytest.raises(ValueError, match="initial goal mask"):
        validate_finish_result(changed, ep)
    result["finish_step"] = False
    with pytest.raises(ValueError, match="integer"):
        validate_finish_result(result, ep)
