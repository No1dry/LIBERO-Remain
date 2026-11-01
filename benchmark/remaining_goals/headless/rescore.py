"""File-only table-support correction; never rewrite an execution record."""
from copy import deepcopy
import csv
import json
from pathlib import Path

from .planning import COMMON_TEN_TASKS, canonical_hash, file_sha, planned_episodes
from .schema import analyze_trace
from .metrics import _score_verified_episode, _summarize_scored
from .workflow import _bound_task, read_batch, write_json

SCHEMA = "remaining-headless-table-support-rescore-v2"
EPISODE_SCHEMA = "remaining-headless-derived-support-episode-v2"
FACTS = ("goals", "released", "tcp", "objects", "event_candidates", "event_evidence")


def _derive_verified_episode(episode, result):
    """Only called after the original reader has checked its original binding."""
    from .environment import corrected_measurement_static, recompute_table_drop, SUPPORT_RULE
    valid = {"path_complete": len(result["trace"]) == result["n_steps"] + 1}
    old = _score_verified_episode(episode, result, valid)
    revised = deepcopy(result)
    support_changes, frames = [], []
    static = result.get("measurement_static")
    if static is not None:
        revised["measurement_static"] = corrected_measurement_static(static)
        for name in static["role_profile"]["table_drop_objects"]:
            before = static["initial_objects"][name]["table_support"]
            after = revised["measurement_static"]["initial_objects"][name]["table_support"]
            if before != after:
                support_changes.append({"object": name, "role": static["role_profile"]["roles"][name]["role"],
                    "body_position": deepcopy(static["initial_objects"][name]["position"]),
                    "old_support": deepcopy(before), "new_support": deepcopy(after),
                    "reason": "native top-face contact establishes support independently of the body reference point"})
        for original, row in zip(result["trace"], revised["trace"]):
            facts = recompute_table_drop({key: original[key] for key in FACTS}, revised["measurement_static"])
            row["event_candidates"]["table_drop"] = facts["event_candidates"]["table_drop"]
            row["event_evidence"]["table_drop"] = facts["event_evidence"]["table_drop"]
        analysis = analyze_trace(revised["trace"], confirmation_steps=result["configuration"]["confirmation_steps"])
        # Re-run the unchanged sticky event logic, preserving every endpoint,
        # goal, release and path fact. Only table_drop may change classification.
        for key in ("path_length_m", "goal_completion_step", "goal_confirmed_step", "goal_regression",
                    "release_unknown_steps", "official_goals_achieved"):
            if analysis[key] != result[key]:
                raise ValueError(f"support correction changed unrelated {key}")
        for key in ("confirmed_events", "event_unknown"):
            if ([item for item in analysis[key] if item["event"] != "table_drop"] !=
                    [item for item in result[key] if item["event"] != "table_drop"]):
                raise ValueError("support correction changed a different event channel")
        for row, derived in zip(revised["trace"], analysis["frames"]):
            row.update(derived)
            frames.append({"step": row["step"], "candidates": deepcopy(row["event_candidates"]["table_drop"]),
                "evidence": deepcopy(row["event_evidence"]["table_drop"]),
                "confirmed_events": [deepcopy(event) for event in derived["confirmed_events"] if event["event"] == "table_drop"]})
        revised.update({key: value for key, value in analysis.items() if key != "frames"})
    new = _score_verified_episode(episode, revised, valid)
    return {"schema_version": EPISODE_SCHEMA, "support_rule": SUPPORT_RULE,
        "episode_id": episode["episode_id"], "derived_only": True, "new_execution": False,
        "old": old, "new": new, "support_changes": support_changes,
        "measurement_static": revised.get("measurement_static"), "table_drop_trace": frames,
        "confirmed_events": deepcopy(revised["confirmed_events"]), "event_unknown": deepcopy(revised["event_unknown"]),
        "preserved": {key: deepcopy(result[key]) for key in ("n_steps", "configuration", "exit_reason", "status",
            "path_length_m", "goal_completion_step", "goal_confirmed_step", "goal_regression", "release_unknown_steps",
            "official_goals_achieved")},
        "preserved_actions_sha256": canonical_hash(result["executed_actions"]),
        "preserved_queries_sha256": canonical_hash(result["queries"])}


def _coverage(rows):
    successes = sum(row["classification"] == "success" for row in rows)
    executed = sum(row["n_steps"] is not None and row["n_steps"] > 0 for row in rows)
    counts = {kind: sum(row["classification"] == kind for row in rows)
              for kind in ("success", "failure", "unknown", "technical_error", "missing")}
    successful = [row["path_length_m"] for row in rows if row["classification"] == "success"]
    def fraction(denominator):
        return {"numerator": successes, "denominator": denominator,
                "percent": 100. * successes / denominator if denominator else None}
    return {"planned": len(rows), "recorded": len(rows) - counts["missing"], "executed": executed,
        "valid_execution": sum(counts[k] for k in ("success", "failure", "unknown")),
        "classification_counts": counts, "success_among_executed": fraction(executed),
        "success_over_plan": fraction(len(rows)),
        "success_conditional_mean_path_m": sum(successful) / len(successful) if successful else None}


