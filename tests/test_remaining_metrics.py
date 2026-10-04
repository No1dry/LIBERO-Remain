"""Boundary, retention, trace-integrity and manifest-coverage tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from benchmark.remaining_goals.metrics import compute_metrics, summarize_results


def episode(mask=(True, False), *, episode_id="e1", task_id="task", horizon=2, retention=2):
    return {
        "episode_id": episode_id,
        "task_id": task_id,
        "initial_mask": list(mask),
        "horizon": horizon,
        "retention_steps": retention,
    }


def trace(*goals, stop=None):
    return [
        {"step": step, "goals": list(values), "action": None if step == 0 else [0.0] * 7,
         "stopped": stop is not None and step >= stop}
        for step, values in enumerate(goals)
    ]


def result(spec, rows=None, *, status="completed"):
    return {**deepcopy(spec), "status": status, "trace": rows or []}


def successful_rows(spec):
    end = spec["retention_steps"] + (0 if all(spec["initial_mask"]) else spec["horizon"])
    return trace(spec["initial_mask"], *([True] * len(spec["initial_mask"]) for _ in range(end)))


def test_success_at_horizon_is_inclusive_and_actions_are_not_errors():
    rows = trace([True, False], [True, False], [True, True], [True, True], [True, True])
    rows[4]["action"] = [1.0] * 7
    got = compute_metrics(episode(), rows)
    assert got == {
        "joint_success": True, "task_success_by_horizon": True,
        "stable_final_success": True, "remaining_success": True,
        "preservation_success": True, "goal_regression": False,
        "regression_steps": 0, "first_all_success_step": 2,
        "explicit_stop_step": None, "n_steps": 4,
    }


def test_first_success_after_horizon_does_not_count():
    rows = trace([True, False], [True, False], [True, False], [True, True], [True, True])
    got = compute_metrics(episode(), rows)
    assert got["first_all_success_step"] == 3
    assert got["task_success_by_horizon"] is False
    assert got["stable_final_success"] is False
    assert got["remaining_success"] is False
    assert got["joint_success"] is False


def test_temporary_initial_goal_break_is_not_erased_by_recovery():
    rows = trace([True, False], [False, True], [True, True], [True, True], [True, True])
    got = compute_metrics(episode(), rows)
    assert got["stable_final_success"] is True
    assert got["remaining_success"] is True
    assert got["preservation_success"] is False
    assert got["joint_success"] is False
    assert got["goal_regression"] is True
    assert got["regression_steps"] == 1


def test_break_inside_retention_window_invalidates_stability_even_if_restored():
    rows = trace([True, False], [True, True], [True, True], [True, False], [True, True])
    got = compute_metrics(episode(), rows)
    assert got["task_success_by_horizon"] is True
    assert got["preservation_success"] is True
    assert got["remaining_success"] is False
    assert got["stable_final_success"] is False
    assert got["joint_success"] is False


def test_remaining_goals_must_be_simultaneously_true():
    spec = episode((False, False))
    got = compute_metrics(spec, trace([False, False], [True, False], [False, True], [True, True], [True, True]))
    assert got["remaining_success"] is False
    assert got["task_success_by_horizon"] is False
    assert got["preservation_success"] is None
    assert got["goal_regression"] is False


def test_all_completed_uses_retention_only_and_has_no_remaining_metric():
    spec = episode((True, True), horizon=20)
    got = compute_metrics(spec, trace([True, True], [True, True], [True, True], stop=1))
    assert got["remaining_success"] is None
    assert got["task_success_by_horizon"] is True
    assert got["joint_success"] is True
    assert got["first_all_success_step"] == 0
    assert got["explicit_stop_step"] == 0
    assert got["n_steps"] == 2


def test_terminal_break_counts_even_if_repaired():
    spec = episode((True, True))
    got = compute_metrics(spec, trace([True, True], [False, False], [True, True]))
    assert got["task_success_by_horizon"] is True
    assert got["stable_final_success"] is False
    assert got["regression_steps"] == 1  # Not two for two violated goals.
    assert got["preservation_success"] is False


def test_explicit_stop_uses_decision_observation_not_hold_action_endpoint():
    rows = successful_rows(episode())
    rows[3]["stopped"] = True
    rows[4]["stopped"] = True
    assert compute_metrics(episode(), rows)["explicit_stop_step"] == 2


def test_zero_budget_pure_function_boundary():
    got = compute_metrics(episode(horizon=0, retention=0), trace([True, False]))
    assert got["n_steps"] == 0
    assert got["joint_success"] is False


@pytest.mark.parametrize("mutation", [
    lambda s, t: t.pop(),
    lambda s, t: t.append(deepcopy(t[-1])),
    lambda s, t: t[2].update(step=1),
    lambda s, t: t[2].update(step=3),
    lambda s, t: t[1].update(step=True),
    lambda s, t: t[0].update(goals=[False, False]),
    lambda s, t: t[1].update(goals=[True]),
    lambda s, t: t[1].update(goals=[True, 1]),
    lambda s, t: t[1].update(goals=[True, "false"]),
    lambda s, t: t[1].update(stopped=0),
    lambda s, t: t[1].update(action="hold"),
    lambda s, t: t[1].pop("action"),
    lambda s, t: s.update(initial_mask=[1, False]),
    lambda s, t: s.update(initial_mask=[]),
    lambda s, t: s.update(horizon=True),
    lambda s, t: s.update(retention_steps=-1),
])
def test_malformed_or_incomplete_trace_is_not_scored(mutation):
    spec = episode()
    rows = successful_rows(spec)
    mutation(spec, rows)
    with pytest.raises(ValueError):
        compute_metrics(spec, rows)


def test_summary_retains_missing_invalid_and_runtime_denominators():
    specs = [episode(episode_id=f"e{i}") for i in range(4)]
    results = [
        result(specs[0], successful_rows(specs[0])),
        result(specs[1], status="invalid_initial_state"),
        result(specs[2], status="runtime_error"),
    ]
    got = summarize_results(specs, results)
    assert got["counts"] == {
        "expected": 4, "completed": 1, "invalid_initial_state": 1,
        "runtime_error": 1, "missing": 1, "errors": 2,
    }
    assert got["missing_episode_ids"] == ["e3"]
    group = got["by_task_mask"][0]
    assert group["valid_metrics"]["joint_success"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert group["coverage"] == 0.25
    assert group["conservative_joint_success"] == 0.25
    assert got["partial_macro"]["valid_joint_success"] == 1.0
    assert got["partial_macro"]["conservative_joint_success"] == 0.25


def test_summary_missing_entire_mask_is_visible_and_not_omitted_from_macro():
    specs = [episode(episode_id="a"), episode((False, True), episode_id="b")]
    got = summarize_results(specs, [result(specs[0], successful_rows(specs[0]))])
    assert [(x["mask"], x["completed"], x["missing"]) for x in got["by_task_mask"]] == [("01", 0, 1), ("10", 1, 0)]
    assert got["partial_macro"]["valid_joint_success"] is None
    assert got["partial_macro"]["expected_task_masks"] == 2
    assert got["partial_macro"]["covered_task_masks"] == 1
    assert got["partial_macro"]["conservative_joint_success"] == 0.5


def test_macro_weights_tasks_then_masks_and_separates_controls():
    specs = [episode(episode_id=f"a10-{i}", task_id="a") for i in range(3)]
    specs += [episode((False, True), episode_id="a01", task_id="a"),
              episode(episode_id="b10", task_id="b"),
              episode((False, False), episode_id="a00", task_id="a"),
              episode((True, True), episode_id="a11", task_id="a")]
    results = [result(s, successful_rows(s)) for s in specs]
    for i in (3, 4):
        results[i]["trace"] = trace(*[specs[i]["initial_mask"]] * 5)
    got = summarize_results(specs, results)
    # Task a: mean(10=1, 01=0)=0.5; task b: 10=0; task macro=0.25.
    assert got["partial_macro"]["valid_joint_success"] == 0.25
    assert got["partial_macro"]["expected"] == 5
    assert got["normal_00"]["valid_joint_success"] == 1.0
    assert got["terminal_11"]["valid_joint_success"] == 1.0
    normal = next(x for x in got["by_task_mask"] if x["mask"] == "00")
    terminal = next(x for x in got["by_task_mask"] if x["mask"] == "11")
    assert normal["valid_metrics"]["preservation_success"]["denominator"] == 0
    assert terminal["valid_metrics"]["remaining_success"]["rate"] is None


def test_summary_recomputes_metrics_instead_of_trusting_cache():
    spec = episode()
    rows = trace(*[[True, False]] * 5)
    record = result(spec, rows)
    record.update(metrics={"joint_success": True}, stop_step=0)
    got = summarize_results([spec], [record])
    assert got["by_task_mask"][0]["valid_metrics"]["joint_success"]["rate"] == 0.0


@pytest.mark.parametrize("case", ["duplicate_expected", "duplicate_result", "unknown_id", "bad_status", "mismatched_mask", "mismatched_horizon", "bad_completed_trace"])
def test_summary_rejects_ambiguous_or_inconsistent_inputs(case):
    spec = episode()
    specs = [spec]
    results = [result(spec, successful_rows(spec))]
    if case == "duplicate_expected":
        specs.append(deepcopy(spec))
    elif case == "duplicate_result":
        results.append(deepcopy(results[0]))
    elif case == "unknown_id":
        results[0]["episode_id"] = "unknown"
    elif case == "bad_status":
        results[0]["status"] = "success"
    elif case == "mismatched_mask":
        results[0]["initial_mask"] = [False, True]
    elif case == "mismatched_horizon":
        results[0]["horizon"] = 3
    else:
        results[0]["trace"].pop()
    with pytest.raises(ValueError):
        summarize_results(specs, results)


def test_empty_manifest_is_explicitly_empty_and_json_safe():
    import json
    got = summarize_results([], [])
    assert got["counts"]["expected"] == 0
    assert got["partial_macro"]["valid_joint_success"] is None
    assert got["terminal_11"]["conservative_joint_success"] is None
    json.dumps(got, allow_nan=False)
