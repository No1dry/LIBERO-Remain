"""Contract tests for physical rollout, privilege boundaries, and failures."""

from copy import deepcopy
import json

import numpy as np
import pytest

from benchmark.remaining_goals.runner import run_episode


def episode(mask=(True, False), horizon=3, retention=2, **extra):
    return {
        "episode_id": "test-10", "task_id": "two-goals", "suite": "test",
        "task_name": "test", "instruction": "put A and B into their containers",
        "goal_specs": [{"id": "A", "language": "put A", "predicates": []},
                       {"id": "B", "language": "put B", "predicates": []}],
        "initial_mask": list(mask), "horizon": horizon,
        "retention_steps": retention, "seed": 3, **extra,
    }


class FakeEnv:
    def __init__(self, initial=None, schedule=None):
        self.initial = initial
        self.schedule = schedule or {}
        self.actions = []
        self.hold_calls = 0
        self.goal_calls = 0
        self.done = False

    def observation(self):
        return {"images": {"front": np.zeros((2, 2, 3), dtype=np.uint8)},
                "proprio": np.array([len(self.actions)], dtype=float)}

    def reset(self, spec):
        self.actions = []
        self.hold_calls = 0
        self.done = False
        self.goals = list(self.initial if self.initial is not None else spec["initial_mask"])
        return self.observation()

    def goal_values(self):
        self.goal_calls += 1
        return list(self.goals)

    def step(self, action):
        self.actions.append(action.copy())
        self.goals = list(self.schedule.get(len(self.actions), self.goals))
        self.done = all(self.goals)
        return self.observation()

    def hold_action(self):
        self.hold_calls += 1
        return np.array([0, 0, 0, 0, 0, 0, -0.5], dtype=float)


class FakePolicy:
    def __init__(self, predictions=None):
        self.predictions = predictions if predictions is not None else [np.ones(7)]
        self.calls = []
        self.resets = 0

    def reset(self):
        self.resets += 1
        self.calls = []

    def predict(self, obs, instruction):
        self.calls.append((deepcopy(obs), instruction))
        index = min(len(self.calls) - 1, len(self.predictions) - 1)
        value = self.predictions[index]
        if isinstance(value, Exception):
            raise value
        return value


def test_goal_success_and_env_done_do_not_stop_execution():
    env = FakeEnv(schedule={1: [True, True], 4: [True, False]})
    policy = FakePolicy()
    result = run_episode(env, policy, episode())
    assert result["status"] == "completed"
    assert result["n_steps"] == 5
    assert result["policy_queries"] == 5
    assert [row["step"] for row in result["trace"]] == list(range(6))
    assert result["trace"][1]["goals"] == [True, True]
    assert result["trace"][-1]["goals"] == [True, False]
    assert result["trace"][0]["action"] is None
    assert not any(row["stopped"] for row in result["trace"])
    assert "success" not in result
    json.dumps(result, allow_nan=False)


def test_initially_satisfied_still_queries_and_runs_exact_retention_window():
    env = FakeEnv(schedule={1: [False, True]})
    result = run_episode(env, FakePolicy(), episode(mask=(True, True), horizon=99, retention=3))
    assert result["status"] == "completed"
    assert result["n_steps"] == 3
    assert result["policy_queries"] == 3
    assert result["trace"][-1]["goals"] == [False, True]


def test_first_success_after_horizon_is_retained_without_inventing_success():
    result = run_episode(FakeEnv(schedule={4: [True, True]}), FakePolicy(), episode())
    assert result["status"] == "completed"
    assert result["trace"][result["horizon"]]["goals"] == [True, False]
    assert result["trace"][4]["goals"] == [True, True]
    assert result["n_steps"] == 5
    assert "success" not in result


def test_stop_runs_dynamic_hold_every_step_instead_of_freezing():
    class DynamicHoldEnv(FakeEnv):
        def hold_action(self):
            self.hold_calls += 1
            return np.full(7, self.hold_calls / 10)

    env = DynamicHoldEnv(schedule={2: [False, False]})
    result = run_episode(env, FakePolicy([None]), episode())
    assert result["status"] == "completed"
    assert result["stop_step"] == 0
    assert result["policy_queries"] == 1
    assert result["n_steps"] == env.hold_calls == 5
    assert result["trace"][2]["goals"] == [False, False]
    assert not result["trace"][0]["stopped"]
    assert all(row["stopped"] for row in result["trace"][1:])
    np.testing.assert_allclose(np.array(env.actions)[:, 0], [.1, .2, .3, .4, .5])


