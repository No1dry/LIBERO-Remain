"""New calibration on actual CPU fake dual-observer/runner records, never native."""
from copy import deepcopy
import math

import pytest

from benchmark.remaining_goals.finish import metrics, workflow as w
from benchmark.remaining_goals.finish.calibration import calibrate_threshold
from benchmark.remaining_goals.finish.calibration_v2 import sensitivity_table
from benchmark.remaining_goals.finish.data import canonical_hash
from benchmark.remaining_goals.finish.evaluation import evaluation_contract, RELEASE_V1, RELEASE_V2, CALIBRATION_LEGACY, CALIBRATION_V2
from benchmark.remaining_goals.finish.schema import validate_finish_result


@pytest.fixture(autouse=True)
def fake_native_contact_filter_absent(monkeypatch):
    # Every native object in this module is a synthetic CPU fixture, with no
    # process-global MuJoCo callback. Match tiny_run's explicit fake capability
    # for manually regenerated frames and direct active runs as well. Geometry
    # computation, static identities and offline validation stay unmocked.
    from benchmark.remaining_goals.finish import environment
    monkeypatch.setattr(environment, "_contact_filter_status", lambda: "absent")


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    from tests.test_finish_versioned_workflow import versioned_fixture, tiny_run
    path = tmp_path_factory.mktemp("dual-calibration-records")
    job, registry = versioned_fixture(path / "inputs")
    with pytest.MonkeyPatch.context() as patch:
        tiny_run(job, path / "shadow", patch)
    metadata, results = w.read_run(path / "shadow")
    return metadata["episodes"], results, {"evaluation_contract": evaluation_contract(),
        "source_registry": registry, "split_identity": metadata["source_identity"]}


def population(recorded):
    return deepcopy(recorded)


def replace_truth(row, *, goals=None, release="separated"):
    """Generate a synthetic alternate frame through both real observers.

    These are offline software fixtures, not counterfactual physical rollouts.
    Neither the production geometry algorithm nor schema validation is mocked.
    """
    from tests.test_finish_release_geometry import geometry_native
    from benchmark.remaining_goals.finish.environment import BasketContract, TARGETS
    native = geometry_native()
    for name, value in zip(TARGETS, row["goals"] if goals is None else goals):
        native.membership[name] = value
    if release == "unknown":
        native.contacts.add("soup")
    elif release == "legacy_true":
        native.sim.data.geom_xpos[:3, 2] = 2.
    elif release == "held":
        native.grasps.add("soup")
    row.update(BasketContract(native, evaluation_contract=evaluation_contract()).evaluator_state())


def set_probability(query, value):
    query.update(p=value, logit=math.log(value / (1 - value)),
                 head_decision="finish" if value >= query["threshold"] else "continue")


def test_official_report_binds_new_five_all_sources_and_does_not_mutate_inputs(recorded):
    episodes, results, kwargs = population(recorded)
    before = canonical_hash([episodes, results, kwargs])
    report = calibrate_threshold(episodes, results, **kwargs)
    assert report["schema_version"] == "remaining-finish-calibration-v3"
    assert report["calibrated"] and report["selected_threshold"] == .95
    assert report["active_eligible"] and not report["sensitivity_only"]
    assert report["expected"] == report["completed"] == 5 and report["coverage"] == 1
    assert report["validation_source_indices"] == list(range(35, 40))
    assert report["source_result_sha256"] == {r["episode_id"]: canonical_hash(r) for r in results}
    assert report["evaluation_contract"] == kwargs["evaluation_contract"]
    assert (report["release_method"], report["calibration_rule"]) == (RELEASE_V2, CALIBRATION_V2)
    assert not report["ordinary_stopping_capability_established"]
    chosen = next(row for row in report["candidates"] if row["threshold"] == .95)
    assert chosen["robust_timely"] == chosen["correct"] == 5 and chosen["timing_unknown"] == 0
    assert all(row["tau_low"] == row["tau_high"] == 8 for row in chosen["episodes"])
    assert canonical_hash([episodes, results, kwargs]) == before
    assert report["calibration_sha256"] == canonical_hash({k: v for k, v in report.items() if k != "calibration_sha256"})


@pytest.mark.parametrize("fault", ["missing", "technical_error", "source_mismatch", "missing_measurement"])
def test_invalid_or_missing_evidence_never_shrinks_denominator_or_selects_threshold(recorded, fault):
    episodes, results, kwargs = population(recorded)
    if fault == "missing": results.pop()
    elif fault == "technical_error": results[-1]["status"] = "runtime_error"
    elif fault == "source_mismatch": results[-1]["state_sha256"] = "f" * 64
    else: results[-1]["trace"][12].pop("measurement")
    report = calibrate_threshold(episodes, results, **kwargs)
    assert report["expected"] == 5 and report["completed"] == 4
    assert report["missing"] + report["errors"] == 1 and report["coverage"] == .8
    assert not report["calibrated"] and report["selected_threshold"] is None
    assert not report["active_eligible"] and not report["validation_evidence_valid"]
    assert all(row["expected"] == 5 and row["timely_rate"] <= .8 for row in report["candidates"])


