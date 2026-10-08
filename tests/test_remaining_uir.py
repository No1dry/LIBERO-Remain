"""Synthetic human-label contracts; none of these labels is a real review."""
from copy import deepcopy
import json

import pytest

from benchmark.remaining_goals.metrics import summarize_results
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.uir import make_annotation_template, summarize_annotations


def fixture(specs=(("A", "10"), ("A", "01"), ("A", "00"), ("A", "11"))):
    episodes = []
    for index, (task, mask) in enumerate(specs):
        episodes.append({"episode_id": f"synthetic_{index}", "task_id": task, "suite": "toy",
                         "initial_mask": [bit == "1" for bit in mask], "horizon": 2, "retention_steps": 2,
                         "state_sha256": "a" * 64})
    manifest = {"environment": {"name": "toy"}, "episodes": episodes}
    metadata = {"run_id": "synthetic-run", "manifest_hash": manifest_hash(manifest),
                "policy_id": "synthetic-policy", "run_config_sha256": "b" * 64}
    results = []
    for index, episode in enumerate(episodes):
        final = 2 if all(episode["initial_mask"]) else 4
        rows = [{"step": step, "goals": episode["initial_mask"] if not step else [True] * len(episode["initial_mask"]),
                 "action": None if not step else [float(step)] * 7, "stopped": False}
                for step in range(final + 1)]
        results.append({**deepcopy(episode), **metadata, "status": "completed", "n_steps": final, "trace": rows,
                        "video": {"status": "saved", "path": f"videos/{index:06d}.mp4", "error": None,
                                  "frames": final + 1, "frame_steps": list(range(final + 1)), "stride": 1,
                                  "episode_id": episode["episode_id"]}})
    return metadata, manifest, results


def labels(metadata, manifest, results, values):
    annotations = make_annotation_template(metadata, manifest, results)
    for row, result, value in zip(annotations["annotations"], results, values):
        if value == "unreviewed":
            continue
        row.update(unnecessary_intervention=value, review_status="reviewed", reviewer="SYNTHETIC reviewer",
                   reason="SYNTHETIC test label, not a claim of actual human video review",
                   reviewed_full_episode=value is not None,
                   evidence=[{"video_path": result["video"]["path"], "start_step": 0, "end_step": result["n_steps"]}]
                   if value is not None else [])
    return annotations


def test_template_is_unreviewed_not_negative_and_marks_synthetic():
    args = fixture()
    template = make_annotation_template(*args)
    assert template["synthetic"] is True
    assert all(row["unnecessary_intervention"] is None and row["reviewer"] == ""
               and row["review_status"] == "unreviewed" and row["reviewed_full_episode"] is False
               and row["evidence"] == [] for row in template["annotations"])
    assert [row["context"]["scheduled_final_step"] for row in template["annotations"]] == [4, 4, 4, 2]
    report = summarize_annotations(*args, template)
    assert report["counts"]["annotated"] == report["counts"]["unknown"] == 0
    assert report["counts"]["unannotated"] == 4
    assert report["counts"]["rate"] is None and report["partial_macro"]["rate"] is None


def test_unknown_and_missing_annotations_never_enter_denominator():
    args = fixture()
    annotations = labels(*args, [True, False, None, "unreviewed"])
    annotations["annotations"].pop()
    report = summarize_annotations(*args, annotations)
    counts = report["counts"]
    assert (counts["numerator"], counts["denominator"], counts["rate"]) == (1, 2, .5)
    assert (counts["annotated"], counts["unknown"], counts["unannotated"], counts["ineligible"]) == (2, 1, 1, 0)
    assert counts["coverage"] == counts["eligible_coverage"] == .5
    assert report["partial_macro"]["rate"] == .5
    assert report["normal_00"]["rate"] is None and report["terminal_11"]["rate"] is None


