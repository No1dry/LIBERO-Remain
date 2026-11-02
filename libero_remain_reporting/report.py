"""Binary report mapping; no physical facts, endpoints or old files are edited."""
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path

REPORT_VERSION = "binary-compliant-success-v1"
IDENTITY_FIELDS = ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")
COMPLETED_CLASSES = {"success", "failure", "unknown"}
MODEL_FIELDS = ("checkpoint_source", "checkpoint_training_suites", "repo_commit", "unnorm_key",
                "dataset_statistics_sha256", "normalization_statistics_sha256", "inference_source_sha256",
                "component_checkpoint_sha256", "inference_configuration", "prepared_checkpoint_code_sha256",
                "method_adapter")


def _rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "percent": 100.0 * numerator / denominator if denominator else None}


def _counts(rows, *, integrity_ok=True):
    completed = sum(row["outcome"] is not None for row in rows)
    successes = sum(row["success"] is True for row in rows)
    return {"expected": len(rows), "completed": completed, "successes": successes,
            "unsuccessful": completed - successes, "unresolved_jobs": len(rows) - completed,
            "completion": _rate(completed, len(rows)),
            "live_completed_SR": _rate(successes, completed),
            "formal_SR": _rate(successes, len(rows)) if rows and completed == len(rows) and integrity_ok else None}


def map_verified_results(expected_episodes, records, *, artifact_issues=()):
    """Map accepted verified score records into a new binary report.

    ``records`` is the accepted core's record sequence (or episode-id mapping),
    each with ``primary``, ``legacy`` and ``source.verified_files``. Completed
    success/failure/unknown map to true/false/false. All execution or integrity
    failures retain null outcome and are excluded only from the explicitly live
    completed SR. Formal scores require the entire fixed population and no
    integrity errors. Input objects are never modified.
    """
    expected = deepcopy(list(expected_episodes))
    names = [row["episode_id"] for row in expected]
    if len(set(names)) != len(names):
        raise ValueError("duplicate planned episode")
    if any(any(key not in row for key in IDENTITY_FIELDS) for row in expected):
        raise ValueError("planned episode lacks source identity")
    errors = [{"code": "artifact_error", "detail": deepcopy(issue)} for issue in artifact_issues]
    indexed = defaultdict(list)
    source_roots, source_files = set(), set()
    supplied = records.items() if isinstance(records, Mapping) else ((None, row) for row in records)
    for key, record in supplied:
        name = record.get("primary", {}).get("episode_id") if isinstance(record, dict) else None
        source = record.get("source", {}) if isinstance(record, dict) else {}
        if source.get("run_path"):
            source_roots.add(str(Path(source["run_path"]).resolve()))
        for reference in source.get("verified_files", []):
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                source_files.add(str(Path(reference["path"]).resolve()))
        if name not in names or key is not None and key != name:
            errors.append({"code": "unplanned_episode", "episode_id": name, "mapping_key": key})
            continue
        indexed[name].append(deepcopy(record))
    rows, checked = [], {}
    for episode in expected:
        name = episode["episode_id"]
        candidates = indexed[name]
        row = {**deepcopy(episode), "outcome": None, "success": None, "execution_status": "missing", "diagnostics": {}}
        rows.append(row)
        if len(candidates) != 1:
            errors.append({"code": "duplicate_episode" if candidates else "missing_episode", "episode_id": name,
                           "count": len(candidates)})
            row["diagnostics"] = {"records": candidates}
            continue
        record = candidates[0]
        row["diagnostics"] = record
        primary, source = record.get("primary", {}), record.get("source", {})
        row["execution_status"] = primary.get("execution_status", "missing")
        if source.get("run_path"):
            source_roots.add(str(Path(source["run_path"]).resolve()))
        if any(primary.get(key) != episode[key] for key in IDENTITY_FIELDS):
            errors.append({"code": "source_identity_error", "episode_id": name})
            continue
        classification, status = primary.get("classification"), primary.get("execution_status")
        if status != "completed" or classification not in COMPLETED_CLASSES:
            errors.append({"code": classification if classification in {"missing", "technical_error", "running"}
                           else str(status or "invalid_execution"), "episode_id": name})
            continue
        try:
            references = source.get("verified_files")
            if not references or not source.get("input_evidence_level"):
                raise ValueError("completed record has no verified source/result binding")
            if source.get("current_reference_issues"):
                raise ValueError(str(source["current_reference_issues"]))
            for reference in references:
                path = Path(reference["path"]).resolve()
                source_files.add(str(path))
                if path not in checked:
                    checked[path] = hashlib.sha256(path.read_bytes()).hexdigest()
                if checked[path] != reference["sha256"]:
                    raise ValueError(f"verified source bytes changed: {path}")
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({"code": "source_integrity_error", "episode_id": name, "detail": str(error)})
            continue
        row.update(success=classification == "success",
                   outcome="success" if classification == "success" else "unsuccessful")
    models = set()
    missing_model = False
    for row in rows:
        if row["outcome"] is None:
            continue
        model = row["diagnostics"].get("source", {}).get("model_identity")
        if not model:
            missing_model = True
            continue
        policy = model.get("policy_metadata", model)
        identity = {key: deepcopy(policy.get(key)) for key in MODEL_FIELDS}
        # Method-aware callers may add adapter identity beside legacy metadata.
        if "method_adapter" in model:
            identity["method_adapter"] = deepcopy(model["method_adapter"])
        models.add(json.dumps(identity, sort_keys=True, allow_nan=False))
    compatible = len(models) <= 1 and not (models and missing_model)
    if not compatible:
        errors.append({"code": "model_identity_mismatch", "detail": "actual model/statistics/inference/adapter identities differ or are missing"})
    tasks = []
    for suite, task in sorted({(e["suite"], e["task_id"]) for e in expected}):
        subset = [row for row in rows if row["suite"] == suite and row["task_id"] == task]
        tasks.append({"suite": suite, "task_id": task, **_counts(subset, integrity_ok=not errors)})
    formal_macro = (sum(task["formal_SR"]["percent"] for task in tasks) / len(tasks)
                    if tasks and all(task["formal_SR"] is not None for task in tasks) else None)
    counts = _counts(rows, integrity_ok=not errors)
    if not compatible:
        for item in [counts, *tasks]:
            item.update(formal_SR=None, live_completed_SR=None)
    return {"report_version": REPORT_VERSION, "derived_only": True, "new_execution": False,
            "counts": counts, "tasks": tasks, "model_aggregation_compatible": compatible,
            "macro": {"formal_SR_percent": formal_macro, "weighting": "equal task weights"},
            "episodes": rows, "integrity_errors": errors,
            "source_roots": sorted(source_roots), "source_files": sorted(source_files)}


