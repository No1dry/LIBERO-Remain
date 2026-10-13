"""Score legal CPU fake runner traces; no physical or model-quality claims."""
from copy import deepcopy

import pytest

from benchmark.remaining_goals.finish import metrics
from benchmark.remaining_goals.finish.runner import run_finish_episode
from tests.test_finish_runner import Env, Policy, episode


class SequenceEnv(Env):
    def __init__(self, goals=None, released=None, objects=None, **kwargs):
        super().__init__(**kwargs)
        self.goal_sequence, self.release_sequence, self.object_sequence = goals, released, objects

    def evaluator_state(self):
        state = super().evaluator_state()
        goals = self.goal_sequence(self.steps) if self.goal_sequence else state["goals"]
        released = self.release_sequence(self.steps) if self.release_sequence else True
        state.update(goals=list(goals), released=released)
        for index, name in enumerate(("a", "b")):
            state["objects"][name].update(in_basket=goals[index], released=released)
        if self.object_sequence:
            state["objects"].update(deepcopy(self.object_sequence(self.steps)))
        return state


def object_state(*, inside=False, released=True, role="distractor"):
    return {"role": role, "in_basket": inside, "released": released,
            "release_evidence": {"method": "synthetic-contact-and-geometry"}}


def execute(*, mask=(False, False), goals=None, released=None, objects=None,
            finish_at=8, mode="active", horizon=12, retention=8, fail_step=None, identifier="case"):
    ep = episode(list(mask))
    ep["episode_id"] = identifier
    env = SequenceEnv(goals=goals, released=released, objects=objects, fail_step=fail_step)
    result = run_finish_episode(env, Policy(finish_at=finish_at), ep, mode=mode,
                                horizon=horizon, retention_steps=retention)
    return ep, result


def completed(step):
    return [step >= 4, step >= 4]


def test_compliant_finish_uses_decision_state_stability_and_delay_in_intervals():
    ep, result = execute(goals=completed)
    before = deepcopy(result)
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is True and score["scoring_status"] == "scored"
    assert score["finish_step"] == 8 and score["tau"] == 4
    assert score["finish_delay_steps"] == 4 and score["finish_delay_seconds"] == .2
    assert score["failure_reasons"] == score["unknown_reasons"] == []
    assert result == before


def test_valid_11_tau_zero_and_no_minimum_action_requirement():
    ep, result = execute(mask=(True, True), finish_at=0)
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is True
    assert score["tau"] == score["finish_step"] == score["finish_delay_steps"] == 0
    assert result["n_steps"] == 8
    assert result["queries"][0]["accepted_chunk_length"] == 0


def test_future_hold_success_cannot_rescue_premature_finish():
    ep, result = execute(goals=lambda step: [step > 0, step > 0], finish_at=0)
    score = metrics.score_episode(ep, result)
    assert all(result["trace"][-1]["goals"])
    assert score["compliant_finish"] is False
    assert {"premature_finish", "unfinished_goal", "unstable_after_exit"} <= set(score["failure_reasons"])
    assert score["tau"] == 1 and score["finish_delay_steps"] is None
    assert score["delay_status"] == "premature_finish"


def test_goal_success_while_held_is_premature_finish_not_released_success():
    ep, result = execute(goals=completed, released=lambda step: step > 8)
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is False and score["released_at_exit"] is False
    assert score["failure_reasons"] == ["premature_finish"]
    assert score["finish_delay_steps"] is None


def test_initial_preservation_regression_remains_failure_after_recovery():
    ep, result = execute(mask=(True, False), goals=lambda step: [step != 2, step >= 4])
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is False
    assert "goal_regression" in score["failure_reasons"] and score["initial_preservation"] is False
    assert all(result["trace"][-1]["goals"])


def test_hold_goal_drift_fails_even_when_finish_was_correct():
    ep, result = execute(goals=lambda step: [step >= 4 and step != 10, step >= 4])
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is False
    assert score["failure_reasons"] == ["unstable_after_exit"]
    assert score["goals_at_exit"] == [True, True]


@pytest.mark.parametrize("stable,expected", [(1, True), (4, True), (8, False)])
def test_wrong_object_stability_sensitivity_counts_physical_intervals(stable, expected):
    # Inside/released states 2..6 span precisely four physical intervals.
    ep, result = execute(goals=completed, objects=lambda step: {
        "extra": object_state(inside=2 <= step <= 6)})
    score = metrics.score_episode(ep, result, stable_steps=stable)
    assert ("forbidden_placement" in score["failure_reasons"]) is expected
    assert score["compliant_finish"] is (not expected)
    if expected:
        assert score["forbidden_placements"] == [{"object": "extra", "start_step": 2,
                                                  "confirmed_step": 2 + stable, "stable_steps": stable}]
        assert result["trace"][-1]["objects"]["extra"]["in_basket"] is False