def test_partial_macro_equal_masks_then_equal_tasks_not_pooled_episodes():
    specs = [("A", "10"), *[("A", "01")] * 9, ("B", "10"), ("B", "01"), ("A", "00"), ("A", "11")]
    args = fixture(specs)
    annotations = labels(*args, [True, *[False] * 11, True, True])
    report = summarize_annotations(*args, annotations)
    assert report["partial_macro"]["rate"] == .25
    assert report["partial_macro"]["micro_rate"] == pytest.approx(1 / 12)
    assert report["partial_macro"]["expected"] == 12
    assert report["normal_00"]["rate"] == report["terminal_11"]["rate"] == 1
    assert {row["mask"] for row in report["by_mask"]} == {"00", "10", "01", "11"}
    annotations["annotations"][10].update(unnecessary_intervention=None, reviewed_full_episode=False)
    report = summarize_annotations(*args, annotations)
    assert report["partial_macro"]["rate"] is None
    assert report["partial_macro"]["covered_task_masks"] == 3


def test_one_labeled_episode_per_expected_cell_is_enough_with_visible_coverage():
    args = fixture([("A", "10"), ("A", "10"), ("A", "01")])
    report = summarize_annotations(*args, labels(*args, [False, None, True]))
    assert report["partial_macro"]["rate"] == .5
    assert report["counts"]["coverage"] == pytest.approx(2 / 3)


def test_errors_missing_and_unknown_partition_counts_without_false_labels():
    metadata, manifest, results = fixture()
    results[1].update(status="runtime_error", n_steps=1, trace=results[1]["trace"][:2], video=None)
    results[2].update(status="invalid_initial_state", n_steps=0, trace=[], video=None)
    results.pop()
    args = metadata, manifest, results
    annotations = make_annotation_template(*args)
    row = annotations["annotations"][0]
    row.update(review_status="reviewed", reviewer="SYNTHETIC", reason="Object not identifiable")
    report = summarize_annotations(*args, annotations)
    counts = report["counts"]
    assert counts["expected"] == 4 and counts["completed"] == 1 and counts["ineligible"] == 3
    assert counts["runtime_error"] == counts["invalid_initial_state"] == counts["missing"] == 1
    assert counts["unknown"] == 1 and counts["annotated"] == counts["unannotated"] == 0
    assert counts["rate"] is None and counts["coverage"] == counts["eligible_coverage"] == 0
    assert counts["expected"] == sum(counts[key] for key in ("annotated", "unknown", "unannotated", "ineligible"))


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("manifest_hash", "c" * 64)])
def test_annotation_cannot_borrow_same_episode_from_another_run(field, value):
    args = fixture()
    annotations = labels(*args, [False] * 4)
    annotations[field] = value
    with pytest.raises(ValueError, match="run_id/manifest_hash"):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("field,value", [
    ("run_id", "another"), ("manifest_hash", "d" * 64), ("suite", "libero_90"),
    ("policy_id", "another"), ("run_config_sha256", "d" * 64), ("state_sha256", "d" * 64),
    ("task_id", "another"), ("initial_mask", [False, True]), ("n_steps", 3), ("n_steps", True),
])
def test_result_identity_and_execution_must_match(field, value):
    args = fixture()
    args[2][0][field] = value
    with pytest.raises(ValueError):
        make_annotation_template(*args)


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "bad_start"])
def test_completed_label_requires_a_complete_valid_trace(tamper):
    args = fixture()
    rows = args[2][0]["trace"]
    if tamper == "missing":
        rows.pop()
    elif tamper == "duplicate":
        rows[2]["step"] = 1
    else:
        rows[0]["goals"] = [False, False]
    with pytest.raises(ValueError):
        make_annotation_template(*args)


@pytest.mark.parametrize("label", [0, 1, "false", "true", [], {}, 0.0])
def test_truthy_nonboolean_labels_are_rejected(label):
    args = fixture()
    annotations = labels(*args, [False] * 4)
    annotations["annotations"][0]["unnecessary_intervention"] = label
    with pytest.raises(ValueError, match="JSON boolean or null"):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("field,value", [
    ("reviewed_full_episode", 1), ("reviewed_full_episode", False),
    ("review_status", "unreviewed"), ("review_status", "accepted"), ("reviewer", " "), ("reason", ""),
])
def test_boolean_labels_need_explicit_complete_human_review(field, value):
    args = fixture()
    annotations = labels(*args, [False] * 4)
    annotations["annotations"][0][field] = value
    with pytest.raises(ValueError):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("label", [True, False])
