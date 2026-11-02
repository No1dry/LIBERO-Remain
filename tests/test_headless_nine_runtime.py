"""Nine-task runtime endpoints and evaluator-only semantic facts, using CPU fakes."""
from copy import deepcopy

import pytest

from benchmark.remaining_goals.headless import runner, schema
from benchmark.remaining_goals.headless.protocols import get_protocol
from tests.test_headless_runner import Env, Policy, Video, episode
from tests.test_headless_normal00_runtime import synthetic_measurements


@pytest.mark.parametrize("key", ["nine-normal00", "nine-mask10"])
def test_nine_protocols_are_explicit_and_do_not_reinterpret_legacy(key):
    descriptor = get_protocol(key)
    assert descriptor.key == key
    assert descriptor.protocol_version != get_protocol("normal00-control").protocol_version
    assert descriptor.result_schema != get_protocol("mask10").result_schema


def source(task="two_pots", normal=True):
    from benchmark.remaining_goals.nine_catalog import get_task, episode_fields
    profile = get_task(task)
    mask = [False, False] if normal else [True, False]
    return episode(episode_id=f"{task}_s000_{'00' if normal else '10'}", task_id=task,
                   task_name=profile["name"], libero_task_id=profile["official_task_id"],
                   initial_mask=mask, **episode_fields(task))


class NineEnv(Env):
    def __init__(self, ep, *, goals=None, invariant=None, opened=None, released=True):
        super().__init__(candidate=lambda kind, step: None if kind == "table_drop" else False)
        self.ep, self.goals, self.invariant, self.opened = ep, goals, invariant, opened
        self.release_value = released

    def evaluator_state(self):
        facts = super().evaluator_state()
        semantics = self.ep["task_semantics"]
        goals = self.goals(self.steps) if self.goals else [self.steps >= 1, self.steps >= 2]
        invariants = [self.invariant(self.steps) if self.invariant else True
                      for _ in semantics["invariant_indices"]]
        official = [False] * len(semantics["official_goal_predicates"])
        for value, indices in zip(goals, semantics["active_goal_indices"]):
            for index in indices:
                official[index] = value
        for index, value in zip(semantics["invariant_indices"], invariants):
            official[index] = value
        facts.update(goals=goals, invariant_values=invariants, official_goal_values=official,
                     official_success=all(official), required_open_values=[
                         self.opened(self.steps) if self.opened else True
                         for _ in semantics["required_open_predicates"]], released=self.release_value)
        return facts


def run(env, ep, normal=True, horizon=8):
    policy, video = Policy(), Video()
    protocol = "nine-normal00" if normal else "nine-mask10"
    result = runner.run_episode(env, policy, ep, protocol=protocol, horizon=horizon, recorder=video)
    schema.validate_protocol_result(result, ep, protocol=protocol)
    return policy, video, result


def test_nine00_stops_at_native_success_without_release_or_drop_gate():
    ep = source()
    env = NineEnv(ep, released=None)
    policy, video, result = run(env, ep)
    assert result["status"] == "completed" and result["exit_reason"] == "official_success"
    assert result["n_steps"] == 2 and result["official_goals_achieved"] is True
    assert result["goal_regression"] is None and result["preservation_applicable"] is False
    assert env.steps == 2 and len(video.frames) == 3 and policy.calls == 1
    assert set(policy.inputs[0][0]) == {"agentview_image", "robot0_eye_in_hand_image", "proprio"}


def test_two_pots_official_success_retains_stove_invariant():
    ep = source()
    _, _, result = run(NineEnv(ep, invariant=lambda step: step == 0), ep)
    assert result["exit_reason"] == "horizon" and result["official_goals_achieved"] is False
    assert result["trace"][-1]["goals"] == [True, True]
    assert result["trace"][-1]["invariant_values"] == [False]


def test_nine10_preserves_invariant_and_original_five_observation_endpoint():
    ep = source(normal=False)
    _, _, result = run(NineEnv(ep, goals=lambda step: [True, step >= 2],
                               invariant=lambda step: step != 1), ep, normal=False)
    assert result["exit_reason"] == "goal_confirmed" and result["n_steps"] == 6
    assert result["goal_regression"] is True and result["invariant_regression"] is True
    assert result["official_goals_achieved"] is True


@pytest.mark.parametrize("task", ["bowl_drawer_close", "mug_microwave_close"])
def test_open_is_initial_constraint_and_closure_is_allowed(task):
    ep = source(task, normal=False)
    _, _, result = run(NineEnv(ep, goals=lambda step: [True, step >= 1],
                               opened=lambda step: step == 0), ep, normal=False)
    assert result["n_steps"] == 5 and result["goal_regression"] is False
    policy, _, bad = run(NineEnv(ep, goals=lambda step: [True, False], opened=lambda step: False), ep, normal=False)
    assert bad["status"] == "invalid_initial_state" and policy.calls == 0


def test_nine_result_rejects_official_mapping_and_invariant_tampering():
    ep = source()
    _, _, result = run(NineEnv(ep), ep)
    broken = deepcopy(result)
    broken["trace"][1]["official_goal_values"][0] = False
    with pytest.raises(ValueError):
        schema.validate_protocol_result(broken, ep)
    broken = deepcopy(result)
    broken["task_semantics"]["invariant_indices"] = []
    with pytest.raises(ValueError):
        schema.validate_protocol_result(broken, ep)
