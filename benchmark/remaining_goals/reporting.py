"""Compact views of existing scores; these functions never redefine a metric."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .metrics import compute_metrics, summarize_results
from .selection import ORACLE_MODE, selected_episodes


def build_display(manifest, results, summary, *, uir=None, metadata=None):
    episodes = selected_episodes(manifest, metadata)
    selection = (metadata or {}).get("execution_selection")
    suites = {episode["suite"] for episode in manifest["episodes"]}
    if len(suites) != 1:
        raise ValueError("display requires exactly one suite; do not pool suites")
    first_steps = defaultdict(list)
    expected = {episode["episode_id"]: episode for episode in episodes}
    if selection:
        # Recompute only the selected expected set; an old full-bank cached
        # summary must not create bogus missing rows for deliberately unselected IDs.
        summary = {**summary, **summarize_results(episodes, results)}
        instructions = {row["episode_id"]: row for row in selection["episodes"]}
        for result in results:
            instruction = instructions[result["episode_id"]]
            for key, value in (("selection_sha256", selection["selection_sha256"]),
                               ("instruction_mode", selection["instruction_mode"]),
                               ("instruction", instruction["original_instruction"]),
                               ("effective_instruction", instruction["effective_instruction"])):
                if result.get(key) != value:
                    raise ValueError(f"display result does not match selection {key}")
        if uir is not None and (uir.get("selection_sha256") != selection["selection_sha256"]
                                or uir.get("instruction_mode") != selection["instruction_mode"]):
            raise ValueError("UIR report does not identify this execution selection")
    for result in results:
        if result["status"] != "completed":
            continue
        episode = expected[result["episode_id"]]
        mask = "".join(str(int(value)) for value in episode["initial_mask"])
        step = compute_metrics(episode, result["trace"])["first_all_success_step"]
        if step is not None:
            first_steps[(episode["task_id"], mask)].append(step)
    uir_groups = {(row["task_id"], row["mask"]): row for row in (uir or {}).get("by_task_mask", [])}
    primary, diagnostics, annotations = [], [], []
    for group in summary["by_task_mask"]:
        identity = {"task_id": group["task_id"], "mask": group["mask"]}
        key = (group["task_id"], group["mask"])
        annotation = uir_groups.get(key)
        primary.append({**identity,
            "joint_success_rate": group["valid_metrics"]["joint_success"]["rate"],
            "unnecessary_intervention_rate": annotation["rate"] if annotation else None})
        diagnostics.append({**identity,
            "remaining_success": group["valid_metrics"]["remaining_success"]["rate"],
            "preservation_success": group["valid_metrics"]["preservation_success"]["rate"],
            "first_all_success_step_mean": mean(first_steps[key]) if first_steps[key] else None,
            "first_all_success_step_count": len(first_steps[key]),
            **{field: group[field] for field in
               ("expected", "completed", "invalid_initial_state", "runtime_error", "missing")}})
        annotations.append({**identity, **({field: annotation[field] for field in
            ("annotated", "unknown", "unannotated", "coverage", "eligible_coverage")} if annotation else {
                "annotated": 0, "unknown": 0, "unannotated": group["completed"],
                "coverage": 0.0, "eligible_coverage": 0.0 if group["completed"] else None})})
    if selection is None or selection["masks"] == "all":
        for stratum in ("normal_00", "partial_macro", "terminal_11"):
            primary.append({"task_id": "ALL (task/mask macro)", "mask": stratum,
                "joint_success_rate": summary[stratum]["valid_joint_success"],
                "unnecessary_intervention_rate": uir[stratum]["rate"] if uir else None})
    display = {"schema_version": "remaining-goals-display-v1", "suite": next(iter(suites)),
            "main": primary, "diagnostics": diagnostics, "annotation_coverage": annotations,
            "joint_denominator": "Completed valid rollouts; original numerator/denominator remain in summary.json.",
            "uir_denominator": "Manually reviewed true + false labels on completed valid rollouts; unknown excluded.",
            "macro_rule": "Equal masks within each task, then equal tasks; no missing task-mask cell is dropped.",
            "synthetic": bool(uir and uir.get("synthetic")),
            "is_toy_fixture": summary.get("is_toy_fixture", False)}
    if selection:
        diagnostic = selection["instruction_mode"] == ORACLE_MODE
        display.update(selection_sha256=selection["selection_sha256"], purpose=selection["purpose"],
                       instruction_mode=selection["instruction_mode"], diagnostic=diagnostic,
                       selection={key: selection[key] for key in
                                  ("masks", "source_expected", "expected", "selected_ids", "not_selected_ids")},
                       notice=("ORACLE DIAGNOSTIC ONLY: initial goal truth selects the remaining instruction. "
                               "Not an original-instruction baseline, causal proof, or performance upper bound. "
                               "Do not pool with main pilot scores." if diagnostic else
                               "Selected original-instruction pilot. Unselected source episodes are not missing; "
                               "the complete source bank remains unchanged."))
    return display


def _cell(value):
    if value is None:
        return "N/A"
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _rate(value):
    return "N/A" if value is None else f"{value:.2%}"


def _table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]]


def render_report(display):
    diagnostic = display.get("diagnostic", False)
    title = "ORACLE DIAGNOSTIC results" if diagnostic else "results"
    lines = [f"# LIBERO-Remain {title} — {_cell(display['suite'])}", ""]
    if display.get("selection"):
        selection = display["selection"]
        lines += [f"**{display['notice']}**", "",
                  f"Selected expected: {selection['expected']} / source episodes: {selection['source_expected']}. "
                  f"Not selected: {len(selection['not_selected_ids'])}; these IDs are not runtime failures or missing results.", ""]
    if display.get("synthetic") or display.get("is_toy_fixture"):
        lines += ["**SYNTHETIC / TOY: software verification only; not human-reviewed VLA evidence.**", ""]
    lines += ["## Oracle diagnostic scores (separate from main results)" if diagnostic else "## Main results", ""]
    lines += _table(["Task", "Mask / stratum", "Joint Success Rate", "Unnecessary Intervention Rate (UIR)"],
                    [(r["task_id"], r["mask"], _rate(r["joint_success_rate"]),
                      _rate(r["unnecessary_intervention_rate"])) for r in display["main"]])
    lines += ["", display["joint_denominator"], "", display["uir_denominator"], "",
              display["macro_rule"], "00 and 11 are separate controls and do not enter partial_macro.", "",
              "## Diagnostics", "",
              "completed means rollout 完整 (rollout complete), not task success. First-success step is the mean among "
              "completed episodes that reached all goals at least once; n is reported and may be zero.", ""]
    lines += _table(["Task", "Mask", "remaining_success", "preservation_success",
                     "first_all_success_step (mean; n)", "expected", "completed (rollout 完整)",
                     "invalid", "runtime_error", "missing"],
                    [(r["task_id"], r["mask"], _rate(r["remaining_success"]), _rate(r["preservation_success"]),
                      f"{_cell(r['first_all_success_step_mean'])}; n={r['first_all_success_step_count']}",
                      r["expected"], r["completed"], r["invalid_initial_state"], r["runtime_error"], r["missing"])
                     for r in display["diagnostics"]])
    lines += ["", "## Annotation coverage", "",
              "annotated = true + false; unknown = reviewed null; unannotated = absent/unreviewed. "
              "Label counts use completed valid rollouts only; failures/missing episodes remain above. "
              "coverage = annotated / expected; eligible_coverage = annotated / completed. "
              "UIR is N/A for a cell with no valid labels; a macro is N/A if any expected cell lacks a rate.", ""]
    lines += _table(["Task", "Mask", "annotated", "unknown", "unannotated", "coverage", "eligible_coverage"],
                    [(r["task_id"], r["mask"], r["annotated"], r["unknown"], r["unannotated"],
                      _rate(r["coverage"]), _rate(r["eligible_coverage"]))
                     for r in display["annotation_coverage"]])
    lines += ["", "Full legacy scores, fractions, conservative scores and error accounting remain in summary.json. "
              "Original episode JSON retains steps, queries, timing, actions and other evidence.", ""]
    return "\n".join(lines)