@pytest.mark.parametrize("scenario", ["transient", "held", "initial_extra", "container", "fixture"])
def test_transient_contact_held_object_existing_extra_and_fixed_roles_not_forbidden(scenario):
    def objects(step):
        if scenario == "transient":
            item = object_state(inside=step == 2)
        elif scenario == "held":
            item = object_state(inside=step >= 2, released=False)
        elif scenario == "initial_extra":
            item = object_state(inside=step != 2)
        else:
            item = object_state(inside=True, role=scenario)
        return {"extra": item}
    ep, result = execute(goals=completed, objects=objects)
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is True and score["forbidden_placements"] == []


@pytest.mark.parametrize("scenario", ["target_release", "initial_object_membership", "object_release"])
def test_ambiguous_evidence_remains_unknown_never_success(scenario):
    kwargs = {"goals": completed}
    if scenario == "target_release":
        kwargs["released"] = lambda step: None if step == 8 else True
    elif scenario == "initial_object_membership":
        kwargs["objects"] = lambda step: {"extra": object_state(inside=None if step == 0 else False)}
    else:
        kwargs["objects"] = lambda step: {"extra": object_state(inside=step > 1,
                                                                  released=None if step > 1 else True)}
    ep, result = execute(**kwargs)
    score = metrics.score_episode(ep, result)
    assert score["compliant_finish"] is None and score["scoring_status"] == "unknown"
    assert score["unknown_reasons"]


def test_timeout_and_shadow_are_distinct_and_never_fake_finish():
    ep, active = execute(goals=completed, finish_at=None)
    score = metrics.score_episode(ep, active)
    assert score["compliant_finish"] is False and score["failure_reasons"] == ["no_finish_timeout"]
    assert score["tau"] == 4 and score["finish_delay_steps"] is None and score["delay_status"] == "timeout"
    ep, shadow = execute(goals=completed, finish_at=0, mode="shadow")
    score = metrics.score_episode(ep, shadow)
    assert score["compliant_finish"] is None and score["scoring_status"] == "not_applicable"
    summary = metrics.summarize([ep], [shadow], mode="shadow")
    assert summary["counts"]["successful"] is None and summary["counts"]["compliant_finish_percent"] is None
    assert "N/A" in metrics.render_report(summary)


def test_fixed_denominator_keeps_unknown_technical_missing_and_all_delay_categories():
    ep1, successful = execute(identifier="success", goals=completed)
    ep2, timeout = execute(identifier="timeout", goals=completed, finish_at=None)
    ep3, unknown = execute(identifier="unknown", goals=completed, released=lambda step: None)
    ep4, error = execute(identifier="technical", goals=completed, fail_step=2)
    ep5 = deepcopy(ep1)
    ep5["episode_id"] = "not_attempted"
    summary = metrics.summarize([ep1, ep2, ep3, ep4, ep5], [successful, timeout, unknown, error], mode="active")
    cell = summary["counts"]
    assert cell["expected"] == 5 and cell["successful"] == 1 and cell["fraction"] == "1/5"
    assert cell["compliant_finish_percent"] == 20.0
    assert (cell["scored"], cell["unknown"], cell["technical_error"], cell["missing"]) == (2, 1, 1, 1)
    assert cell["score_coverage"] == .4 and cell["delay_coverage"] == .2
    assert cell["delay_mean_steps"] == 4 and cell["delay_observed"] == 1
    assert cell["delay_categories"] == {"observed": 1, "timeout": 1, "unknown_release": 1,
                                         "technical_error": 1, "missing": 1}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0, -1, True])
def test_invalid_frequency_rejected_even_for_all_missing_results(bad):
    ep = episode()
    with pytest.raises(ValueError, match="control_freq"):
        metrics.summarize([ep], [], mode="active", control_freq=bad)


@pytest.mark.parametrize("change", ["new_object", "missing_object", "changed_role", "initial_mask"])
def test_tampered_evaluator_identity_cannot_change_scoring_contract(change):
    ep, result = execute(goals=completed, objects=lambda step: {"extra": object_state()})
    if change == "new_object":
        result["trace"][3]["objects"]["unlisted"] = object_state(inside=True)
    elif change == "missing_object":
        del result["trace"][3]["objects"]["extra"]
    elif change == "changed_role":
        result["trace"][3]["objects"]["extra"]["role"] = "fixture"
    else:
        result["trace"][0]["goals"] = [True, True]
    with pytest.raises(ValueError):
        metrics.score_episode(ep, result)


def test_summary_rejects_duplicates_unknown_ids_mixed_modes_and_legacy_result():
    ep, result = execute(goals=completed)
    for rows in ([result, deepcopy(result)], [{**result, "episode_id": "wrong"}],
                 [{**result, "mode": "shadow"}], [{**result, "protocol_version": "remaining-goals-v0.1"}]):
        with pytest.raises(ValueError):
            metrics.summarize([ep], rows, mode="active")
