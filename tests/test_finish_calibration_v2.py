"""Decision/timing logic on CPU sequences; no physical/model execution."""
from copy import deepcopy
from itertools import product

import pytest

from benchmark.remaining_goals.finish.calibration import THRESHOLDS, _first_stable, calibrate_threshold
from benchmark.remaining_goals.finish.calibration_v2 import tau_bounds, first_hit_timing, sensitivity_table
from benchmark.remaining_goals.finish.data import canonical_hash
from benchmark.remaining_goals.finish.evaluation import evaluation_contract
from benchmark.remaining_goals.finish import metrics


def decision(truth, step, *, threshold=.5, horizon=None, k=4, timely=24):
    return first_hit_timing(truth, [{"observation_step": step, "p": .9}], threshold,
                            len(truth) - 1 if horizon is None else horizon,
                            confirmation_steps=k, timely_steps=timely)


def test_k4_needs_five_observations_and_never_fills_known_false_prefix():
    truth = [False] * 4 + [True] * 5
    assert tau_bounds(truth, 8)["tau_low"] == tau_bounds(truth, 8)["tau_high"] == 4
    row = decision(truth, 4)
    assert row["timely"] is True and row["delay_steps_interval"] == {"minimum": 0, "maximum": 0}
    assert tau_bounds([False] * 4 + [True] * 4, 7)["tau_low"] is None


@pytest.mark.parametrize("offset,expected", [(-1, False), (0, True), (24, True), (25, False)])
def test_exact_reference_timing_edges(offset, expected):
    # Keep the first-hit frame True even before tau: an isolated True is not K4.
    truth = [False] * 6 + [True] * 30
    step = 6 + offset
    if offset == -1:
        truth[step] = True
        truth[step + 1] = False
        truth[step + 2:] = [True] * len(truth[step + 2:])
    row = decision(truth, step)
    assert row["timely"] is expected and row["timing_unknown"] is False
    assert row["first_hit_status"] == "correct"  # too early for tau is not a new premature label


def test_unknown_interval_true_false_and_ambiguous_without_favorable_endpoint_selection():
    truth = [False] * 3 + [None] * 5 + [True] * 40
    bounds = tau_bounds(truth, len(truth) - 1)
    assert (bounds["tau_low"], bounds["tau_high"]) == (3, 8)
    assert decision(truth, 8)["timely"] is True
    assert decision(truth, 27)["timely"] is True
    ambiguous = decision(truth, 28)
    assert ambiguous["timely"] is None and ambiguous["timing_unknown"]
    assert ambiguous["delay_steps_interval"] == {"minimum": 20, "maximum": 25}
    late = decision(truth, 33)
    assert late["timely"] is False and not late["timing_unknown"]


def test_no_stable_reference_both_sides_is_known_not_timely():
    row = decision([False, True, False, True, False, True], 3)
    assert row["first_hit_status"] == "correct"
    assert row["tau_low"] is None and row["tau_high"] is None
    assert row["timely"] is False and not row["timing_unknown"]
    assert row["timing_reason"] == "no_stable_reference_under_either_completion"


def test_one_no_reference_endpoint_cannot_be_used_as_success():
    row = decision([False, None, None, True, True, True, False], 3)
    assert row["tau_low"] == 1 and row["tau_high"] is None
    assert row["timely"] is None and row["timing_unknown"]


@pytest.mark.parametrize("first", [False, None])
def test_first_false_or_unknown_is_never_erased_by_later_good_crossing(first):
    truth = [False, first, False, True, True, True, True, True]
    row = first_hit_timing(truth, [{"observation_step": 1, "p": .8}, {"observation_step": 3, "p": .99}], .5, 7)
    assert row["first_crossing_step"] == 1
    assert row["first_hit_status"] == ("premature" if first is False else "unknown_first_hit")
    assert row["timely"] is not True and not row["timing_unknown"]


def test_not_triggered_has_known_false_timeliness_despite_uncertain_tau():
    row = first_hit_timing([False, None, None, True, True, True], [{"observation_step": 3, "p": .1}], .5, 5)
    assert row["tau_low"] == 1 and row["tau_high"] is None
    assert row["first_hit_status"] == "not_triggered"
    assert row["timely"] is False and row["timing_unknown"] is False


