"""Selection-aware reports and human-label denominators, with synthetic traces."""
from copy import deepcopy

import pytest

from benchmark.remaining_goals.metrics import summarize_results
from benchmark.remaining_goals.reporting import build_display, render_report
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.selection import build_selection, selected_episodes
from benchmark.remaining_goals.uir import make_annotation_template, summarize_annotations
from .test_remaining_selection import make_manifest


def selected_fixture(*, masks=("10", "01", "11"), mode="original", sources=2):
    manifest = make_manifest(sources=sources)
    selection = build_selection(manifest, masks=list(masks), instruction_mode=mode)
    metadata = {"run_id": "SYNTHETIC-run", "manifest_hash": manifest_hash(manifest),
                "policy_id": "SYNTHETIC-policy", "run_config_sha256": "b" * 64,
                "execution_selection": selection}
    results = []
    for index, (episode, instruction) in enumerate(zip(selected_episodes(manifest, metadata), selection["episodes"])):
        final = 2 if all(episode["initial_mask"]) else 4
        result = {**deepcopy(episode), **{key: metadata[key] for key in
                                       ("run_id", "manifest_hash", "policy_id", "run_config_sha256")},
                  "selection_sha256": selection["selection_sha256"], "instruction_mode": mode,
                  "effective_instruction": instruction["effective_instruction"],
                  "status": "completed", "n_steps": final,
                  "trace": [{"step": step, "goals": episode["initial_mask"] if step == 0 else [True, True],
                             "action": None if step == 0 else [0.] * 7, "stopped": False} for step in range(final + 1)],
                  "video": {"status": "saved", "path": f"videos/{index:06d}.mp4", "error": None,
                            "frames": final + 1, "frame_steps": list(range(final + 1)), "stride": 1}}
        results.append(result)
    return metadata, manifest, results


def mark_labels(metadata, manifest, results, labels):
    annotations = make_annotation_template(metadata, manifest, results)
    for row, result, label in zip(annotations["annotations"], results, labels):
        row.update(unnecessary_intervention=label, review_status="reviewed", reviewer="SYNTHETIC reviewer",
                   reason="SYNTHETIC label; no real video was reviewed", reviewed_full_episode=label is not None,
                   evidence=[{"video_path": result["video"]["path"], "start_step": 0, "end_step": result["n_steps"]}]
                   if label is not None else [])
    return annotations


def test_selected_template_binds_source_and_selection_without_unselected_rows():
    metadata, manifest, results = selected_fixture()
    before = deepcopy((metadata, manifest, results))
    template = make_annotation_template(metadata, manifest, results)
    assert len(template["annotations"]) == 6
    assert template["selection_sha256"] == metadata["execution_selection"]["selection_sha256"]
    assert template["manifest_hash"] == manifest_hash(manifest)
    assert template["source_expected"] == 8
    assert template["not_selected_ids"] == ["basket_s000_00", "basket_s001_00"]
    assert [row["episode_id"] for row in template["annotations"]] == metadata["execution_selection"]["selected_ids"]
    assert all(row["unnecessary_intervention"] is None for row in template["annotations"])
    assert (metadata, manifest, results) == before


def test_missing_selected_mask_stays_in_macro_denominator_but_00_is_not_missing():
    metadata, manifest, results = selected_fixture(sources=1)
    missing_id = next(row["episode_id"] for row in results if row["initial_mask"] == [True, False])
    results = [row for row in results if row["episode_id"] != missing_id]
    # Template includes the missing row; explicitly label only present result identities.
    annotations = make_annotation_template(metadata, manifest, results)
    for row in annotations["annotations"]:
        result = next((item for item in results if item["episode_id"] == row["episode_id"]), None)
        if result is not None:
            row.update(unnecessary_intervention=False, review_status="reviewed", reviewed_full_episode=True,
                       reviewer="SYNTHETIC", reason="SYNTHETIC full review",
                       evidence=[{"video_path": result["video"]["path"], "start_step": 0, "end_step": result["n_steps"]}])
    report = summarize_annotations(metadata, manifest, results, annotations)
    assert report["counts"]["expected"] == 3 and report["counts"]["missing"] == 1
    assert report["counts"]["annotated"] == 2 and report["counts"]["coverage"] == pytest.approx(2 / 3)
    assert report["partial_macro"]["expected_task_masks"] == 2
    assert report["partial_macro"]["covered_task_masks"] == 1
    assert report["partial_macro"]["rate"] is None
    assert report["normal_00"]["expected"] == 0
    assert {row["mask"] for row in report["by_task_mask"]} == {"01", "10", "11"}


def test_selected_unknown_error_and_missing_are_distinct():
    metadata, manifest, results = selected_fixture(sources=1)
    results[1].update(status="runtime_error", n_steps=1, trace=results[1]["trace"][:2], video=None)
    results.pop()
    annotations = make_annotation_template(metadata, manifest, results)
    annotations["annotations"][0].update(review_status="reviewed", reviewer="SYNTHETIC", reason="Necessary information unclear")
    report = summarize_annotations(metadata, manifest, results, annotations)
    counts = report["counts"]
    assert counts["expected"] == 3 and counts["completed"] == 1
    assert counts["runtime_error"] == counts["missing"] == counts["unknown"] == 1
    assert counts["annotated"] == 0 and counts["rate"] is None and counts["coverage"] == 0


