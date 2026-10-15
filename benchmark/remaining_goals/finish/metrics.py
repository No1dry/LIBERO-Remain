"""Offline finish-v1 task contract. No policy decisions or legacy JSR changes."""
from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean

PROTOCOL = "remaining-finish-v1"
METRICS_VERSION = "remaining-finish-contract-v1"


def _window(value):
    if type(value) is not int or value < 1:
        raise ValueError("stable_steps must be a positive integer")
    return value


def stable_start(trace, stable_steps=4):
    """K physical intervals require K+1 consecutive observed states."""
    k = _window(stable_steps)
    streak = 0
    for row in trace:
        good = all(row["goals"]) and row["released"] is True
        streak = streak + 1 if good else 0
        if streak >= k + 1:
            return row["step"] - k
    return None


def forbidden_events(trace, stable_steps=4):
    """Initially outside movable distractors only; confirmed events are sticky."""
    k = _window(stable_steps)
    if not trace:
        return {"events": [], "unknown": ["no initial object evidence"]}
    initial = trace[0]["objects"]
    for row in trace:
        if set(row["objects"]) != set(initial) or any(
                row["objects"][name]["role"] != value["role"] for name, value in initial.items()):
            raise ValueError("object inventory/role changed within a finish episode")
    eligible, unknown = [], []
    for name, value in initial.items():
        if value["role"] != "distractor":
            continue
        if value["in_basket"] is False:
            eligible.append(name)
        elif value["in_basket"] is None:
            unknown.append(f"{name}: unknown initial basket membership")
    events = []
    for name in eligible:
        streak = 0
        for row in trace:
            obj = row["objects"].get(name)
            if obj is None or obj.get("role") != "distractor":
                raise ValueError("object identity/role changed within a finish episode")
            inside, released = obj["in_basket"], obj["released"]
            if inside is None or (inside is True and released is None):
                unknown.append(f"{name}: uncertain placement/release at step {row['step']}")
            streak = streak + 1 if inside is True and released is True else 0
            if streak >= k + 1:
                events.append({"object": name, "start_step": row["step"] - k,
                               "confirmed_step": row["step"], "stable_steps": k})
                break
    return {"events": events, "unknown": unknown}


def score_episode(episode, result, *, stable_steps=4, control_freq=20):
    from .schema import validate_finish_result
    _window(stable_steps)
    if type(control_freq) not in (int, float) or not math.isfinite(control_freq) or control_freq <= 0:
        raise ValueError("control_freq must be finite and positive")
    validate_finish_result(result, episode)
    base = {"metrics_version": METRICS_VERSION, "protocol_version": PROTOCOL,
            "stable_steps": stable_steps, "stability_convention": "K intervals / K+1 observed states",
            "mode": result["mode"], "compliant_finish": None, "failure_reasons": [],
            "unknown_reasons": [], "finish_step": result.get("finish_step"),
            "timeout_step": result.get("timeout_step"), "tau": None,
            "finish_delay_steps": None, "finish_delay_seconds": None,
            "delay_status": "technical_error", "forbidden_placements": []}
    if result["status"] != "completed":
        return {**base, "scoring_status": "technical_error"}
    trace = result["trace"]
    initial = episode["initial_mask"]
    if trace[0]["goals"] != initial:
        raise ValueError("completed finish episode has an invalid initial goal mask")
    reasons, unknown = [], []
    f = result.get("finish_step")
    exit_step = f if f is not None else result["timeout_step"]
    exit_row = trace[exit_step]
    finished_now = all(exit_row["goals"]) and exit_row["released"] is True
    if exit_row["released"] is None:
        unknown.append("target release at exit is unknown")
    if f is None:
        reasons.append("no_finish_timeout")
    elif not all(exit_row["goals"]) or exit_row["released"] is False:
        reasons.append("premature_finish")
    if not all(exit_row["goals"]):
        reasons.append("unfinished_goal")
    regression = any(any(flag and not row["goals"][i] for i, flag in enumerate(initial)) for row in trace)
    if regression:
        reasons.append("goal_regression")
    if any(not all(row["goals"]) for row in trace[exit_step:]):
        reasons.append("unstable_after_exit")
    placement = forbidden_events(trace, stable_steps)
    if placement["events"]:
        reasons.append("forbidden_placement")
    unknown += placement["unknown"]
    tau = stable_start(trace, stable_steps)
    tau_basis = "first_observed_stable_interval"
    if all(initial) and all(trace[0]["goals"]) and trace[0]["released"] is True:
        tau, tau_basis = 0, "valid_initially_completed_state"
    delay_status = ("timeout" if f is None else "unknown_release" if exit_row["released"] is None
                    else "premature_finish" if not finished_now else "no_tau" if tau is None else "observed")
    delay = f - tau if delay_status == "observed" and tau <= f else None
    if delay_status == "observed" and delay is None:
        delay_status = "no_tau_at_finish"
    # Shadow has no active FINISH score, even though its diagnostic exit is timeout.
    if result["mode"] == "shadow":
        status, success = "not_applicable", None
    elif reasons:
        status, success = "scored", False
    elif unknown:
        status, success = "unknown", None
    else:
        status, success = "scored", True
    return {**base, "scoring_status": status, "compliant_finish": success,
            "failure_reasons": reasons, "unknown_reasons": unknown,
            "forbidden_placements": placement["events"], "tau": tau, "tau_basis": tau_basis,
            "finish_delay_steps": delay, "finish_delay_seconds": None if delay is None else delay/control_freq,
            "delay_status": delay_status, "goals_at_exit": exit_row["goals"],
            "released_at_exit": exit_row["released"], "initial_preservation": not regression}