def render_report(report):
    def rate(value):
        return f"{value['percent']:.2f}% ({value['numerator']}/{value['denominator']})" if value and value["percent"] is not None else "N/A"
    lines = ["# Binary compliant success", "", REPORT_VERSION, "",
             "Completed episodes have two outcomes: success and unsuccessful. Original evidence remains in episode diagnostics.", "",
             "| Task | Success | Unsuccessful | Formal SR | Live completed SR | Completion |",
             "|---|---:|---:|---:|---:|---:|"]
    for item in report["tasks"] + [{"task_id": "Total", **report["counts"]}]:
        lines.append(f"| {item['task_id']} | {item['successes']} | {item['unsuccessful']} | {rate(item['formal_SR'])} | {rate(item['live_completed_SR'])} | {rate(item['completion'])} |")
    macro = report["macro"]["formal_SR_percent"]
    lines += ["", f"Equal-task formal macro SR: {macro:.2f}%" if macro is not None else "Equal-task formal macro SR: N/A (incomplete population or integrity errors).", "",
              f"Run integrity errors: {len(report['integrity_errors'])}. Unresolved jobs: {report['counts']['unresolved_jobs']}."]
    if report["integrity_errors"]:
        lines += ["", "Run integrity diagnostics:", ""]
        lines.extend(f"- {issue.get('episode_id', 'input')}: {issue['code']} — {issue.get('detail', '')}" for issue in report["integrity_errors"])
    return "\n".join(lines) + "\n"


def write_report(report, output):
    """Write only to a new isolated directory; never overwrite old reports."""
    output = Path(output).resolve()
    for value in report.get("source_roots", []):
        root = Path(value).resolve()
        if output == root or root in output.parents or output in root.parents:
            raise ValueError("report output overlaps source evidence")
    for value in report.get("source_files", []):
        path = Path(value).resolve()
        if output == path or output in path.parents:
            raise ValueError("report output overlaps source evidence")
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_report(report), encoding="utf-8")