@pytest.mark.parametrize("fault", ["wrong_source_role", "duplicate_source", "head_mixed", "contract"])
def test_wrong_population_head_or_version_cannot_enter_new_calibration(recorded, fault):
    episodes, results, kwargs = population(recorded)
    if fault == "wrong_source_role": episodes[0]["eval_source"]["role"] = "normal_test"
    elif fault == "duplicate_source":
        episodes[1]["eval_source"] = deepcopy(episodes[0]["eval_source"])
        episodes[1]["initial_state_index"] = episodes[0]["initial_state_index"]
    elif fault == "head_mixed": results[0]["queries"][0]["head_identity"]["artifact_sha256"] = "f" * 64
    else: kwargs["evaluation_contract"]["calibration_rule"] = CALIBRATION_LEGACY
    with pytest.raises(ValueError): calibrate_threshold(episodes, results, **kwargs)


@pytest.mark.parametrize("kind", ["premature", "unknown_first_hit", "timing_unknown", "no_hit"])
def test_first_hit_and_uncertain_reference_prevent_freezing_at_report_level(recorded, kind):
    episodes, results, kwargs = population(recorded)
    for result in results:
        if kind == "premature":
            set_probability(result["queries"][0], .999)
        elif kind == "unknown_first_hit":
            set_probability(result["queries"][1], .999)
            replace_truth(result["trace"][8], release="unknown")
        elif kind == "timing_unknown":
            for step in range(4, 8): replace_truth(result["trace"][step], goals=[True, True], release="unknown")
            for step in range(11, 21): replace_truth(result["trace"][step], goals=[False, False])
        else:
            for query in result["queries"]: set_probability(query, .001)
        validate_finish_result(result)
    report = calibrate_threshold(episodes, results, **kwargs)
    assert not report["calibrated"] and report["selected_threshold"] is None
    chosen = next(row for row in report["candidates"] if row["threshold"] == .95)
    assert chosen[{"no_hit": "not_triggered"}.get(kind, kind)] == 5
    assert chosen["robust_timely"] == 0
    if kind == "timing_unknown":
        assert all(row["tau_low"] == 4 and row["tau_high"] is None for row in chosen["episodes"])


def test_unrelated_w_unknown_kept_in_diagnostics_without_vetoing_robust_hit(recorded):
    episodes, results, kwargs = population(recorded)
    for result in results: replace_truth(result["trace"][20], release="unknown")
    report = calibrate_threshold(episodes, results, **kwargs)
    assert report["calibrated"] and report["selected_threshold"] == .95
    assert report["unknown"] == 5
    assert all(row["unknown_steps"] == row["release_unknown_steps"] == [20] for row in report["unknown_coverage"])
    assert all(row["object_release_unknown_steps"]["alphabet_soup_1"] == [20] for row in report["unknown_coverage"])


def test_two_by_two_changes_measurement_and_rule_only_never_formal_threshold(recorded):
    episodes, results, kwargs = population(recorded)
    before = canonical_hash(results)
    table = sensitivity_table(episodes, results, **kwargs)
    assert table["sensitivity_only"] and not table["active_eligible"] and table["selected_threshold"] is None
    cells = {(cell["release_method"], cell["calibration_rule"]): cell for cell in table["cells"]}
    assert set(cells) == {(method, rule) for method in (RELEASE_V1, RELEASE_V2) for rule in (CALIBRATION_LEGACY, CALIBRATION_V2)}
    assert all(cell["source_result_sha256"] == table["source_result_sha256"] and cell["expected"] == 5 for cell in cells.values())
    assert all(not cell["active_eligible"] and not cell["calibrated"] and cell["selected_threshold"] is None for cell in cells.values())
    assert not cells[RELEASE_V1, CALIBRATION_LEGACY]["would_freeze_threshold"]
    assert not cells[RELEASE_V1, CALIBRATION_V2]["would_freeze_threshold"]
    assert cells[RELEASE_V2, CALIBRATION_LEGACY]["diagnostic_threshold"] == .95
    assert cells[RELEASE_V2, CALIBRATION_V2]["diagnostic_threshold"] == .95
    assert all(row["release_unknown_steps"] == list(range(21)) for row in cells[RELEASE_V1, CALIBRATION_LEGACY]["unknown_coverage"])
    assert all(row["unknown_steps"] == list(range(8, 21)) for row in cells[RELEASE_V1, CALIBRATION_LEGACY]["unknown_coverage"])
    assert canonical_hash(results) == before