def test_irrelevant_retention_unknown_is_diagnostic_not_timing_veto():
    truth = [False] * 4 + [True] * 10 + [None] * 10
    row = decision(truth, 8, horizon=12)
    assert row["tau_low"] == row["tau_high"] == 4
    assert row["timely"] is True
    assert row["completion_unknown_steps"] == list(range(14, 24))


def test_completion_start_after_horizon_is_not_a_reference():
    row = decision([False] * 5 + [True] * 5, 4, horizon=4)
    assert row["tau_low"] is row["tau_high"] is None
    assert row["first_hit_status"] == "premature"


def test_tau_bounds_and_known_classifications_are_sound_under_all_completions():
    # Exhaustive small sequences verify the interval reasoning independently,
    # including holes of known False; this does not certify physical labels.
    for prefix in product((False, True, None), repeat=6):
        truth = list(prefix[:4]) + [True] + list(prefix[4:])
        bounds = tau_bounds(truth, 6, 2)
        indices = [i for i, value in enumerate(truth) if value is None]
        references, answers = [], []
        for values in product((False, True), repeat=len(indices)):
            completion = truth.copy()
            for index, value in zip(indices, values):
                completion[index] = value
            tau = _first_stable(completion, 6, 2)
            references.append(tau)
            answers.append(tau is not None and 0 <= 4 - tau <= 2)
        finite = [tau for tau in references if tau is not None]
        assert bounds["tau_low"] == (min(finite) if finite else None)
        assert bounds["tau_high"] == (max(references) if all(t is not None for t in references) else None)
        row = decision(truth, 4, k=2, timely=2)
        if row["timely"] is True:
            assert all(answers)
        elif row["timely"] is False:
            assert not any(answers)


@pytest.mark.parametrize("kwargs", [{"thresholds": [.5]}, {"confirmation_steps": 3}, {"timely_steps": 25}])
def test_new_formal_search_cannot_change_preregistered_grid_or_windows(kwargs):
    with pytest.raises(ValueError, match="preregistered"):
        calibrate_threshold([], [], evaluation_contract=evaluation_contract(), **kwargs)


def test_new_formal_search_requires_five_registered_sources_and_valid_contract():
    with pytest.raises(ValueError, match="five"):
        calibrate_threshold([], [], evaluation_contract=evaluation_contract())
    contract = evaluation_contract()
    contract["timely_steps"] = 25
    with pytest.raises(ValueError, match="contract|method|rule"):
        calibrate_threshold([], [], evaluation_contract=contract)


def test_legacy_calibration_and_metrics_golden_hashes_unchanged():
    from tests.test_remaining_finish_calibration import population
    from tests.test_remaining_finish_metrics import execute, completed
    episodes, results = population(unknown_at=10)
    for result in results:
        result["elapsed_seconds"] = 0.0
    report = calibrate_threshold(episodes, results)
    assert report["calibrated"] is False
    assert canonical_hash(report) == "9046c209c93a1d0a8dc4b80bdd41e5cd4729c6203f7ee6d2ed3ac0b7c0405343"
    episode, result = execute(goals=completed)
    assert canonical_hash(metrics.score_episode(episode, result)) == "3a894b2efced6dcf7050a0b76a94d4d2e0db1a35eb4343ab11bb87e7975e005a"
    assert canonical_hash(metrics.summarize([episode], [result], mode="active")) == "82c2a1cd257c3e0a014841936a43f6d293094f50bc3714afff7716daed3f972a"


def test_new_results_cannot_enter_implicit_legacy_calibration_or_metrics():
    new = {"schema_version": "remaining-finish-episode-v2", "evaluation_contract": evaluation_contract()}
    with pytest.raises(ValueError, match="explicit"):
        calibrate_threshold([{"episode_id": "case"}], [new])
    with pytest.raises(ValueError, match="explicit"):
        metrics.score_episode({}, new)
    from tests.test_remaining_finish_metrics import execute, completed
    episode, result = execute(goals=completed)
    with pytest.raises(ValueError, match="legacy"):
        metrics.score_episode(episode, result, evaluation_contract=evaluation_contract())
