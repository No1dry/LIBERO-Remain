"""Trace-derived metrics for the remaining-goal benchmark.

This module has no simulator, policy, or NumPy dependency. JSON booleans are
required: numbers, strings, and other truthy values are not goal labels.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


_STATUSES = {"completed", "invalid_initial_state", "runtime_error"}
_BOOLEAN_METRICS = (
    "joint_success",
    "task_success_by_horizon",
    "stable_final_success",
    "remaining_success",
    "preservation_success",
    "goal_regression",
)


def _nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer, not a boolean")
    return value


def _boolean_mask(value: Any, name: str) -> list[bool]:
    if not isinstance(value, list) or not value or any(type(x) is not bool for x in value):
        raise ValueError(f"{name} must be a nonempty list of booleans")
    return value


def _episode_spec(episode: dict) -> tuple[list[bool], int, int]:
    if not isinstance(episode, dict):
        raise ValueError("episode must be a dictionary")
    return (
        _boolean_mask(episode.get("initial_mask"), "initial_mask"),
        _nonnegative_int(episode.get("horizon"), "horizon"),
        _nonnegative_int(episode.get("retention_steps"), "retention_steps"),
    )


def compute_metrics(episode: dict, trace: list[dict]) -> dict:
    """Validate a complete trace and recompute metrics without cached results.

    ``episode`` supplies ``initial_mask``, ``horizon`` H and
    ``retention_steps`` W. The production schema requires positive H/W; this
    pure function also accepts zero to make boundary semantics explicit.
    A nonterminal trace contains exactly H+W+1 ordered observations, with
    consecutive integer ``step`` values 0..H+W. An initially all-true trace
    instead contains W+1 observations, 0..W. Step 0 must match initial_mask.
    Every row has a boolean goal vector of the same width, a boolean
    ``stopped``, and ``action`` (a list or None). Action magnitude/contact do
    not affect success; this module makes no claim that movement is an error.

    For nonterminal starts:
      * task_success_by_horizon: all goals were simultaneously true at least
        once in steps 0..H (inclusive).
      * stable_final_success: task_success_by_horizon AND all goals stay
        true throughout H..H+W (inclusive).
      * preservation_success: every initially true goal stays true at every
        observation; None when there was nothing initially completed.
      * joint_success: stable_final_success AND initial-goal preservation.
      * remaining_success: initially false goals are simultaneously true
        by H and remain true throughout H..H+W; other goals do not affect it.
    For an all-true start, task_success_by_horizon is already True at step 0;
    stable_final_success and joint_success require the entire 0..W window
    to remain satisfied, and remaining_success is None.

    goal_regression means any initially true goal becomes false, even if it
    later recovers. regression_steps counts observations with at least one
    such false goal (each environment step counts once, not once per goal).
    first_all_success_step may be later than H; that does not grant success.
    n_steps excludes the initial observation.

    A row at step k>0 describes the state after action k. stopped=True means
    STOP had been selected before that action, so explicit_stop_step is the
    first stopped row's step minus one: the observation at which STOP was
    decided. A stopped step-0 row, if supplied, maps to decision step 0.
    No stopped row yields None. The result's cached stop_step is never read.

    Invalid types, incomplete traces, duplicate/out-of-order steps or a
    mismatched initial mask raise ValueError; incomplete runs are not scored.
    """
    initial, horizon, retention = _episode_spec(episode)
    terminal = all(initial)
    final_step = retention if terminal else horizon + retention
    if not isinstance(trace, list) or len(trace) != final_step + 1:
        raise ValueError(f"trace must contain exactly {final_step + 1} observations")

    goals: list[list[bool]] = []
    explicit_stop_step = None
    for expected_step, row in enumerate(trace):
        if not isinstance(row, dict):
            raise ValueError(f"trace[{expected_step}] must be a dictionary")
        step = _nonnegative_int(row.get("step"), f"trace[{expected_step}].step")
        if step != expected_step:
            raise ValueError("trace steps must be ordered, unique, and consecutive from 0")
        values = _boolean_mask(row.get("goals"), f"trace[{step}].goals")
        if len(values) != len(initial):
            raise ValueError(f"trace[{step}].goals does not match initial_mask width")
        if type(row.get("stopped")) is not bool:
            raise ValueError(f"trace[{step}].stopped must be a boolean")
        if "action" not in row or (row["action"] is not None and not isinstance(row["action"], list)):
            raise ValueError(f"trace[{step}].action must be a list or None")
        if row["stopped"] and explicit_stop_step is None:
            explicit_stop_step = max(0, step - 1)
        goals.append(values)
    if goals[0] != initial:
        raise ValueError("trace step 0 goals do not match initial_mask")

    completed_indices = [i for i, value in enumerate(initial) if value]
    remaining_indices = [i for i, value in enumerate(initial) if not value]
    all_success = [all(values) for values in goals]
    first_success = next((i for i, value in enumerate(all_success) if value), None)
    task_success = terminal or any(all_success[: horizon + 1])
    window_start = 0 if terminal else horizon
    stable_success = task_success and all(all_success[window_start:])
    regression_steps = sum(any(not values[i] for i in completed_indices) for values in goals)
    preservation = regression_steps == 0 if completed_indices else None
    if remaining_indices:
        remaining_satisfied = [all(values[i] for i in remaining_indices) for values in goals]
        remaining_success = any(remaining_satisfied[: horizon + 1]) and all(remaining_satisfied[horizon:])
    else:
        remaining_success = None

    return {
        "joint_success": stable_success and preservation is not False,
        "task_success_by_horizon": task_success,
        "stable_final_success": stable_success,
        "remaining_success": remaining_success,
        "preservation_success": preservation,
        "goal_regression": regression_steps > 0,
        "regression_steps": regression_steps,
        "first_all_success_step": first_success,
        "explicit_stop_step": explicit_stop_step,
        "n_steps": final_step,
    }


def _identity(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _counts(items: list[dict]) -> dict:
    counts = {
        "expected": len(items),
        "completed": sum(x["status"] == "completed" for x in items),
        "invalid_initial_state": sum(x["status"] == "invalid_initial_state" for x in items),
        "runtime_error": sum(x["status"] == "runtime_error" for x in items),
        "missing": sum(x["status"] == "missing" for x in items),
    }
    counts["errors"] = counts["invalid_initial_state"] + counts["runtime_error"]
    return counts


def _stratum(mask: list[bool]) -> str:
    if all(mask):
        return "terminal_11"
    return "partial" if any(mask) else "normal_00"


def _group_summary(task_id: str, mask: str, items: list[dict]) -> dict:
    counts = _counts(items)
    scored = [x["metrics"] for x in items if x["status"] == "completed"]
    valid_metrics = {}
    for metric in _BOOLEAN_METRICS:
        values = [x[metric] for x in scored if x[metric] is not None]
        numerator = sum(values)
        valid_metrics[metric] = {
            "numerator": numerator,
            "denominator": len(values),
            "rate": numerator / len(values) if values else None,
        }
    return {
        "task_id": task_id,
        "mask": mask,
        "initial_mask": [x == "1" for x in mask],
        "stratum": _stratum(items[0]["initial_mask"]),
        **counts,
        "missing_episode_ids": [x["episode_id"] for x in items if x["status"] == "missing"],
        "error_episode_ids": {
            status: [x["episode_id"] for x in items if x["status"] == status]
            for status in ("invalid_initial_state", "runtime_error")
        },
        "coverage": counts["completed"] / counts["expected"],
        "valid_metrics": valid_metrics,
        "conservative_joint_success": valid_metrics["joint_success"]["numerator"] / counts["expected"],
    }


def _macro(groups: list[dict], items: list[dict]) -> dict:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for group in groups:
        by_task[group["task_id"]].append(group)
    task_rates = []
    for task_id, task_groups in sorted(by_task.items()):
        rates = [x["valid_metrics"]["joint_success"]["rate"] for x in task_groups]
        task_rates.append({
            "task_id": task_id,
            "expected_task_masks": len(task_groups),
            "covered_task_masks": sum(x is not None for x in rates),
            "valid_joint_success": mean(rates) if all(x is not None for x in rates) else None,
            "conservative_joint_success": mean(x["conservative_joint_success"] for x in task_groups),
            "coverage": mean(x["coverage"] for x in task_groups),
        })
    valid = [x["valid_joint_success"] for x in task_rates]
    return {
        **_counts(items),
        "n_tasks": len(task_rates),
        "expected_task_masks": len(groups),
        "covered_task_masks": sum(x["completed"] > 0 for x in groups),
        "valid_joint_success": mean(valid) if valid and all(x is not None for x in valid) else None,
        "conservative_joint_success": mean(x["conservative_joint_success"] for x in task_rates) if task_rates else None,
        "coverage": mean(x["coverage"] for x in task_rates) if task_rates else None,
        "by_task": task_rates,
    }


def summarize_results(episodes: list[dict], results: list[dict]) -> dict:
    """Score results against the complete expected manifest, without omission.

    Every expected episode requires a unique nonempty episode_id/task_id and
    the compute_metrics specification. Supplied result IDs must be unique and
    known; statuses are completed, invalid_initial_state, or runtime_error.
    Each result must repeat the expected task_id, initial_mask, horizon and
    retention_steps exactly. A completed result requires a complete trace;
    malformed completed traces raise ValueError rather than receive a score.
    Cached ``metrics`` and ``stop_step`` fields are ignored.

    by_task_mask is a sorted list with expected/completed/errors/missing
    counts, explicit error types/IDs, completed-only Boolean metric fractions,
    coverage, and conservative_joint_success (successes / all expected).
    This conservative score treats missing/error episodes as zero for coverage
    accounting; it is not an estimate of policy failure on legal states.

    partial_macro first equally weights partial masks within each task, then
    equally weights tasks. normal_00 and terminal_11 are separate controls and
    never enter that primary macro, even for K other than two. A conditional
    valid macro is None if any expected task-mask has no completed result;
    absent cells are never silently dropped. The conservative macro always
    includes all expected cells. No episodes in a stratum yields None rates.
    Missing masks not present in the supplied manifest cannot be inferred.
    """
    if not isinstance(episodes, list) or not isinstance(results, list):
        raise ValueError("episodes and results must be lists")
    expected: dict[str, dict] = {}
    task_widths: dict[str, int] = {}
    for episode in episodes:
        initial, _, _ = _episode_spec(episode)
        episode_id = _identity(episode.get("episode_id"), "episode_id")
        task_id = _identity(episode.get("task_id"), "task_id")
        if episode_id in expected:
            raise ValueError(f"duplicate expected episode_id: {episode_id}")
        if task_id in task_widths and task_widths[task_id] != len(initial):
            raise ValueError(f"inconsistent initial_mask width for task: {task_id}")
        task_widths[task_id] = len(initial)
        expected[episode_id] = episode

    supplied: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("each result must be a dictionary")
        episode_id = _identity(result.get("episode_id"), "result.episode_id")
        if episode_id in supplied:
            raise ValueError(f"duplicate result episode_id: {episode_id}")
        if episode_id not in expected:
            raise ValueError(f"unknown result episode_id: {episode_id}")
        status = result.get("status")
        if not isinstance(status, str) or status not in _STATUSES:
            raise ValueError(f"invalid status for {episode_id}: {status!r}")
        _episode_spec(result)
        _identity(result.get("task_id"), "result.task_id")
        for field in ("task_id", "initial_mask", "horizon", "retention_steps"):
            if result[field] != expected[episode_id][field]:
                raise ValueError(f"result {episode_id} does not match expected {field}")
        supplied[episode_id] = result

    items = []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for episode_id, episode in expected.items():
        result = supplied.get(episode_id)
        status = result["status"] if result is not None else "missing"
        metrics = compute_metrics(episode, result.get("trace")) if status == "completed" else None
        item = {
            "episode_id": episode_id,
            "task_id": episode["task_id"],
            "initial_mask": episode["initial_mask"],
            "status": status,
            "metrics": metrics,
        }
        items.append(item)
        mask = "".join("1" if x else "0" for x in episode["initial_mask"])
        grouped[(episode["task_id"], mask)].append(item)
    groups = [_group_summary(task_id, mask, values) for (task_id, mask), values in sorted(grouped.items())]
    return {
        "schema_version": "remaining-goals-metrics-v1",
        "counts": _counts(items),
        "missing_episode_ids": [x["episode_id"] for x in items if x["status"] == "missing"],
        "error_episode_ids": {
            status: [x["episode_id"] for x in items if x["status"] == status]
            for status in ("invalid_initial_state", "runtime_error")
        },
        "by_task_mask": groups,
        "partial_macro": _macro([x for x in groups if x["stratum"] == "partial"], [x for x in items if _stratum(x["initial_mask"]) == "partial"]),
        "normal_00": _macro([x for x in groups if x["stratum"] == "normal_00"], [x for x in items if _stratum(x["initial_mask"]) == "normal_00"]),
        "terminal_11": _macro([x for x in groups if x["stratum"] == "terminal_11"], [x for x in items if _stratum(x["initial_mask"]) == "terminal_11"]),
    }