def test_stop_decision_boundary_precedes_first_hold_transition():
    env = FakeEnv(schedule={2: [True, True]})
    result = run_episode(env, FakePolicy([np.ones(7), None]), episode())
    assert result["stop_step"] == 1
    assert result["trace"][1]["goals"] == [True, False]
    assert result["trace"][2]["goals"] == [True, True]
    assert result["policy_queries"] == 2


def test_action_chunks_are_truncated_and_requery_uses_latest_observation():
    chunk = np.stack([np.full(7, n) for n in (1, 2, 99)])
    env, policy = FakeEnv(), FakePolicy([chunk])
    result = run_episode(env, policy, episode(), max_chunk_steps=2)
    assert result["status"] == "completed"
    assert result["policy_queries"] == 3
    assert [a[0] for a in env.actions] == [1, 2, 1, 2, 1]
    assert [call[0]["proprio"][0] for call in policy.calls] == [0, 2, 4]


def test_unconsumed_chunks_do_not_cross_episode_boundary():
    class ChangingPolicy(FakePolicy):
        def predict(self, obs, instruction):
            self.calls.append((obs, instruction))
            return np.full((8, 7), self.resets)

    env, policy = FakeEnv(), ChangingPolicy()
    first = run_episode(env, policy, episode(horizon=1, retention=0))
    second = run_episode(env, policy, episode(horizon=1, retention=0, episode_id="next"))
    assert first["trace"][1]["action"] == [1.] * 7
    assert second["trace"][1]["action"] == [2.] * 7
    assert policy.resets == 2


def test_initial_mask_mismatch_is_invalid_and_never_queries_policy():
    env, policy = FakeEnv(initial=[False, False]), FakePolicy()
    result = run_episode(env, policy, episode())
    assert result["status"] == "invalid_initial_state"
    assert result["n_steps"] == result["policy_queries"] == 0
    assert policy.resets == 0
    assert len(result["trace"]) == 1
    assert "expected" in result["error"]


def test_policy_receives_no_episode_metadata():
    env, policy = FakeEnv(), FakePolicy()
    spec = episode(source_path="secret-10-state.npz", metadata={"mask": [1, 0]})
    run_episode(env, policy, spec)
    for obs, instruction in policy.calls:
        assert set(obs) == {"images", "proprio"}
        assert instruction == spec["instruction"]
        assert set(obs["images"]) == {"front"}


def test_inplace_policy_preprocessing_cannot_mutate_environment_buffers():
    class BufferedEnv(FakeEnv):
        pixels = np.zeros((2, 2, 3), dtype=np.uint8)
        proprio = np.zeros(2)

        def observation(self):
            return {"images": {"front": self.pixels}, "proprio": self.proprio}

        def step(self, action):
            assert not self.pixels.any()
            assert not self.proprio.any()
            return super().step(action)

    class MutatingPolicy(FakePolicy):
        def predict(self, obs, instruction):
            obs["images"]["front"][:] = 255
            obs["proprio"][:] = 999
            return np.zeros(7)

    result = run_episode(BufferedEnv(), MutatingPolicy(), episode())
    assert result["status"] == "completed"


def test_post_step_privileged_observation_stops_before_another_policy_query():
    class LeakingEnv(FakeEnv):
        def observation(self):
            obs = super().observation()
            if self.actions:
                obs["goals"] = [True, False]
            return obs

    result = run_episode(LeakingEnv(), FakePolicy(), episode())
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == "observation"
    assert result["n_steps"] == result["policy_queries"] == 1
    assert len(result["trace"]) == 2


def test_action_trace_preserves_command_if_environment_mutates_input():
    class MutatingEnv(FakeEnv):
        def step(self, action):
            action[:] = 99
            return super().step(action)

    result = run_episode(MutatingEnv(), FakePolicy(), episode())
    assert result["status"] == "completed"
    assert all(row["action"] == [1.] * 7 for row in result["trace"][1:])


@pytest.mark.parametrize("extra", [
    {"initial_mask": [True, False]}, {"goals": [True, False]},
    {"info": {"success": True}}, {"episode_id": "test-10"},
    {"state": {"mask": [True, False]}},
    {"images": {"mask": {"A": True}}},
    {"proprio": np.array([np.nan])},
])
def test_privileged_or_malformed_observations_are_not_forwarded(extra):
    class BadObservationEnv(FakeEnv):
        def observation(self):
            return {**super().observation(), **extra}

    policy = FakePolicy()
    result = run_episode(BadObservationEnv(), policy, episode())
    assert result["status"] == "runtime_error"
    assert result["policy_queries"] == 0
    assert not policy.calls