@pytest.mark.parametrize("defect", ["sparse", "failed_encoder", "wrong_count", "bad_stride", "wrong_episode", "step_bool", "duplicate_frame"])
def test_any_boolean_label_requires_all_frames_from_this_episode(label, defect):
    args = fixture()
    annotations = labels(*args, [label] * 4)
    movie = args[2][0]["video"]
    if defect == "sparse":
        movie.update(frame_steps=[0, 2, 4], frames=3, stride=2)
    elif defect == "failed_encoder":
        movie.update(status="video_error", error="encoder failed")
    elif defect == "wrong_count":
        movie["frames"] = 6
    elif defect == "bad_stride":
        movie["stride"] = 2
    elif defect == "wrong_episode":
        movie["episode_id"] = "other"
    elif defect == "step_bool":
        movie["frame_steps"][0] = False
    else:
        movie["frame_steps"][1] = 0
    with pytest.raises(ValueError):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("evidence", [
    [], [{"video_path": "videos/000000.mp4", "start_step": 1, "end_step": 4}],
    [{"video_path": "videos/000000.mp4", "start_step": 0, "end_step": 2}],
    [{"video_path": "videos/000000.mp4", "start_step": 0, "end_step": 1},
     {"video_path": "videos/000000.mp4", "start_step": 3, "end_step": 4}],
])
def test_full_review_must_cover_initial_and_entire_retention_window(evidence):
    args = fixture()
    annotations = labels(*args, [True] * 4)
    annotations["annotations"][0]["evidence"] = evidence
    with pytest.raises(ValueError, match="full episode window"):
        summarize_annotations(*args, annotations)


def test_full_window_plus_multiple_events_still_counts_one_episode():
    args = fixture()
    annotations = labels(*args, [True, False, False, False])
    annotations["annotations"][0]["evidence"].extend([
        {"video_path": "videos/000000.mp4", "start_step": 2, "end_step": 3},
        {"video_path": "videos/000000.mp4", "start_step": 3, "end_step": 4}])
    assert summarize_annotations(*args, annotations)["counts"]["numerator"] == 1


@pytest.mark.parametrize("path", ["../videos/000000.mp4", "/videos/000000.mp4", "C:\\other\\video.mp4",
                                   "videos\\..\\000000.mp4", "https://example.com/video.mp4", "videos/000001.mp4"])
def test_evidence_paths_must_match_this_episode_inside_the_run(path):
    args = fixture()
    annotations = labels(*args, [True] * 4)
    annotations["annotations"][0]["evidence"][0]["video_path"] = path
    with pytest.raises(ValueError):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("start,end", [(-1, 4), (0, 5), (3, 2), (False, 4), (0, True), (0, 4.0)])
def test_evidence_physical_steps_are_bounded_integers(start, end):
    args = fixture()
    annotations = labels(*args, [True] * 4)
    annotations["annotations"][0]["evidence"][0].update(start_step=start, end_step=end)
    with pytest.raises(ValueError):
        summarize_annotations(*args, annotations)


def test_unknown_can_record_partial_sparse_evidence_without_entering_uir():
    args = fixture()
    args[2][0]["video"].update(frame_steps=[0, 2, 4], frames=3, stride=2)
    annotations = labels(*args, [None, False, False, False])
    annotations["annotations"][0]["evidence"] = [{"video_path": "videos\\000000.mp4", "start_step": 0, "end_step": 2}]
    report = summarize_annotations(*args, annotations)
    assert report["counts"]["unknown"] == 1 and report["counts"]["denominator"] == 3
    assert report["partial_macro"]["rate"] is None


