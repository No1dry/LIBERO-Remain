"""Two task011 main quantities with fixed planned denominators and coverage."""
from copy import deepcopy
from collections import Counter

from .schema import PROTOCOL, validate_result, canonical_hash

CLASSES = ("success", "failure", "unknown", "technical_error", "missing")


def score_episode(episode, result=None):
    return _score_verified_episode(episode, result, validate_result(result) if result is not None else None)


def _score_verified_episode(episode, result, valid):
    """Same classification for source-verified or explicitly derived facts.

    Internal offline callers must verify the original execution first. This
    avoids treating corrected derived facts as a newly executed raw result.
    """
    row = {key: deepcopy(episode.get(key)) for key in
           ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")}
    row.update(classification="missing", success=None, failure_reasons=[], unknown_reasons=[],
               n_steps=None, path_length_m=None, path_complete=False, goal_confirmed_step=None,
               official_goals_achieved=None, execution_status="missing")
    if result is None:
        return row
    # Fixed 100-entry plans can be minimal for unavailable tasks. Full external
    # state binding is checked by the workflow/evidence reader; here every source
    # field actually supplied by the plan must still agree with the result.
    for key in ("episode_id", "task_id", "task_name", "suite", "instruction", "initial_mask", "initial_state_index",
                "seed", "state_sha256", "model_xml_sha256", "bddl_sha256"):
        if key in episode and canonical_hash(episode[key]) != canonical_hash(result.get(key)):
            raise ValueError(f"score result differs from planned {key}")
    row.update(n_steps=result["n_steps"], path_length_m=result["path_length_m"], path_complete=valid["path_complete"],
        goal_confirmed_step=result["goal_confirmed_step"], official_goals_achieved=result["official_goals_achieved"],
        execution_status=result["status"], exit_reason=result["exit_reason"], error=result.get("error"),
        event_unknown=deepcopy(result["event_unknown"]), release_unknown_steps=result["release_unknown_steps"])
    if result["status"] != "completed":
        row.update(classification="technical_error", failure_reasons=[result["status"]])
        return row
    failures = (["goal_regression"] if result["goal_regression"] else [])
    failures.extend(sorted({event["event"] for event in result["confirmed_events"]}))
    unknown = ["event_evidence_unknown"] if result["event_unknown"] else []
    if result["goal_confirmed_step"] is None:
        # Determine whether missing release evidence could affect the endpoint;
        # this is coverage only, not an imputed physical completion label.
        possible_streak = 0
        possible = False
        for frame in result["trace"]:
            possible_streak = possible_streak + 1 if all(frame["goals"]) and frame["released"] is not False else 0
            possible |= possible_streak >= 5
        if possible:
            unknown.append("completion_release_unknown")
        else:
            failures.append("goal_not_confirmed_by_horizon")
    row.update(failure_reasons=failures, unknown_reasons=unknown)
    if failures:
        row.update(classification="failure", success=False)
    elif unknown:
        row.update(classification="unknown", success=None)
    else:
        row.update(classification="success", success=True)
    return row


def _group(rows):
    expected = len(rows)
    counts = {name: sum(row["classification"] == name for row in rows) for name in CLASSES}
    successful = [row for row in rows if row["classification"] == "success"]
    return {"expected": expected, "successes": counts["success"],
            "success_percent": 100. * counts["success"] / expected if expected else None,
            "success_conditional_mean_path_m": sum(row["path_length_m"] for row in successful) / len(successful) if successful else None,
            "path_success_coverage": {"numerator": len(successful), "denominator": expected},
            "classification_counts": counts,
            "valid_execution_coverage": {"numerator": sum(counts[key] for key in ("success", "failure", "unknown")), "denominator": expected},
            "failure_reasons": dict(Counter(reason for row in rows for reason in row["failure_reasons"])),
            "unknown_reasons": dict(Counter(reason for row in rows for reason in row["unknown_reasons"])),
            "official_goals_achieved": {"numerator": sum(row["official_goals_achieved"] is True for row in rows), "denominator": expected}}


def _macro(tasks, rows):
    result = _group(rows)
    valid_means = [task["success_conditional_mean_path_m"] for task in tasks if task["success_conditional_mean_path_m"] is not None]
    result.update(success_percent=sum(task["success_percent"] for task in tasks) / len(tasks) if tasks else None,
        success_conditional_mean_path_m=sum(valid_means) / len(valid_means) if valid_means else None,
        path_task_coverage={"numerator": len(valid_means), "denominator": len(tasks)},
        weighting="equal task weights; conditional path averages only tasks with observed successes; coverage shown")
    return result


def summarize(episodes, results, *, expected_tasks=None):
    expected = {episode["episode_id"]: episode for episode in episodes}
    if len(expected) != len(episodes):
        raise ValueError("duplicate planned headless episode")
    indexed = {}
    for result in results:
        name = result.get("episode_id")
        if name not in expected or name in indexed:
            raise ValueError("unplanned or duplicate headless result")
        indexed[name] = result
    rows = [score_episode(episode, indexed.get(episode["episode_id"])) for episode in episodes]
    return _summarize_scored(episodes, rows, expected_tasks=expected_tasks)


def _summarize_scored(episodes, rows, *, expected_tasks=None):
    """Aggregate already scored rows with the unchanged fixed-denominator rules."""
    if [row["episode_id"] for row in rows] != [episode["episode_id"] for episode in episodes]:
        raise ValueError("scored rows differ from the fixed planned population")
    pairs = sorted({(episode["suite"], episode["task_id"]) for episode in episodes})
    if expected_tasks is not None and set(expected_tasks) != {task for _, task in pairs}:
        raise ValueError("expected task inventory differs from fixed planned population")
    tasks = [{"task_id": task, "suite": suite, **_group([row for row in rows if row["task_id"] == task and row["suite"] == suite])}
             for suite, task in pairs]
    tracks = [{"suite": suite, **_macro([task for task in tasks if task["suite"] == suite],
               [row for row in rows if row["suite"] == suite])} for suite in sorted({suite for suite, _ in pairs})]
    return {"schema_version": "remaining-headless-summary-v1", "protocol_version": PROTOCOL,
            "counts": _group(rows), "tasks": tasks, "tracks": tracks,
            "mixed_batch": _macro(tasks, rows), "episodes": rows,
            "notice": "Goal confirmation is an evaluator endpoint, not model STOP. Main path efficiency is conditional on compliant success; no success is N/A. Fixed planned denominators retain missing/technical/unknown cases. LIBERO-90 is a separately labelled SOG10 zero-shot extension; the mixed batch is descriptive."}


def render_report(summary):
    def number(value):
        return f"{value:.6f}" if value is not None else "N/A"

    def coverage(value):
        return f"{value['numerator']}/{value['denominator']}"

    def reasons(value):
        return "; ".join(f"{key}: {count}" for key, count in sorted(value.items())) or "none"

    lines = ["# Headless ten-task baseline", "", summary["notice"], "",
             "| Task | Track | Compliant success | Successful mean TCP path (m) | Path coverage |", "|---|---|---:|---:|---:|"]
    for task in summary["tasks"]:
        percent = f"{task['success_percent']:.2f}%" if task['success_percent'] is not None else "N/A"
        lines.append(f"| {task['task_id']} | {task['suite']} | {percent} ({task['successes']}/{task['expected']}) | {number(task['success_conditional_mean_path_m'])} | {coverage(task['path_success_coverage'])} |")
    lines += ["", "## Equal-task summaries", "",
              "Each track averages tasks equally. Path averages include only tasks with compliant successes; both task and episode coverage are shown. The mixed batch is descriptive and does not replace either track.", "",
              "| Group | Equal-task compliant success | Equal-task successful mean TCP path (m) | Path task coverage | Successful episode coverage |",
              "|---|---:|---:|---:|---:|"]
    for label, group in [(track["suite"], track) for track in summary["tracks"]] + [("Mixed batch (descriptive)", summary["mixed_batch"])]:
        percent = f"{group['success_percent']:.2f}%" if group['success_percent'] is not None else "N/A"
        lines.append(f"| {label} | {percent} | {number(group['success_conditional_mean_path_m'])} | {coverage(group['path_task_coverage'])} | {coverage(group['path_success_coverage'])} |")
    lines += ["", "## Failure and coverage diagnostics", "",
              "Official goals achieved counts any observed all-goal frame. It does not certify release, confirmation, or compliant success.", "",
              "| Task | Failure | Unknown | Technical | Missing | Valid execution coverage | Official goals achieved | Failure reasons | Unknown reasons |",
              "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for task in summary["tasks"]:
        counts = task["classification_counts"]
        lines.append(f"| {task['task_id']} | {counts['failure']} | {counts['unknown']} | {counts['technical_error']} | {counts['missing']} | {coverage(task['valid_execution_coverage'])} | {coverage(task['official_goals_achieved'])} | {reasons(task['failure_reasons'])} | {reasons(task['unknown_reasons'])} |")
    return "\n".join(lines) + "\n"
