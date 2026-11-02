"""Plan6: reuse historical records read-only and execute only the new three tasks."""
from collections import Counter
from copy import deepcopy
from pathlib import Path

from . import workflow
from .nine_planning import (PLAN_SCHEMA, NINE_PROTOCOLS, NINE_NORMAL00, NEW_TASKS, REUSE_TASKS,
    canonical_hash, file_sha, read_json, dry_plan, validate_plan, expected_episodes, condition)
from .offline_scoring import score_verified_result, SCORING_VERSION

BATCH_SCHEMA = "remaining-headless-nine-batch-v1"
SUMMARY_SCHEMA = "remaining-headless-nine-summary-v1"
CLASSES = ("success", "failure", "unknown", "technical_error", "missing")


def _missing(episode, reason="not executed", status="missing"):
    from .metrics import _score_verified_episode
    row = _score_verified_episode(episode, None, None)
    if status in {"technical_error", "technical_pause", "artifact_error", "failed", "running"}:
        row.update(classification="technical_error", execution_status="technical_error",
                   failure_reasons=[status], error=reason)
    row["error"] = reason
    bits = "00" if episode["initial_mask"] == [False, False] else "10"
    return {"condition": bits, "legacy": deepcopy(row), "primary": deepcopy(row),
            "source": {"input_evidence_level": "unavailable", "reason": reason}}


def _refresh_reference(record):
    result = deepcopy(record)
    issues = []
    for ref in result.get("source", {}).get("verified_files", []):
        try:
            if file_sha(ref["path"]) != ref["sha256"]:
                raise ValueError("source bytes changed")
        except (OSError, KeyError, ValueError, TypeError) as error:
            issues.append(f"{ref.get('path')}: {type(error).__name__}: {error}")
    if issues:
        result["primary"].update(classification="technical_error", success=None,
            execution_status="technical_error", failure_reasons=["reuse_artifact_changed"], error="; ".join(issues))
        result["source"]["current_reference_issues"] = issues
    return result


def _rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "percent": 100.0 * numerator / denominator if denominator else None}


def _portable_model(model):
    """Compare actual assets/configuration; checkout and weight-directory paths may move."""
    shared = workflow.shared_model_identity(model) if "policy_metadata" in model else deepcopy(model)
    shared.pop("checkpoint", None)
    return shared


def _check_reuse_model(reuse, actual):
    expected = _portable_model(actual)
    for name, record in reuse["episodes"].items():
        row = record["primary"]
        if row.get("execution_status") != "completed" or row.get("classification") in {"technical_error", "missing"}:
            continue
        original = record.get("source", {}).get("model_identity")
        if not original or _portable_model(original) != expected:
            raise ValueError(f"actual loaded model/statistics/inference differ from reused episode {name}")