def test_native_libero_observation_keys_are_accepted():
    class NativeEnv(FakeEnv):
        def observation(self):
            return {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8),
                    "robot0_eye_in_hand_image": np.zeros((2, 2, 3), dtype=np.uint8),
                    "robot0_eef_pos": np.zeros(3), "robot0_eef_quat": np.zeros(4),
                    "robot0_gripper_qpos": np.zeros(2), "robot0_joint_pos": np.zeros(7),
                    "robot0_joint_vel": np.zeros(7)}

    assert run_episode(NativeEnv(), FakePolicy(), episode())["status"] == "completed"


@pytest.mark.parametrize("action", [
    np.zeros(6), np.zeros((2, 8)), np.zeros((0, 7)), np.zeros((1, 1, 7)),
    np.full(7, np.nan), np.full(7, np.inf), np.array(["0"] * 7),
    np.ones(7, dtype=complex), np.zeros(7, dtype=bool), {"action": [0] * 7},
    np.array([[0.] * 7, [np.nan] * 7]),
])
def test_bad_actions_are_runtime_errors_not_stop_or_success(action):
    result = run_episode(FakeEnv(), FakePolicy([action]), episode(), max_chunk_steps=1)
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == "validate_action"
    assert result["n_steps"] == 0
    assert result["policy_queries"] == 1
    assert result["stop_step"] is None


@pytest.mark.parametrize("hold", [None, lambda: np.zeros(6), lambda: np.full(7, np.nan)])
def test_stop_requires_explicit_valid_hold_implementation(hold):
    env = FakeEnv()
    env.hold_action = hold
    result = run_episode(env, FakePolicy([None]), episode())
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == "hold_action"
    assert result["n_steps"] == 0
    assert result["stop_step"] == 0


def test_prediction_exception_preserves_completed_physical_steps():
    result = run_episode(FakeEnv(), FakePolicy([np.ones(7), RuntimeError("model failed")]), episode())
    assert result["status"] == "runtime_error"
    assert result["policy_queries"] == 2
    assert result["n_steps"] == 1
    assert len(result["trace"]) == 2
    assert "model failed" in result["error"]


def test_policy_reset_exception_is_recorded_without_executing():
    class FailingResetPolicy(FakePolicy):
        def reset(self):
            raise RuntimeError("reset failed")

    result = run_episode(FakeEnv(), FailingResetPolicy(), episode())
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == "policy_reset"
    assert result["n_steps"] == result["policy_queries"] == 0
    assert len(result["trace"]) == 1


@pytest.mark.parametrize("method, phase, steps", [
    ("reset", "env_reset", 0), ("step", "env_step", 0),
    ("goal_values", "initial_goals", 0),
])
def test_environment_errors_return_explicit_failure(method, phase, steps):
    env = FakeEnv()

    def fail(*args):
        raise RuntimeError("environment failure")

    setattr(env, method, fail)
    result = run_episode(env, FakePolicy(), episode())
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == phase
    assert result["n_steps"] == steps
    assert "environment failure" in result["error"]


def test_failed_post_step_goal_read_reports_physical_step_without_fabricating_trace():
    class FailingGoalsEnv(FakeEnv):
        def goal_values(self):
            if self.actions:
                raise RuntimeError("predicate failed")
            return super().goal_values()

    result = run_episode(FailingGoalsEnv(), FakePolicy(), episode())
    assert result["status"] == "runtime_error"
    assert result["n_steps"] == 1
    assert len(result["trace"]) == 1
    assert result["error_phase"] == "goal_values"


@pytest.mark.parametrize("mask", [[1, 0], [True], [True, False, False], [[True, False]]])
def test_initial_mask_requires_exact_boolean_vector(mask):
    result = run_episode(FakeEnv(), FakePolicy(), episode(initial_mask=mask))
    assert result["status"] == "runtime_error"
    assert result["policy_queries"] == 0


@pytest.mark.parametrize("changes, chunk", [
    ({"horizon": -1}, 8), ({"retention_steps": -1}, 8),
    ({"horizon": 1.5}, 8), ({"horizon": True}, 8),
    ({}, 0), ({}, -1), ({}, 2.5), ({}, True),
])
def test_invalid_budgets_are_rejected(changes, chunk):
    result = run_episode(FakeEnv(), FakePolicy(), episode(**changes), max_chunk_steps=chunk)
    assert result["status"] == "runtime_error"
    assert result["error_phase"] == "validate_episode"


def test_zero_window_records_step_zero_without_querying_policy():
    result = run_episode(FakeEnv(), FakePolicy(), episode(mask=(True, True), retention=0))
    assert result["status"] == "completed"
    assert result["n_steps"] == result["policy_queries"] == 0
    assert len(result["trace"]) == 1
