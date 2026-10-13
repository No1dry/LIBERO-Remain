"""Validate and summarize independent human UIR annotations without writing runs.

No action, gripper, STOP, predicate transition, or contact creates a UIR label.
The checks validate evidence declarations, not whether a human actually watched
the video or correctly judged necessity. The CLI must additionally verify the
referenced files exist inside the source run and record their byte hashes.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
from statistics import mean

from .metrics import summarize_results
from .schema import manifest_hash
from .selection import selected_episodes


SCHEMA_VERSION = "remaining-goals-uir-annotations-v1"


def _text(value, name, *, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{name} must be {'a' if allow_empty else 'a nonempty'} string")
    return value


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, not a boolean")
    return value


def _canonical_hash(value):
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("annotations must contain only finite JSON values") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _path(value):
    _text(value, "video_path")
    portable = value.replace("\\", "/")
    windows, posix = PureWindowsPath(value), PurePosixPath(portable)
    if (windows.drive or windows.root or posix.is_absolute() or "//" in portable
            or any(part in ("", ".", "..") or ":" in part or part.endswith((" ", "."))
                   for part in portable.split("/"))
            or posix.suffix.lower() != ".mp4"):
        raise ValueError("video_path must be a contained relative MP4 path")
    return posix.as_posix()


def _context(metadata, manifest, results):
    if not isinstance(metadata, dict) or not isinstance(manifest, dict):
        raise ValueError("metadata and manifest must be JSON objects")
    run_id = _text(metadata.get("run_id"), "run_id")
    expected_hash = manifest_hash(manifest)
    if metadata.get("manifest_hash") != expected_hash:
        raise ValueError("run metadata manifest_hash differs from the supplied manifest")
    if "content_hash" in manifest and manifest["content_hash"] != expected_hash:
        raise ValueError("manifest content_hash mismatch")
    episodes = selected_episodes(manifest, metadata)
    # Reuse the unchanged scorer's complete trace, mask, task and status checks.
    summarize_results(episodes, results)
    if not episodes:
        raise ValueError("UIR requires a nonempty manifest")
    suites = {_text(episode.get("suite"), "episode.suite") for episode in episodes}
    if len(suites) != 1:
        raise ValueError("UIR requires one suite; summarize LIBERO-10 and LIBERO-90 separately")
    expected = {episode["episode_id"]: episode for episode in episodes}
    selection = metadata.get("execution_selection")
    instructions = {row["episode_id"]: row for row in selection["episodes"]} if selection else {}
    found, video_paths = {}, {}
    for result in results:
        identifier = result["episode_id"]
        episode = expected[identifier]
        for key, value in (("run_id", run_id), ("manifest_hash", expected_hash), ("suite", episode["suite"])):
            if result.get(key) != value:
                raise ValueError(f"result {identifier} does not match {key}")
        for source, key in ((metadata, "policy_id"), (metadata, "run_config_sha256"), (episode, "state_sha256"),
                            (episode, "task_name"), (episode, "instruction"), (episode, "seed")):
            if key in source and result.get(key) != source[key]:
                raise ValueError(f"result {identifier} does not match {key}")
        if selection:
            for key, value in (("selection_sha256", selection["selection_sha256"]),
                               ("instruction_mode", selection["instruction_mode"]),
                               ("effective_instruction", instructions[identifier]["effective_instruction"])):
                if result.get(key) != value:
                    raise ValueError(f"result {identifier} does not match selection {key}")
        final_step = episode["retention_steps"] + (0 if all(episode["initial_mask"]) else episode["horizon"])
        actual_steps = _integer(result.get("n_steps"), "result.n_steps")
        if actual_steps > final_step or (result["status"] == "completed" and actual_steps != final_step):
            raise ValueError(f"result {identifier} has inconsistent n_steps")
        movie = result.get("video")
        if isinstance(movie, dict) and movie.get("status") == "saved" and movie.get("path"):
            movie_path = _path(movie["path"])
            if movie_path in video_paths:
                raise ValueError("different episodes cannot claim the same saved video_path")
            video_paths[movie_path] = identifier
        found[identifier] = result
    return run_id, expected_hash, next(iter(suites)), expected, found


def _selection_fields(metadata):
    """Expose selection identity without weakening the original run binding."""
    selection = metadata.get("execution_selection")
    if selection is None:
        return {}
    return {key: deepcopy(selection[key]) for key in
            ("selection_sha256", "instruction_mode", "purpose", "source_expected", "not_selected_ids")}


def _video_evidence(episode, result, evidence, *, require_full):
    if not isinstance(evidence, list):
        raise ValueError("annotation.evidence must be a list")
    if not evidence:
        if require_full:
            raise ValueError("a complete review needs video evidence for the full episode window")
        return []
    if result is None:
        raise ValueError("missing episode result cannot supply video evidence")
    movie = result.get("video")
    if (not isinstance(movie, dict) or movie.get("status") != "saved"
            or movie.get("error") is not None):
        raise ValueError("video evidence requires a successfully saved episode video")
    if "episode_id" in movie and movie["episode_id"] != episode["episode_id"]:
        raise ValueError("video episode_id differs from the annotated episode")
    movie_path = _path(movie.get("path"))
    steps = movie.get("frame_steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("video evidence needs explicit physical frame_steps")
    for index, step in enumerate(steps):
        _integer(step, "video.frame_steps")
        if step > result["n_steps"] or (index and step <= steps[index - 1]):
            raise ValueError("video frame_steps must be ordered, unique, and within the actual rollout")
    if type(movie.get("frames")) is not int or movie["frames"] != len(steps):
        raise ValueError("video.frames must match frame_steps")
    if require_full and steps != list(range(result["n_steps"] + 1)):
        raise ValueError("boolean UIR labels require every physical step; sparse video is insufficient")
    if require_full and "stride" in movie and (type(movie["stride"]) is not int or movie["stride"] != 1):
        raise ValueError("boolean UIR labels require video stride=1")
    intervals, normalized = [], []
    frame_steps = set(steps)
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("each evidence item must be an object")
        path = _path(item.get("video_path"))
        if path != movie_path:
            raise ValueError("evidence video_path does not match this run's episode video")
        start = _integer(item.get("start_step"), "evidence.start_step")
        end = _integer(item.get("end_step"), "evidence.end_step")
        if start > end or end > result["n_steps"] or start not in frame_steps or end not in frame_steps:
            raise ValueError("evidence must use available physical steps inside the episode window")
        intervals.append((start, end))
        normalized.append({**deepcopy(item), "video_path": path})
    if require_full:
        covered_until = -1
        for start, end in sorted(intervals):
            if start > covered_until + 1:
                raise ValueError("evidence intervals do not cover the full episode window")
            covered_until = max(covered_until, end)
        if covered_until != result["n_steps"]:
            raise ValueError("evidence intervals do not cover the full episode window")
    return normalized


def make_annotation_template(metadata, manifest, results, *, reviewer="") -> dict:
    """Produce an unreviewed template; no label is inferred from a rollout."""
    run_id, digest, suite, expected, found = _context(metadata, manifest, results)
    _text(reviewer, "reviewer", allow_empty=True)
    rows = []
    for identifier, episode in expected.items():
        result = found.get(identifier)
        movie = result.get("video", {}) if result else {}
        movie = movie if isinstance(movie, dict) else {}
        rows.append({
            "episode_id": identifier, "unnecessary_intervention": None,
            "review_status": "unreviewed", "reviewed_full_episode": False,
            "reviewer": reviewer, "reason": "Not reviewed; null is not a negative label.", "evidence": [],
            "context": {"task_id": episode["task_id"], "suite": suite,
                        "initial_mask": deepcopy(episode["initial_mask"]),
                        "result_status": result["status"] if result else "missing",
                        "scheduled_final_step": episode["retention_steps"] + (0 if all(episode["initial_mask"]) else episode["horizon"]),
                        "video_path": movie.get("path"), "video_status": movie.get("status", "missing")},
        })
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "manifest_hash": digest,
            **_selection_fields(metadata),
            "synthetic": manifest.get("environment", {}).get("name") == "toy",
            "notice": "Human review required. Boolean labels require complete recorded physical-step coverage; unknown remains null.",
            "annotations": rows}


def _counts(items):
    eligible = [item for item in items if item["eligible"]]
    annotated = [item for item in eligible if type(item["unnecessary_intervention"]) is bool]
    numerator = sum(item["unnecessary_intervention"] is True for item in annotated)
    unknown = sum(item["review_status"] == "reviewed" and item["unnecessary_intervention"] is None for item in eligible)
    return {"expected": len(items), "completed": len(eligible), "eligible": len(eligible),
            "invalid_initial_state": sum(item["result_status"] == "invalid_initial_state" for item in items),
            "runtime_error": sum(item["result_status"] == "runtime_error" for item in items),
            "missing": sum(item["result_status"] == "missing" for item in items),
            "ineligible": len(items) - len(eligible), "annotated": len(annotated), "unknown": unknown,
            "unannotated": len(eligible) - len(annotated) - unknown,
            "numerator": numerator, "denominator": len(annotated),
            "rate": numerator / len(annotated) if annotated else None,
            "coverage": len(annotated) / len(items) if items else None,
            "eligible_coverage": len(annotated) / len(eligible) if eligible else None}


def _macro(groups, items):
    by_task = defaultdict(list)
    for group in groups:
        by_task[group["task_id"]].append(group)
    tasks = []
    for task_id, task_groups in sorted(by_task.items()):
        rates = [group["rate"] for group in task_groups]
        tasks.append({"task_id": task_id, "expected_task_masks": len(rates),
                      "covered_task_masks": sum(rate is not None for rate in rates),
                      "rate": mean(rates) if all(rate is not None for rate in rates) else None,
                      "coverage": mean(group["coverage"] for group in task_groups)})
    rates = [task["rate"] for task in tasks]
    counts = _counts(items)
    return {**counts, "micro_rate": counts["rate"],
            "rate": mean(rates) if rates and all(rate is not None for rate in rates) else None,
            "aggregation": "equal masks within each task, then equal tasks; numerator/denominator describe pooled annotations",
            "n_tasks": len(tasks), "expected_task_masks": len(groups),
            "covered_task_masks": sum(group["rate"] is not None for group in groups), "by_task": tasks}


def summarize_annotations(metadata, manifest, results, annotations) -> dict:
    """Return a derived UIR report; never modify metadata, results, or annotations.

    Counts partition expected into annotated + unknown + unannotated + ineligible.
    Only completed valid rollouts can enter the first three categories. Coverage
    is annotated/expected; eligible_coverage is annotated/completed. A macro is
    null if any expected task-mask has no valid boolean annotation.
    """
    run_id, digest, suite, expected, found = _context(metadata, manifest, results)
    if not isinstance(annotations, dict) or annotations.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported UIR annotation schema_version")
    if annotations.get("run_id") != run_id or annotations.get("manifest_hash") != digest:
        raise ValueError("annotation run_id/manifest_hash do not identify this run")
    for key, value in _selection_fields(metadata).items():
        if _canonical_hash(annotations.get(key)) != _canonical_hash(value):
            raise ValueError(f"annotation {key} does not identify this execution selection")
    synthetic = annotations.get("synthetic", False)
    if type(synthetic) is not bool:
        raise ValueError("annotation.synthetic must be boolean")
    if manifest.get("environment", {}).get("name") == "toy" and synthetic is not True:
        raise ValueError("toy annotations must be explicitly marked synthetic=true")
    rows = annotations.get("annotations")
    if not isinstance(rows, list):
        raise ValueError("annotations must be a list")
    canonical_hash = _canonical_hash(annotations)
    labeled = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each annotation must be an object")
        identifier = _text(row.get("episode_id"), "annotation.episode_id")
        if identifier not in expected or identifier in labeled:
            raise ValueError("annotation episode_id must be known and unique")
        if "unnecessary_intervention" not in row:
            raise ValueError("annotation needs an explicit bool or null unnecessary_intervention")
        label = row["unnecessary_intervention"]
        if label is not None and type(label) is not bool:
            raise ValueError("unnecessary_intervention must be a JSON boolean or null")
        review = row.get("review_status", "unreviewed")
        if review not in ("unreviewed", "reviewed"):
            raise ValueError("review_status must be unreviewed or reviewed")
        complete = row.get("reviewed_full_episode", False)
        if type(complete) is not bool:
            raise ValueError("reviewed_full_episode must be boolean")
        reviewer = _text(row.get("reviewer"), "annotation.reviewer", allow_empty=review == "unreviewed")
        reason = _text(row.get("reason"), "annotation.reason", allow_empty=review == "unreviewed")
        if review == "unreviewed" and (label is not None or complete):
            raise ValueError("unreviewed annotations cannot claim a label or a complete review")
        result = found.get(identifier)
        if complete and (result is None or result["status"] != "completed"):
            raise ValueError("a complete episode review requires a completed valid rollout")
        if label is not None and (not complete or review != "reviewed" or result is None or result["status"] != "completed"):
            raise ValueError("boolean UIR labels require a complete review of a completed valid rollout")
        evidence = _video_evidence(expected[identifier], result, row.get("evidence"), require_full=complete)
        labeled[identifier] = {"unnecessary_intervention": label, "review_status": review,
                               "reviewed_full_episode": complete, "reviewer": reviewer,
                               "reason": reason, "evidence": evidence}
    items, grouped = [], defaultdict(list)
    for identifier, episode in expected.items():
        result = found.get(identifier)
        status = result["status"] if result else "missing"
        label = labeled.get(identifier, {"unnecessary_intervention": None, "review_status": "unreviewed",
                                         "reviewed_full_episode": False, "reviewer": "", "reason": "No annotation entry", "evidence": []})
        mask = "".join("1" if bit else "0" for bit in episode["initial_mask"])
        stratum = "terminal_11" if all(episode["initial_mask"]) else "partial" if any(episode["initial_mask"]) else "normal_00"
        item = {"episode_id": identifier, "task_id": episode["task_id"], "suite": suite, "mask": mask,
                "stratum": stratum, "result_status": status, "eligible": status == "completed", **deepcopy(label)}
        items.append(item)
        grouped[(episode["task_id"], mask, stratum)].append(item)
    groups = [{"task_id": task, "suite": suite, "mask": mask, "stratum": stratum, **_counts(values)}
              for (task, mask, stratum), values in sorted(grouped.items())]
    report = {"schema_version": "remaining-goals-uir-summary-v1", "annotation_schema_version": SCHEMA_VERSION,
              "run_id": run_id, "manifest_hash": digest, "suite": suite, "synthetic": synthetic,
              **_selection_fields(metadata),
              "annotation_sha256": canonical_hash,
              "annotation_hash_scope": "canonical JSON of the full annotation object (UTF-8, sorted keys, compact separators); not source file bytes",
              "definition": "Human judgment of unnecessary task operations on goals already satisfied at that time; no automatic action-based detection",
              "validation_scope": "Identity, complete rollout and video-coverage declarations are checked; human review and semantic correctness are not independently certified",
              "counts": _counts(items), "by_episode": items, "by_task_mask": groups}
    for stratum in ("partial", "normal_00", "terminal_11"):
        report["partial_macro" if stratum == "partial" else stratum] = _macro(
            [group for group in groups if group["stratum"] == stratum],
            [item for item in items if item["stratum"] == stratum])
    report["by_mask"] = [{"mask": mask, **_macro([group for group in groups if group["mask"] == mask],
                                               [item for item in items if item["mask"] == mask])}
                         for mask in sorted({item["mask"] for item in items})]
    return report