@pytest.mark.parametrize("field,value", [("selection_sha256", "f" * 64), ("instruction_mode", "oracle-remaining-initial"),
                                        ("effective_instruction", "changed language"), ("instruction", "changed source")])
def test_selected_results_cannot_change_execution_identity(field, value):
    metadata, manifest, results = selected_fixture(sources=1)
    results[0][field] = value
    with pytest.raises(ValueError):
        make_annotation_template(metadata, manifest, results)
    summary = summarize_results(selected_episodes(manifest, metadata), results)
    with pytest.raises(ValueError):
        build_display(manifest, results, summary, metadata=metadata)


def test_unselected_result_or_label_is_not_silently_ignored():
    metadata, manifest, results = selected_fixture(sources=1)
    extra = deepcopy(results[0])
    extra["episode_id"] = metadata["execution_selection"]["not_selected_ids"][0]
    with pytest.raises(ValueError, match="unknown"):
        make_annotation_template(metadata, manifest, [*results, extra])
    annotations = make_annotation_template(metadata, manifest, results)
    annotations["annotations"][0]["episode_id"] = extra["episode_id"]
    with pytest.raises(ValueError, match="known"):
        summarize_annotations(metadata, manifest, results, annotations)


@pytest.mark.parametrize("field,value", [("selection_sha256", "f" * 64), ("instruction_mode", "oracle-remaining-initial"),
                                        ("source_expected", True), ("not_selected_ids", [])])
def test_annotations_cannot_borrow_a_different_selection(field, value):
    metadata, manifest, results = selected_fixture(sources=1)
    annotations = make_annotation_template(metadata, manifest, results)
    annotations[field] = value
    with pytest.raises(ValueError, match="execution selection"):
        summarize_annotations(metadata, manifest, results, annotations)


def test_display_recomputes_selected_denominators_even_if_given_old_full_summary():
    metadata, manifest, results = selected_fixture(sources=1)
    old_summary = summarize_results(manifest["episodes"], results)
    assert old_summary["counts"]["missing"] == 1
    before = deepcopy((metadata, manifest, results, old_summary))
    report = build_display(manifest, results, old_summary, metadata=metadata)
    assert {row["mask"] for row in report["main"]} == {"01", "10", "11"}
    assert len(report["main"]) == 3
    assert sum(row["expected"] for row in report["diagnostics"]) == 3
    assert sum(row["missing"] for row in report["diagnostics"]) == 0
    assert all(row["unnecessary_intervention_rate"] is None for row in report["main"])
    rendered = render_report(report)
    assert "Selected expected: 3 / source episodes: 4" in rendered
    assert "Not selected: 1" in rendered
    assert "ORACLE DIAGNOSTIC" not in rendered
    assert (metadata, manifest, results, old_summary) == before


def test_oracle_display_and_annotation_binding_cannot_masquerade_as_main():
    metadata, manifest, results = selected_fixture(masks=("10", "01"), mode="oracle-remaining-initial", sources=1)
    annotations = mark_labels(metadata, manifest, results, [False, True])
    uir = summarize_annotations(metadata, manifest, results, annotations)
    summary = summarize_results(selected_episodes(manifest, metadata), results)
    display = build_display(manifest, results, summary, metadata=metadata, uir=uir)
    assert display["diagnostic"] is True and display["purpose"] == "oracle-remaining-initial-diagnostic"
    assert {row["mask"] for row in display["main"]} == {"10", "01"}
    text = render_report(display)
    assert "ORACLE DIAGNOSTIC" in text and "separate from main results" in text
    assert "Not an original-instruction baseline" in text and "performance upper bound" in text
    assert "## Main results" not in text
    altered = deepcopy(uir)
    altered["selection_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="UIR report"):
        build_display(manifest, results, summary, metadata=metadata, uir=altered)


def test_legacy_all_report_remains_identical_with_or_without_metadata_argument():
    metadata, manifest, results = selected_fixture(masks=("00", "01", "10", "11"), sources=1)
    metadata.pop("execution_selection")
    for result in results:
        for key in ("selection_sha256", "instruction_mode", "effective_instruction"):
            result.pop(key)
    annotations = mark_labels(metadata, manifest, results, [False] * 4)
    uir = summarize_annotations(metadata, manifest, results, annotations)
    summary = summarize_results(manifest["episodes"], results)
    legacy = build_display(manifest, results, summary, uir=uir)
    explicit = build_display(manifest, results, summary, uir=uir, metadata=metadata)
    assert legacy == explicit and render_report(legacy) == render_report(explicit)
    assert len(legacy["main"]) == 7
    assert "selection_sha256" not in annotations and "selection_sha256" not in uir
    assert "selection" not in legacy and "diagnostic" not in legacy