def _counts(records, *, normal):
    rows = [record["primary"] for record in records]
    observed = [r for r in rows if r.get("execution_status") == "completed"
                and r.get("classification") not in {"missing", "technical_error"}]
    official = [r for r in observed if type(r.get("official_goals_achieved")) is bool]
    successes = [r for r in observed if r["classification"] == "success"]
    legacy_rows = [r["legacy"] for r in records if r.get("legacy_diagnostic_available", True)]
    legacy_observed = [r for r in legacy_rows if r.get("execution_status") == "completed"
                       and r.get("classification") not in {"missing", "technical_error"}]
    paths = [r for r in successes if r.get("path_complete") and isinstance(r.get("path_length_m"), (int, float))]
    by_endpoint = {}
    for record in records:
        row = record["primary"]
        if row not in paths:
            continue
        key = record.get("source", {}).get("original_protocol", "unspecified_recorded_endpoint")
        by_endpoint.setdefault(key, []).append(row["path_length_m"])
    result = {"expected": len(rows), "observed": len(observed),
        "coverage": _rate(len(observed), len(rows)),
        "classification_counts": {key: sum(r["classification"] == key for r in rows) for key in CLASSES},
        "official_task_SR": _rate(sum(r["official_goals_achieved"] for r in official), len(official)),
        "official_signal_coverage": _rate(len(official), len(rows)),
        "compliant_task_SR": None if normal else _rate(len(successes), len(observed)),
        "legacy_compliant_SR": _rate(sum(r["classification"] == "success" for r in legacy_observed), len(legacy_observed)),
        "success_conditional_mean_path_m": None if normal else sum(r["path_length_m"] for r in paths) / len(paths) if paths else None,
        "path_success_coverage": _rate(len(paths), len(rows)),
        "path_completeness_among_successes": _rate(len(paths), len(successes)),
        "path_by_endpoint": {key: {"n": len(values), "mean_m": sum(values) / len(values)} for key, values in by_endpoint.items()},
        "failure_reasons": dict(Counter(reason for r in rows for reason in r.get("failure_reasons", []))),
        "unknown_reasons": dict(Counter(reason for r in rows for reason in r.get("unknown_reasons", []))),
        "table_drop_diagnostic": {"confirmed_episodes": sum(any(e.get("event") == "table_drop" for e in
            (r.get("primary", {}).get("legacy_confirmed_events") or [])) for r in records),
            "unknown_episodes": sum(any(e.get("event") == "table_drop" for e in
                (r.get("primary", {}).get("legacy_event_unknown", r.get("legacy", {}).get("event_unknown")) or [])) for r in records)},
        "path_notice": "00 whole-trajectory lengths are grouped by original endpoint/protocol; no mixed-endpoint efficiency mean." if normal else "Original full executed trajectory, conditional on compliant success."}
    identities = {canonical_hash(_portable_model(r["source"]["model_identity"])) for r in records
        if r.get("source", {}).get("model_identity") and r["primary"].get("execution_status") == "completed"
        and r["primary"].get("classification") not in {"missing", "technical_error"}}
    result["model_aggregation_compatible"] = len(identities) <= 1
    if len(identities) > 1:
        result.update(official_task_SR=None, compliant_task_SR=None, legacy_compliant_SR=None,
                      success_conditional_mean_path_m=None, path_by_endpoint={})
    return result


def make_report(records, *, protocols=NINE_PROTOCOLS):
    if len(protocols) != len(set(protocols)) or any(p not in NINE_PROTOCOLS for p in protocols):
        raise ValueError("duplicate or foreign report protocol")
    expected = [e for protocol in protocols for e in expected_episodes(protocol)]
    allowed_all = {e["episode_id"] for protocol in NINE_PROTOCOLS for e in expected_episodes(protocol)}
    if set(records) - allowed_all:
        raise ValueError("legacy LIBERO90 or unplanned records cannot enter the nine-task report")
    selected = {}
    for episode in expected:
        name = episode["episode_id"]
        record = _refresh_reference(records[name]) if name in records else _missing(episode)
        for field in ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask"):
            if record["primary"].get(field) != episode[field]:
                raise ValueError("report row differs from planned source identity")
        if record.get("condition") != name[-2:]:
            raise ValueError("report row condition differs")
        selected[name] = record
    # Different harnesses/endpoints are expected; different actual model assets are not.
    models = {}
    for name, record in selected.items():
        row, model = record["primary"], record.get("source", {}).get("model_identity")
        if row.get("execution_status") == "completed" and row.get("classification") not in {"missing", "technical_error"} and model:
            models[name] = canonical_hash(_portable_model(model))
    model_issues = []
    if len(set(models.values())) > 1:
        model_issues.append("input records have different actual model/statistics/inference identities")
    conditions = {}
    for protocol in protocols:
        bits = condition(protocol)
        rows = [selected[e["episode_id"]] for e in expected_episodes(protocol)]
        item = _counts(rows, normal=bits == "00")
        keys = list(dict.fromkeys(e["task_id"] for e in expected_episodes(protocol)))
        item["tasks"] = [{"task_id": task, "official_task_id": next(e["libero_task_id"] for e in expected if e["task_id"] == task),
            **_counts([r for r in rows if r["primary"]["task_id"] == task], normal=bits == "00")} for task in keys]
        task_paths = [t["success_conditional_mean_path_m"] for t in item["tasks"]
                      if t["success_conditional_mean_path_m"] is not None]
        item["macro_success_conditional_mean_path_m"] = sum(task_paths) / len(task_paths) if task_paths and item["model_aggregation_compatible"] else None
        item["path_task_coverage"] = _rate(len(task_paths), len(keys)) if bits == "10" else None
        item["reuse_only"] = _counts([r for r in rows if r["primary"]["task_id"] in REUSE_TASKS], normal=bits == "00")
        item["new_three"] = _counts([r for r in rows if r["primary"]["task_id"] in NEW_TASKS], normal=bits == "00")
        item["selected_model_population"] = 30
        conditions[bits] = item
    return {"schema_version": SUMMARY_SCHEMA, "scoring_version": SCORING_VERSION,
        "conditions": conditions, "expected_all_conditions": 180, "new_model_episode_budget": 60,
        "episodes": selected, "model_compatibility_issues": model_issues,
        "model_identity_groups": {identity: [name for name, value in models.items() if value == identity]
                                  for identity in sorted(set(models.values()))},
        "note": "SR denominators are observed eligible executions, not missing future episodes. Each condition retains its fixed90 plan. Official00 and official10 are comparable; compliant10 is a separate quantity.",
        "simulation_created": False, "weights_loaded": False}