def test_two_by_two_isolates_rule_effect_and_legacy_cell_matches_original_algorithm(recorded):
    episodes, results, kwargs = population(recorded)
    for result in results:
        for frame in result["trace"]: replace_truth(frame, release="legacy_true")
        replace_truth(result["trace"][20], release="unknown")
    table = sensitivity_table(episodes, results, **kwargs)
    for cell in table["cells"]:
        assert cell["would_freeze_threshold"] is (cell["calibration_rule"] == CALIBRATION_V2)
    # Test-only projection into the original API: production keeps untouched full
    # source hashes and never fabricates a historical v1 run or pilot truth.
    projected = deepcopy(results)
    for result in projected:
        result["schema_version"] = "remaining-finish-episode-v1"
        result.pop("evaluation_contract"); result.pop("measurement_static")
        for frame in result["trace"]:
            legacy = frame.pop("measurement")["legacy"]
            frame.update(legacy)
    old = calibrate_threshold(episodes, projected, **{k: v for k, v in kwargs.items() if k != "evaluation_contract"})
    cell = table["cells"][0]
    assert old["calibrated"] is False and cell["would_freeze_threshold"] is False
    for original, derived in zip(old["candidates"], cell["candidates"]):
        for field in ("threshold", "premature", "correct", "timely", "not_triggered", "unknown_first_hit"):
            assert original[field] == derived[field]


def test_missing_dual_evidence_is_indeterminate_never_imputed_or_dropped(recorded):
    episodes, results, kwargs = population(recorded)
    results[0]["trace"][8]["measurement"].pop("legacy")
    table = sensitivity_table(episodes, results, **kwargs)
    assert all(cell["status"] == "indeterminate" and cell["expected"] == 5 and cell["errors"] == 1 for cell in table["cells"])
    assert all(cell["diagnostic_threshold"] is None and not cell["would_freeze_threshold"] for cell in table["cells"])


def test_versioned_metrics_bind_contract_preserve_main_score_and_expose_interval(recorded):
    episodes, results, kwargs = population(recorded)
    result, episode = results[0], episodes[0]
    score = metrics.score_episode(episode, result, evaluation_contract=kwargs["evaluation_contract"])
    assert score["compliant_finish"] is None and score["scoring_status"] == "not_applicable"
    assert score["metrics_version"] == "remaining-finish-contract-v2"
    assert score["timing_diagnostic"]["first_hit_status"] == "not_triggered"
    assert score["timing_diagnostic"]["tau_low"] == score["timing_diagnostic"]["tau_high"] == 8
    assert score["timing_diagnostic"]["timely"] is False
    summary = metrics.summarize(episodes, results[:-1], mode="shadow", evaluation_contract=kwargs["evaluation_contract"])
    assert summary["schema_version"] == "remaining-finish-summary-v2"
    assert summary["counts"]["expected"] == 5 and summary["counts"]["missing"] == 1
    assert summary["counts"]["successful"] is None
    with pytest.raises(ValueError): metrics.score_episode(episode, result, evaluation_contract=kwargs["evaluation_contract"], stable_steps=3)


@pytest.mark.parametrize("uncertain", [False, True])
def test_active_metrics_keep_main_contract_with_separate_robust_timing(recorded, uncertain):
    from tests.test_finish_versioned_workflow import GeometryEnvironment
    from tests.test_finish_runner import Policy
    from benchmark.remaining_goals.finish.runner import run_finish_episode
    from benchmark.remaining_goals.finish.environment import TARGETS
    class TimingEnvironment(GeometryEnvironment):
        def step(self, action):
            obs = super().step(action)
            if uncertain and self.steps >= 4:
                for name in TARGETS: self.native.membership[name] = True
                self.native.contacts.clear()
                if self.steps in (4, 5, 6, 7, 9): self.native.contacts.add("soup")
            return obs
    episode = deepcopy(recorded[0][0])
    episode.update(horizon=16, retention_steps=6)
    env = TimingEnvironment({"evaluation_contract": evaluation_contract()})
    try:
        result = run_finish_episode(env, Policy(finish_at=8), episode, horizon=16, retention_steps=6,
                                    evaluation_contract=evaluation_contract())
    finally:
        env.close()
    assert result["status"] == "completed" and result["finish_step"] == 8
    score = metrics.score_episode(episode, result, evaluation_contract=evaluation_contract())
    assert score["compliant_finish"] is True and score["scoring_status"] == "scored"
    diagnostic = score["timing_diagnostic"]
    assert diagnostic["timing_unknown"] is uncertain
    assert diagnostic["timely"] is (None if uncertain else True)
    assert (diagnostic["tau_low"], diagnostic["tau_high"]) == ((4, 10) if uncertain else (8, 8))
    assert diagnostic["delay_steps_interval"] == ({"minimum": -2, "maximum": 4} if uncertain else {"minimum": 0, "maximum": 0})
    # Same current truth under the old scoring contract: the main score and
    # existing scalar diagnostics stay unchanged; interval timing is separate.
    old = deepcopy(result)
    old.update(schema_version="remaining-finish-episode-v1")
    old.pop("evaluation_contract"); old.pop("measurement_static")
    for frame in old["trace"]: frame.pop("measurement")
    legacy_score = metrics.score_episode(episode, old)
    for key, value in legacy_score.items():
        if key != "metrics_version": assert score[key] == value
