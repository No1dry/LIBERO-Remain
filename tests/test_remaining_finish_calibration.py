"""Calibration on full synthetic FINISH ledgers; no environment/model assets."""
import copy
import math

import pytest

from benchmark.remaining_goals.finish.calibration import THRESHOLDS, calibrate_threshold
from benchmark.remaining_goals.finish.runner import run_finish_episode
from tests.test_finish_runner import Env, Policy, envelope, episode


class CompletionEnv(Env):
    def __init__(self, complete_at=8, unknown_at=None):
        super().__init__()
        self.complete_at, self.unknown_at = complete_at, unknown_at

    def evaluator_state(self):
        self.mask = [self.steps >= self.complete_at] * 2
        result = super().evaluator_state()
        if self.steps == self.unknown_at:
            result["released"] = None
        return result


class ScorePolicy(Policy):
    def __init__(self, scores):
        super().__init__()
        self.scores = scores

    def predict(self, obs, instruction):
        step = int(obs["proprio"][0])
        probability = self.scores.get(step, 0.01)
        result = envelope(probability >= .5, step)
        result.update(p=probability, logit=math.log(probability / (1 - probability)))
        return result


def population(scores=None, complete_at=8, unknown_at=None):
    expected, results = [], []
    for source in range(35, 40):
        ep = episode()
        ep["episode_id"] = f"normal_{source}"
        expected.append({"episode_id": ep["episode_id"], "source_index": source, "split": "validation"})
        result = run_finish_episode(CompletionEnv(complete_at, unknown_at), ScorePolicy(scores or {8: .91, 16: .95}), ep,
                                    mode="shadow", horizon=16, retention_steps=4)
        assert result["status"] == "completed", result["error"]
        results.append(result)
    return expected, results


def test_fixed_default_grid_and_highest_tie_selected():
    expected, results = population()
    report = calibrate_threshold(expected, results)
    assert THRESHOLDS == tuple([i / 20 for i in range(1, 20)] + [.99])
    assert report["selected_threshold"] == .95
    assert report["calibrated"] and report["validation_evidence_valid"]
    assert report["ordinary_stopping_capability_established"] is False
    selected = next(row for row in report["candidates"] if row["threshold"] == .95)
    assert selected["timely"] == 5 and selected["timely_rate"] == 1
    assert selected["episodes"][0]["first_crossing_step"] == 16


def test_first_early_hit_cannot_be_erased_by_later_good_crossing():
    expected, results = population({0: .8, 8: .95, 16: .98})
    report = calibrate_threshold(expected, results, thresholds=[.5, .9])
    assert report["candidates"][0]["premature"] == 5
    assert report["candidates"][0]["correct"] == 0
    assert report["selected_threshold"] == .9
    assert report["candidates"][1]["timely"] == 5


def test_zero_early_zero_finish_is_not_stopping_capability():
    expected, results = population({0: .01, 8: .01, 16: .01})
    report = calibrate_threshold(expected, results)
    assert report["validation_evidence_valid"] and report["selected_threshold"] == .99
    assert not report["calibrated"] and not report["candidate_stopping_behavior_observed"]
    assert report["reason"] == "no_timely_finish"
    assert all(row["not_triggered"] == 5 for row in report["candidates"])


def test_all_early_has_no_feasible_threshold():
    expected, results = population({0: .999, 8: .999, 16: .999})
    report = calibrate_threshold(expected, results)
    assert report["selected_threshold"] is None
    assert report["reason"] == "no_zero_premature_candidate"


def test_missing_runtime_error_fixed_denominator_and_unknown_are_visible():
    expected, results = population()
    results.pop()
    results[0] = {"episode_id": expected[0]["episode_id"], "status": "runtime_error", "error": "fake"}
    report = calibrate_threshold(expected, results)
    assert (report["expected"], report["completed"], report["errors"], report["missing"]) == (5, 3, 1, 1)
    assert not report["calibrated"] and report["coverage"] == .6
    assert max(row["timely_rate"] for row in report["candidates"]) == .6
    expected, results = population(unknown_at=10)
    report = calibrate_threshold(expected, results)
    assert report["unknown"] == 5 and not report["calibrated"]


def test_completion_after_horizon_does_not_create_timely_hit():
    expected, results = population(complete_at=17)
    report = calibrate_threshold(expected, results)
    assert all(row["timely"] == 0 for row in report["candidates"])
    assert not report["calibrated"]


@pytest.mark.parametrize("change", ["duplicate", "unknown", "wrong_split", "oracle", "edited", "wrong_sources"])
def test_population_identity_and_test_leakage_rejected(change):
    expected, results = population()
    if change == "duplicate":
        results.append(copy.deepcopy(results[0]))
    elif change == "unknown":
        results[0]["episode_id"] = "other"
    elif change == "wrong_split":
        expected[0]["split"] = "normal_test"
    elif change == "oracle":
        expected[0]["instruction_mode"] = "oracle-remaining-initial"
    elif change == "edited":
        expected[0]["edited_variant"] = True
    else:
        expected[0]["source_index"] = 40
    with pytest.raises(ValueError):
        calibrate_threshold(expected, results)


@pytest.mark.parametrize("change", ["trace_gap", "nan", "fake_p", "missing_query", "active", "source_conflict"])
def test_invalid_evidence_cannot_be_silently_excluded_to_calibrate(change):
    expected, results = population()
    if change == "trace_gap":
        results[0]["trace"].pop(3)
    elif change == "nan":
        results[0]["queries"][0]["p"] = float("nan")
    elif change == "fake_p":
        results[0]["queries"][0]["p"] = .7
    elif change == "missing_query":
        results[0]["queries"].pop()
    elif change == "active":
        results[0]["mode"] = "active"
    else:
        results[0]["source_index"] = 49
    if change == "nan":
        # Nonfinite evidence cannot even be canonically hashed into an artifact.
        with pytest.raises(ValueError):
            calibrate_threshold(expected, results)
    else:
        report = calibrate_threshold(expected, results)
        assert report["errors"] == 1 and not report["calibrated"]
        assert report["expected"] == 5


def test_different_head_artifacts_not_pooled():
    expected, results = population()
    for query in results[0]["queries"]:
        query["head_identity"]["artifact_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="different head"):
        calibrate_threshold(expected, results)


def test_arbitrary_alternate_sources_need_frozen_confirmed_split_identity():
    expected, results = population()
    for episode in expected:
        episode["source_index"] -= 10
    with pytest.raises(ValueError, match="frozen split identity"):
        calibrate_threshold(expected, results, expected_validation_sources=list(range(25, 30)))