def render_report(report):
    lines = ["# LIBERO-Remain: nine LIBERO-10 compound tasks", "", report["note"], "",
        "| condition | official task | coverage n/N | official SR n/N (%) | compliant SR n/N (%) | success TCP (m) | path coverage n/N |", "|---|---|---|---|---|---|---|"]
    def display(rate):
        return "N/A" if rate is None or rate["percent"] is None else f"{rate['numerator']}/{rate['denominator']} ({rate['percent']:.2f}%)"
    for bits, item in report["conditions"].items():
        for task in item["tasks"]:
            coverage = task["coverage"]
            length = task['success_conditional_mean_path_m']
            length = "N/A" if length is None else f"{length:.5f}"
            pc = task['path_success_coverage']
            lines.append(f"| {bits} | {task['official_task_id']}: {task['task_id']} | {coverage['numerator']}/{coverage['denominator']} | {display(task['official_task_SR'])} | {display(task['compliant_task_SR'])} | {length} | {pc['numerator']}/{pc['denominator']} |")
        lines.extend(["", f"{bits}: planned90; observed {item['observed']}/90; official SR {display(item['official_task_SR'])}; compliant SR {display(item['compliant_task_SR'])}.",
            f"Legacy compliant diagnostic (available historical endpoints only): {display(item['legacy_compliant_SR'])}.", item["path_notice"], ""])
        if bits == "10":
            lines.append(f"Equal-task success-conditional TCP mean: {item['macro_success_conditional_mean_path_m']} m; task coverage {display(item['path_task_coverage'])}.")
    if report.get("model_compatibility_issues"):
        lines.extend(["", "Model identity mismatch: incompatible aggregates are N/A; original row scores remain in JSON, grouped by actual asset/configuration identity."])
    return "\n".join(lines) + "\n"


def save_report(output, report, *, update=False):
    output = Path(output)
    workflow.write_json(output / "summary.json", report, update=update)
    path = output / "report.md"
    if path.exists() and not update:
        raise ValueError("refusing to overwrite report")
    path.write_text(render_report(report), encoding="utf-8")


def read_batch(directory):
    directory = Path(directory).resolve()
    batch = read_json(directory / "batch.json")
    if (batch.get("schema_version") != BATCH_SCHEMA or batch.get("batch_identity_sha256") != canonical_hash(batch["identity"])
            or batch.get("expected") != expected_episodes(batch["protocol"])):
        raise ValueError("nine batch identity differs")
    plans = []
    for ref in batch["invocations"]:
        path = workflow._contained(directory, ref["plan"])
        if file_sha(path) != ref["sha256"]:
            raise ValueError("frozen invocation plan changed")
        plan = validate_plan(read_json(path))
        if plan["identity"] != batch["identity"] or plan["selected_episode_ids"] != batch["selected_episode_ids"]:
            raise ValueError("batch invocation changes identity/population")
        plans.append(plan)
    if not plans:
        raise ValueError("nine batch has no frozen invocation")
    if set(batch["episodes"]) - set(batch["selected_episode_ids"]):
        raise ValueError("batch cannot execute a historical reused episode")
    return batch, plans