def test_missing_and_error_results_cannot_receive_boolean_labels():
    args = fixture()
    annotations = labels(*args, [True] * 4)
    args[2][0].update(status="runtime_error", n_steps=1, trace=args[2][0]["trace"][:2])
    with pytest.raises(ValueError, match="completed valid rollout"):
        summarize_annotations(*args, annotations)
    args[2].pop(0)
    with pytest.raises(ValueError, match="completed valid rollout"):
        summarize_annotations(*args, annotations)


@pytest.mark.parametrize("defect", ["annotation_duplicate", "annotation_unknown", "result_duplicate", "manifest_duplicate", "video_reused"])
def test_duplicate_or_foreign_episode_evidence_is_rejected(defect):
    args = fixture()
    annotations = labels(*args, [True] * 4)
    if defect == "annotation_duplicate":
        annotations["annotations"].append(deepcopy(annotations["annotations"][0]))
    elif defect == "annotation_unknown":
        annotations["annotations"][0]["episode_id"] = "other"
    elif defect == "result_duplicate":
        args[2].append(deepcopy(args[2][0]))
    elif defect == "manifest_duplicate":
        args[1]["episodes"].append(deepcopy(args[1]["episodes"][0]))
        args[0]["manifest_hash"] = manifest_hash(args[1])
    else:
        args[2][1]["video"]["path"] = args[2][0]["video"]["path"]
    with pytest.raises(ValueError):
        summarize_annotations(*args, annotations)


def test_suite_mixing_and_manifest_identity_changes_are_rejected():
    args = fixture()
    args[1]["episodes"][0]["suite"] = "libero_90"
    args[0]["manifest_hash"] = manifest_hash(args[1])
    with pytest.raises(ValueError, match="one suite"):
        make_annotation_template(*args)
    args = fixture()
    args[1]["episodes"][0]["horizon"] += 1
    with pytest.raises(ValueError, match="manifest_hash"):
        make_annotation_template(*args)


def test_annotations_are_independent_of_actions_and_old_scores_are_unchanged():
    args = fixture()
    annotations = labels(*args, [False, True, False, True])
    before = deepcopy((*args, annotations))
    scores = summarize_results(args[1]["episodes"], args[2])
    report = summarize_annotations(*args, annotations)
    assert scores == summarize_results(args[1]["episodes"], args[2])
    assert before == (*args, annotations)
    assert report["counts"]["rate"] == .5
    assert all(row["valid_metrics"]["joint_success"]["rate"] == 1 for row in scores["by_task_mask"])
    assert report["synthetic"] is True
    json.dumps(report, allow_nan=False)
    changed = deepcopy(annotations)
    changed["annotations"][0]["reason"] += " clarified"
    other = summarize_annotations(*args, changed)
    assert report["annotation_sha256"] != other["annotation_sha256"]
    reordered = {key: annotations[key] for key in reversed(annotations)}
    assert report["annotation_sha256"] == summarize_annotations(*args, reordered)["annotation_sha256"]


def test_synthetic_examples_cannot_be_presented_as_real_human_labels():
    args = fixture()
    annotations = labels(*args, [False] * 4)
    annotations["synthetic"] = False
    with pytest.raises(ValueError, match="synthetic=true"):
        summarize_annotations(*args, annotations)


def test_reviewed_unknown_on_incomplete_episode_cannot_claim_full_episode_review():
    args = fixture()
    annotations = labels(*args, [None] * 4)
    annotations["annotations"][0]["reviewed_full_episode"] = True
    args[2][0].update(status="runtime_error", n_steps=1, trace=args[2][0]["trace"][:2])
    with pytest.raises(ValueError, match="completed valid rollout"):
        summarize_annotations(*args, annotations)


def test_three_goal_partial_strata_exclude_only_all_zero_and_all_one():
    args = fixture([("A", "000"), ("A", "100"), ("A", "011"), ("A", "111")])
    report = summarize_annotations(*args, labels(*args, [True, False, False, True]))
    assert report["partial_macro"]["rate"] == 0
    assert report["partial_macro"]["expected_task_masks"] == 2
    assert report["normal_00"]["rate"] == report["terminal_11"]["rate"] == 1