def _comparison(old, new):
    return {"old": _coverage(old), "new": _coverage(new)}


def _write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()} for row in rows)


def _report(summary):
    def rate(value):
        item = value["success_among_executed"]
        percent = f"{item['percent']:.2f}%" if item["percent"] is not None else "N/A"
        return f"{percent} ({item['numerator']}/{item['denominator']})"
    def length(value):
        number = value["success_conditional_mean_path_m"]
        return "N/A" if number is None else f"{number:.6f}"
    lines = ["# Table-support v2 offline rescore", "", summary["notice"], "",
        "Success / executed includes unknown and technical executed cases in its denominator; they are shown separately, not relabelled as model failures.",
        "Executed means at least one recorded policy control step. Source-verification errors are listed explicitly and are never scored as successes.", "",
        "| Task / group | Old success / executed | New success / executed | Planned | Missing | Old successful L (m) | New successful L (m) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    groups = [{"task_id": "All episodes (descriptive)", **summary["comparison"]}, *summary["tasks"]]
    for item in groups:
        old, new = item["old"], item["new"]
        lines.append(f"| {item['task_id']} | {rate(old)} | {rate(new)} | {new['planned']} | {new['classification_counts']['missing']} | {length(old)} | {length(new)} |")
    lines += ["", "## Classification and coverage", "",
        "| Task | Old success/failure/unknown/technical/missing | New success/failure/unknown/technical/missing | Recorded / planned | Valid execution / planned |", "|---|---|---|---:|---:|"]
    for item in groups:
        def counts(value):
            return "/".join(str(value["classification_counts"][k]) for k in ("success", "failure", "unknown", "technical_error", "missing"))
        new = item["new"]
        lines.append(f"| {item['task_id']} | {counts(item['old'])} | {counts(new)} | {new['recorded']}/{new['planned']} | {new['valid_execution']}/{new['planned']} |")
    lines += ["", "## Classification or event changes", "",
        "| Episode | Old | New | Changed support objects | New failure reasons | New unknown reasons |", "|---|---|---|---|---|---|"]
    for row in summary["changes"]:
        lines.append(f"| {row['episode_id']} | {row['old_classification']} | {row['new_classification']} | {', '.join(row['support_changed_objects']) or 'none'} | {', '.join(row['new_failure_reasons']) or 'none'} | {', '.join(row['new_unknown_reasons']) or 'none'} |")
    lines += ["", "Per-episode JSON files retain original SHA references, old/new support evidence and every derived table-drop candidate/sticky event. episodes.csv includes all 100 planned entries.",
        "", "Track and equal-task aggregates retain the original metrics definitions in old_summary/new_summary; the rates above use episode denominators.",
        "", "## Source artifact issues", "", json.dumps(summary["unverified_task_artifacts"], ensure_ascii=False, indent=2), ""]
    return "\n".join(lines)


def rescore_batch(directory, output):
    """Verify existing originals, then write only to a new independent directory."""
    from ..cli import _source_hash
    from .environment import SUPPORT_RULE
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if output == directory or directory in output.parents or output in directory.parents or output.exists():
        raise ValueError("rescore output must be a new independent directory outside the original batch")
    batch_sha = file_sha(directory / "batch.json")
    batch = read_batch(directory)
    expected = planned_episodes()
    planned = {row["episode_id"]: row for row in expected}
    old_rows = {key: _score_verified_episode(value, None, None) for key, value in planned.items()}
    new_rows = deepcopy(old_rows)
    artifacts, changes, issues, task_sources = [], [], [], []
    output.mkdir(parents=True, exist_ok=False)
    for task in COMMON_TEN_TASKS:
        task_dir = directory / "tasks" / task
        if not task_dir.exists():
            continue
        try:
            metadata_sha = file_sha(task_dir / "task_run.json")
            metadata, results = _bound_task(directory, batch, task, allow_partial=True)
            issues.extend(metadata["artifact_issues"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"task_id": task, "reason": f"{type(error).__name__}: {error}"})
            continue
        references = {row["episode_id"]: row for row in metadata["results"]}
        task_sources.append({"task_id": task, "task_run_sha256": metadata_sha,
                             "source_plan_sha256": metadata["source_plan"]["source_plan_sha256"]})
        for result in results:
            name = result["episode_id"]
            derived = _derive_verified_episode(planned[name], result)
            derived["source"] = {"batch_identity_sha256": batch["batch_identity_sha256"], "batch_sha256": batch_sha,
                "source_harness_sha256": batch["identity"]["harness_source_sha256"],
                "task_run_path": f"tasks/{task}/task_run.json", "task_run_sha256": metadata_sha,
                "raw_path": f"tasks/{task}/{references[name]['path']}", "raw_sha256": references[name]["sha256"],
                "source_plan_sha256": metadata["source_plan"]["source_plan_sha256"],
                "original_identity_sha256": result["identity_sha256"],
                "original_measurement_static_sha256": (result.get("measurement_static") or {}).get("static_sha256"),
                "original_execution_evidence": deepcopy(result.get("execution_evidence"))}
            old_rows[name], new_rows[name] = derived["old"], derived["new"]
            relative = f"episodes/{name}.json"
            write_json(output / relative, derived)
            artifacts.append({"episode_id": name, "path": relative, "sha256": file_sha(output / relative)})
            changed_events = (derived["confirmed_events"] != result["confirmed_events"] or
                              derived["event_unknown"] != result["event_unknown"])
            if derived["old"] != derived["new"] or changed_events or derived["support_changes"]:
                changes.append({"episode_id": name, "task_id": task,
                    "old_classification": derived["old"]["classification"], "new_classification": derived["new"]["classification"],
                    "old_failure_reasons": derived["old"]["failure_reasons"], "new_failure_reasons": derived["new"]["failure_reasons"],
                    "old_unknown_reasons": derived["old"]["unknown_reasons"], "new_unknown_reasons": derived["new"]["unknown_reasons"],
                    "support_changed_objects": [row["object"] for row in derived["support_changes"]],
                    "classification_changed": derived["old"]["classification"] != derived["new"]["classification"],
                    "event_evidence_changed": changed_events, "evidence_path": relative,
                    "reason": "derive table support from native top-face contacts; recompute table_drop with unchanged 2cm/K4 rule"})
        if file_sha(task_dir / "task_run.json") != metadata_sha:
            raise ValueError("original task changed during offline derivation")
    if file_sha(directory / "batch.json") != batch_sha:
        raise ValueError("original batch changed during offline derivation")
    for row in expected:
        name, task = row["episode_id"], row["task_id"]
        if old_rows[name]["classification"] == "missing":
            reason = next((i["reason"] for i in issues if i["task_id"] == task and i.get("episode_id", name) == name), None)
            reason = reason or batch["tasks"].get(task, {}).get("error") or "not run"
            old_rows[name]["missing_reason"] = new_rows[name]["missing_reason"] = reason
    old, new = list(old_rows.values()), list(new_rows.values())
    summary = {"schema_version": SCHEMA, "support_rule": SUPPORT_RULE, "derived_only": True, "new_execution": False,
        "source": {"batch_path": str(directory), "batch_sha256": batch_sha,
                   "batch_identity_sha256": batch["batch_identity_sha256"] ,
                   "source_harness_sha256": batch["identity"]["harness_source_sha256"],
                   "plans": deepcopy(batch["invocations"]), "tasks": task_sources,
                   "original_summary_sha256": file_sha(directory / "summary.json") if (directory / "summary.json").exists() else None},
        "derivation_harness_sha256": _source_hash(), "expected": expected, "comparison": _comparison(old, new),
        "old_summary": _summarize_scored(expected, old), "new_summary": _summarize_scored(expected, new),
        "tasks": [{"task_id": task, "suite": planned[f"{task}_s000_10"]["suite"],
                   **_comparison([r for r in old if r["task_id"] == task], [r for r in new if r["task_id"] == task])}
                  for task in COMMON_TEN_TASKS],
        "changes": changes, "derived_episodes": artifacts, "unverified_task_artifacts": issues,
        "notice": "Derived table-support v2 rescore of every verifiable recorded episode. Original raw/static/execution/source/summary bytes are not overwritten. The fixed 100-entry population retains missing, unknown and technical cases; they are not automatically model failures. Per-episode actions, goals, endpoint, release and TCP path are unchanged; successful-population mean L may change."}
    write_json(output / "summary.json", summary)
    write_json(output / "changes.json", {"schema_version": SCHEMA, "changes": changes})
    _write_csv(output / "episodes.csv", [{"episode_id": a["episode_id"], "task_id": a["task_id"], "suite": a["suite"],
        "old_classification": a["classification"], "new_classification": b["classification"],
        "n_steps": a["n_steps"], "path_length_m": a["path_length_m"], "old_failure_reasons": a["failure_reasons"],
        "new_failure_reasons": b["failure_reasons"], "old_unknown_reasons": a["unknown_reasons"],
        "new_unknown_reasons": b["unknown_reasons"], "missing_reason": a.get("missing_reason")} for a, b in zip(old, new)])
    (output / "report.md").write_text(_report(summary), encoding="utf-8")
    return summary