def summarize(episodes, results, *, mode, stable_steps=4, control_freq=20):
    _window(stable_steps)
    if type(control_freq) not in (int, float) or not math.isfinite(control_freq) or control_freq <= 0:
        raise ValueError("control_freq must be finite and positive")
    if mode not in ("active", "shadow"):
        raise ValueError("unsupported finish mode")
    expected = {e["episode_id"]: e for e in episodes}
    if not expected or len(expected) != len(episodes):
        raise ValueError("expected episodes must be nonempty and unique")
    found = {}
    for result in results:
        name = result["episode_id"]
        if name not in expected or name in found or result.get("mode") != mode:
            raise ValueError("unexpected/duplicate/mixed-mode finish result")
        found[name] = result
    rows = []
    for name, episode in expected.items():
        scored = score_episode(episode, found[name], stable_steps=stable_steps, control_freq=control_freq) if name in found else {
            "scoring_status": "missing", "compliant_finish": None, "failure_reasons": [],
            "unknown_reasons": [], "delay_status": "missing", "finish_delay_steps": None}
        rows.append({"episode_id": name, "task_id": episode["task_id"],
                     "mask": "".join(str(int(v)) for v in episode["initial_mask"]), **scored})
    def cell(items):
        count = len(items)
        success = sum(row["compliant_finish"] is True for row in items)
        counts = {key: sum(row["scoring_status"] == key for row in items)
                  for key in ("scored", "unknown", "technical_error", "missing", "not_applicable")}
        delays = [row["finish_delay_steps"] for row in items if row["finish_delay_steps"] is not None]
        categories = sorted({row["delay_status"] for row in items})
        return {"expected": count, "successful": success if mode == "active" else None,
                "compliant_finish_percent": 100*success/count if mode == "active" else None,
                "fraction": f"{success}/{count}" if mode == "active" else "N/A (shadow diagnostic)",
                **counts, "score_coverage": counts["scored"]/count,
                "delay_mean_steps": mean(delays) if delays else None,
                "delay_observed": len(delays), "delay_coverage": len(delays)/count,
                "delay_categories": {key: sum(r["delay_status"] == key for r in items) for key in categories},
                "failure_counts": {key: sum(key in r["failure_reasons"] for r in items) for key in
                    ("premature_finish", "no_finish_timeout", "unfinished_goal", "goal_regression", "forbidden_placement", "unstable_after_exit")}}
    groups = defaultdict(list)
    for row in rows:
        groups[(row["task_id"], row["mask"])].append(row)
    return {"schema_version": "remaining-finish-summary-v1", "protocol_version": PROTOCOL,
            "metrics_version": METRICS_VERSION, "mode": mode, "stable_steps": stable_steps,
            "counts": cell(rows), "by_task_mask": [{"task_id": key[0], "mask": key[1], **cell(items)} for key,items in sorted(groups.items())],
            "episodes": rows, "notice": "Fixed planned denominator; technical errors, unknown and missing are disclosed separately. Shadow has no active main score. This is not legacy JSR or UIR."}


def render_report(summary):
    lines = ["# FINISH-v1 " + summary["mode"], "", summary["notice"], "",
             "| Task | Mask | Compliant FINISH | n/N | Scored | Unknown | Technical | Missing |",
             "|---|---|---|---|---|---|---|---|"]
    for row in summary["by_task_mask"]:
        rate = "N/A" if row["compliant_finish_percent"] is None else f"{row['compliant_finish_percent']:.2f}%"
        lines.append(f"| {row['task_id']} | {row['mask']} | {rate} | {row['fraction']} | {row['scored']} | {row['unknown']} | {row['technical_error']} | {row['missing']} |")
    lines += ["", "Stability uses K physical intervals / K+1 states. Delay/failed/timeout/unknown coverage and multiple failure reasons remain in summary.json.", ""]
    return "\n".join(lines)