def _collect(directory):
    directory = Path(directory).resolve()
    batch, plans = read_batch(directory)
    records = {name: deepcopy(record) for name, record in plans[-1]["reuse"]["episodes"].items()}
    issues = []
    for episode in batch["expected"]:
        if episode["task_id"] in REUSE_TASKS:
            continue
        name = episode["episode_id"]
        target = directory / "episodes" / name
        state = batch["episodes"].get(name, {})
        if not target.exists():
            records[name] = _missing(episode, state.get("error") or "not executed", state.get("status", "missing"))
            continue
        try:
            sources = [r["source_plan"] for plan in plans for r in plan["sources"]
                       if r["episode_id"] == name and r["status"] == "ready"]
            metadata, results = workflow._read_task(target, scoped=True, batch_identity=batch["batch_identity_sha256"],
                runtime=batch["identity"]["runtime_configs"]["libero_10"], sources=sources,
                model_identity=batch.get("loaded_model_identity"))
            if len(results) != 1:
                raise ValueError("single-source execution did not yield one verified result")
            result = results[0]
            record = score_verified_result(episode, result, condition=condition(batch["protocol"]), source={
                "run_path": str(directory), "task_run_path": str(target / "task_run.json"),
                "original_protocol": result["protocol_version"], "original_endpoint": result.get("endpoint_rule"),
                "source_harness_sha256": batch["identity"]["harness_source_sha256"],
                "model_identity": workflow._model_identity(metadata), "source_plan_sha256": metadata["source_plan"]["source_plan_sha256"],
                "input_evidence_level": "verified_raw_execution_video_and_source_archive",
                "verified_files": [{"path": str(directory / "batch.json"), "sha256": file_sha(directory / "batch.json"), "kind": "nine_batch"},
                    {"path": str(target / "task_run.json"), "sha256": file_sha(target / "task_run.json"), "kind": "task_run"}]})
            records[name] = record
        except (OSError, ValueError, KeyError, TypeError) as error:
            reason = f"{type(error).__name__}: {error}"
            issues.append({"episode_id": name, "error": reason})
            records[name] = _missing(episode, reason, "artifact_error")
    return batch, records, issues


def inspect_batch(directory):
    batch, records, issues = _collect(directory)
    report = make_report(records, protocols=[batch["protocol"]])
    report.update(run=str(Path(directory).resolve()), artifact_issues=issues,
                  selected_episode_ids=batch["selected_episode_ids"])
    return report


def summarize_runs(directories, reuse_path, output):
    from .nine_planning import read_reuse
    directories = [Path(p).resolve() for p in directories]
    output = Path(output).resolve()
    if any(output == p or p in output.parents or output in p.parents for p in directories):
        raise ValueError("derived report must be outside original run directories")
    if output.exists():
        raise FileExistsError("report output already exists")
    reuse = read_reuse(reuse_path)
    _check_output_isolation(output, {"reuse": reuse, "sources": []})
    records = deepcopy(reuse["episodes"])
    seen, issues = set(), []
    for directory in directories:
        batch, rows, failures = _collect(directory)
        issues.extend(failures)
        for episode in batch["expected"]:
            if episode["task_id"] not in NEW_TASKS:
                continue
            name = episode["episode_id"]
            if name in seen:
                raise ValueError("duplicate new episode across input runs; no best-run selection")
            seen.add(name)
            records[name] = rows[name]
    report = make_report(records)
    report["artifact_issues"] = issues
    output.mkdir(parents=True, exist_ok=False)
    save_report(output, report)
    return report


def _check_output_isolation(output, plan):
    roots = set()
    for record in plan["reuse"]["episodes"].values():
        if record.get("source", {}).get("run_path"):
            roots.add(Path(record["source"]["run_path"]).resolve())
    for row in plan["sources"]:
        if row["status"] == "ready" and row["source_plan"].get("source", {}).get("manifest"):
            roots.add(Path(row["source_plan"]["source"]["manifest"]).resolve().parent)
    if any(output == root or output in root.parents or root in output.parents for root in roots):
        raise ValueError("new output overlaps historical run or source evidence")


