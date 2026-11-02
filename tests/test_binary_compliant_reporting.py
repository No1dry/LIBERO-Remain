"""Report-only contracts: binary mapping, fixed population and source integrity."""
from copy import deepcopy
import hashlib
import importlib
import json

import pytest


def api():
    # A missing implementation is an explicit behavioral failure during RED.
    try:
        return importlib.import_module("libero_remain_reporting")
    except ModuleNotFoundError:
        pytest.fail("binary report mapping is not implemented")


def population(counts):
    return [{"episode_id": f"{task}_{i}", "task_id": task, "suite": "libero_10",
             "initial_state_index": i, "initial_mask": [True, False]}
            for task, size in counts.items() for i in range(size)]


def verified(tmp_path, episodes, classes):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    evidence = source / "evidence.json"
    evidence.write_text('{"released": null}', encoding="utf-8")
    reference = {"path": str(evidence), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    result = []
    for episode, classification in zip(episodes, classes):
        row = {**episode, "classification": classification,
               "execution_status": "completed" if classification in {"success", "failure", "unknown"} else classification,
               "success": True if classification == "success" else False if classification == "failure" else None,
               "unknown_reasons": ["completion_release_unknown"] if classification == "unknown" else [],
               "failure_reasons": [], "released": None, "n_steps": 520,
               "official_goals_achieved": True, "path_length_m": 1.0}
        result.append({"condition": "10", "primary": row, "legacy": deepcopy(row),
                       "source": {"input_evidence_level": "verified_fixture", "run_path": str(source), "verified_files": [reference]}})
    return result


def test_binary_maps_only_completed_classes_and_preserves_diagnostics(tmp_path):
    episodes = population({"a": 3})
    records = verified(tmp_path, episodes, ["success", "failure", "unknown"])
    before = deepcopy(records)
    report = api().map_verified_results(episodes, records)
    assert [r["outcome"] for r in report["episodes"]] == ["success", "unsuccessful", "unsuccessful"]
    assert [r["success"] for r in report["episodes"]] == [True, False, False]
    assert report["counts"]["formal_SR"] == {"numerator": 1, "denominator": 3, "percent": 100 / 3}
    assert report["episodes"][2]["diagnostics"]["primary"]["released"] is None
    assert report["episodes"][2]["diagnostics"]["primary"]["unknown_reasons"] == ["completion_release_unknown"]
    assert records == before


def test_nine_task_22_of_90_and_equal_task_macro(tmp_path):
    episodes = population({str(i): 10 for i in range(9)})
    records = verified(tmp_path, episodes, ["success"] * 22 + ["failure"] * 67 + ["unknown"])
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["successes"] == 22
    assert report["counts"]["unsuccessful"] == 68
    assert report["counts"]["formal_SR"]["denominator"] == 90
    assert report["counts"]["formal_SR"]["percent"] == pytest.approx(24.44444444)
    assert report["macro"]["formal_SR_percent"] == pytest.approx(24.44444444)
    assert report["tasks"][2]["formal_SR"]["numerator"] == 2


def test_incomplete_progress_has_no_formal_score_or_binary_imputation(tmp_path):
    episodes = population({"a": 4})
    records = verified(tmp_path, episodes[:3], ["success", "technical_error", "running"])
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["formal_SR"] is None
    assert report["macro"]["formal_SR_percent"] is None
    assert report["counts"]["live_completed_SR"] == {"numerator": 1, "denominator": 1, "percent": 100.0}
    assert report["counts"]["completion"] == {"numerator": 1, "denominator": 4, "percent": 25.0}
    assert [r["outcome"] for r in report["episodes"]] == ["success", None, None, None]
    assert {e["code"] for e in report["integrity_errors"]} >= {"technical_error", "running", "missing_episode"}


def test_duplicate_missing_unplanned_and_corrupt_records_are_reported(tmp_path):
    episodes = population({"a": 2})
    records = verified(tmp_path, episodes[:1], ["success"])
    records += deepcopy(records)
    records += verified(tmp_path, population({"foreign": 1}), ["success"])
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["completed"] == 0
    assert {e["code"] for e in report["integrity_errors"]} >= {"duplicate_episode", "missing_episode", "unplanned_episode"}
    with pytest.raises(ValueError, match="duplicate planned"):
        api().map_verified_results(episodes + episodes, [])
    with pytest.raises(ValueError, match="overlap"):
        api().write_report(report, tmp_path / "source" / "derived")


def test_unbound_and_changed_evidence_cannot_supply_success(tmp_path):
    episodes = population({"a": 1})
    records = verified(tmp_path, episodes, ["success"])
    (tmp_path / "source" / "evidence.json").write_text("changed", encoding="utf-8")
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["completed"] == 0
    assert report["episodes"][0]["success"] is None
    assert report["integrity_errors"][0]["code"] == "source_integrity_error"
    records[0]["source"]["verified_files"] = []
    assert api().map_verified_results(episodes, records)["counts"]["completed"] == 0


def test_macro_is_equal_task_and_suppressed_when_any_task_incomplete(tmp_path):
    episodes = population({"a": 1, "b": 3})
    records = verified(tmp_path, episodes, ["success", "failure", "failure", "failure"])
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["formal_SR"]["percent"] == 25.0
    assert report["macro"]["formal_SR_percent"] == 50.0
    assert api().map_verified_results(episodes, records[:-1])["macro"]["formal_SR_percent"] is None


def test_different_method_adapters_cannot_aggregate_as_one_model(tmp_path):
    episodes = population({"a": 2})
    records = verified(tmp_path, episodes, ["success", "success"])
    for record, adapter in zip(records, ("adapter-a", "adapter-b")):
        record["source"]["model_identity"] = {"policy_metadata": {
            "unnorm_key": "libero_10_no_noops", "method_adapter": {"sha256": adapter}}}
    report = api().map_verified_results(episodes, records)
    assert report["counts"]["formal_SR"] is None
    assert report["counts"]["live_completed_SR"] is None
    assert report["macro"]["formal_SR_percent"] is None
    assert any(issue["code"] == "model_identity_mismatch" for issue in report["integrity_errors"])


def test_new_output_directory_and_markdown_do_not_rewrite_sources(tmp_path):
    episodes = population({"a": 3})
    records = verified(tmp_path, episodes, ["success", "failure", "unknown"])
    report = api().map_verified_results(episodes, records)
    before = (tmp_path / "source" / "evidence.json").read_bytes()
    out = tmp_path / "new"
    api().write_report(report, out)
    saved = json.loads((out / "summary.json").read_text())
    assert saved["episodes"][2]["outcome"] == "unsuccessful"
    markdown = (out / "report.md").read_text()
    assert "33.33% (1/3)" in markdown
    assert "Unknown |" not in markdown
    assert (tmp_path / "source" / "evidence.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        api().write_report(report, out)
    with pytest.raises(ValueError, match="overlap"):
        api().write_report(report, tmp_path / "source" / "new")