def run_batch(config_path, output, *, allow_missing=False, continue_run=False):
    plan = validate_plan(dry_plan(config_path))
    output = Path(output).resolve()
    _check_output_isolation(output, plan)
    if output.exists():
        if not continue_run:
            raise FileExistsError("existing output requires explicit --continue")
        batch, _ = read_batch(output)
        if batch["identity"] != plan["identity"]:
            raise ValueError("continuation changes frozen model/code/reuse/population identity")
    else:
        if continue_run:
            raise ValueError("--continue requires an existing nine-task run")
        batch = {"schema_version": BATCH_SCHEMA, "protocol": plan["protocol"],
            "identity": plan["identity"], "batch_identity_sha256": plan["batch_identity_sha256"],
            "expected": plan["expected"], "selected_episode_ids": plan["selected_episode_ids"],
            "episodes": {}, "invocations": []}
    def attempted(name):
        old = batch["episodes"].get(name, {})
        return old.get("attempted", False) or old.get("status") in {
            "running", "completed", "technical_error", "technical_pause", "artifact_error"}
    pending = [r for r in plan["sources"] if r["selected"] and not attempted(r["episode_id"])
               and not (output / "episodes" / r["episode_id"]).exists()]
    if not allow_missing and any(r["status"] != "ready" for r in pending):
        raise ValueError("new sources missing/failed; inspect or explicitly pass --allow-missing")
    output.mkdir(parents=True, exist_ok=True)
    path = f"plans/{len(batch['invocations']):03d}.json"
    workflow.write_json(output / path, plan)
    batch["invocations"].append({"plan": path, "sha256": file_sha(output / path),
        "allow_missing": bool(allow_missing), "explicit_continuation": bool(continue_run)})
    workflow.write_json(output / "batch.json", batch, update=(output / "batch.json").exists())
    policy = None
    def bind_model(actual):
        _check_reuse_model(plan["reuse"], actual)
        if batch.get("loaded_model_identity") not in (None, actual):
            raise ValueError("actual model/statistics changed across new sources")
        if "loaded_model_identity" not in batch:
            batch["loaded_model_identity"] = actual
            workflow.write_json(output / "batch.json", batch, update=True)
    try:
        for row in plan["sources"]:
            if not row["selected"]:
                continue
            name = row["episode_id"]
            target = output / "episodes" / name
            if target.exists():
                try:
                    sources = [r["source_plan"] for previous in read_batch(output)[1] for r in previous["sources"]
                               if r["episode_id"] == name and r["status"] == "ready"]
                    existing, _ = workflow._read_task(target, scoped=True, batch_identity=batch["batch_identity_sha256"],
                        runtime=plan["identity"]["runtime_configs"]["libero_10"], sources=sources,
                        model_identity=batch.get("loaded_model_identity"))
                    state = {"status": existing["status"], "error": existing["error"], "skipped_existing": True}
                except (OSError, ValueError, KeyError, TypeError) as error:
                    state = {"status": "artifact_error", "error": str(error), "skipped_existing": True}
            elif attempted(name):
                original = deepcopy(batch["episodes"][name].get("previous_attempt", batch["episodes"][name]))
                state = {"status": "artifact_error", "error": "previously attempted episode directory is missing; no automatic rerun",
                         "skipped_existing": True, "attempted": True, "previous_attempt": original}
                if original.get("error"):
                    state["error"] += "; original attempt: " + original["error"]
            elif row["status"] != "ready":
                state = {"status": row["status"], "error": row["error"], "model_queries": 0}
            else:
                # Durable intent precedes even worker loading: failed/missing evidence
                # must never turn an already attempted source into a fresh episode.
                batch["episodes"][name] = {"status": "running", "error": None, "attempted": True}
                workflow.write_json(output / "batch.json", batch, update=True)
                try:
                    if policy is None:
                        policy = workflow.make_policy(plan["identity"]["runtime_configs"]["libero_10"])
                    result = workflow._run_task(target, row["source_plan"],
                        plan["identity"]["runtime_configs"]["libero_10"], batch["batch_identity_sha256"], bind_model,
                        scoped=True, shared_policy=policy)
                    state = {"status": result["status"], "error": result["error"], "attempted": True}
                except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                    state = {"status": "technical_error", "error": f"{type(error).__name__}: {error}", "attempted": True}
                except KeyboardInterrupt as error:
                    batch["episodes"][name] = {"status": "technical_pause", "error": f"KeyboardInterrupt: {error}", "attempted": True}
                    workflow.write_json(output / "batch.json", batch, update=True)
                    raise
            batch["episodes"][name] = state
            workflow.write_json(output / "batch.json", batch, update=True)
    finally:
        try:
            if policy is not None:
                policy.close()
        finally:
            save_report(output, inspect_batch(output), update=(output / "summary.json").exists())
    return batch
