"""Versioned, file-only Task032 scores and read-only historical reuse records.

Report readers bind archived summaries to their frozen batch, plans and task
metadata. They explicitly do not claim to revalidate unread raw/video/observation
files. Raw fallback validates only the episode whose facts are needed.
"""
from copy import deepcopy
import math
from pathlib import Path

from .planning import canonical_hash, file_sha, planned_episodes, TASKS
from .metrics import _score_verified_episode
from .source_acceptance import _json

SCORING_VERSION = "remaining-headless-official00-drop-diagnostic-v1"
REUSE_TASKS = ("basket", "basket_cheese_butter", "stove", "dual_mugs", "mug_pudding", "basket_soup_cheese")
CLASSES = {"success", "failure", "unknown", "technical_error", "missing"}
SUPPORT_SCHEMA = "remaining-headless-table-support-rescore-v2"
SUPPORT_EPISODE_SCHEMA = "remaining-headless-derived-support-episode-v2"


def _condition(condition):
    if condition not in {"00", "10"}:
        raise ValueError("condition must be explicit 00 or 10")
    return condition


def _events(value, name):
    if not isinstance(value, list) or any(not isinstance(e, dict) or not isinstance(e.get("event"), str) for e in value):
        raise ValueError(f"{name} requires explicit event-typed records")
    return deepcopy(value)


def derive_row(legacy_row, *, condition, confirmed_events=None, event_unknown=None):
    """Derive main classification without changing any historical fact or row."""
    condition = _condition(condition)
    old = deepcopy(legacy_row)
    if old.get("classification") not in CLASSES:
        raise ValueError("unknown legacy classification")
    new = deepcopy(old)
    unknown_events = old.get("event_unknown") if event_unknown is None else event_unknown
    confirmed = [] if confirmed_events is None else _events(confirmed_events, "confirmed_events")
    new.update(scoring_version=SCORING_VERSION, condition=condition,
        legacy_classification=old["classification"], legacy_failure_reasons=deepcopy(old.get("failure_reasons", [])),
        legacy_unknown_reasons=deepcopy(old.get("unknown_reasons", [])),
        legacy_event_unknown=deepcopy(unknown_events), legacy_confirmed_events=confirmed)
    status = old.get("execution_status")
    if old["classification"] == "missing" or status == "missing":
        new.update(classification="missing", success=None)
    elif old["classification"] == "technical_error" or status != "completed":
        new.update(classification="technical_error", success=None)
    elif condition == "00":
        signal = old.get("official_goals_achieved")
        if signal is not None and type(signal) is not bool:
            raise ValueError("official goal signal must be boolean or absent")
        new.update(classification="unknown" if signal is None else "success" if signal else "failure",
            success=signal, failure_reasons=["official_goal_never_achieved"] if signal is False else [],
            unknown_reasons=["official_signal_missing"] if signal is None else [])
    else:
        unknown_events = _events(unknown_events, "event_unknown")
        retained = [e for e in unknown_events if e["event"] != "table_drop"]
        failures = [r for r in old.get("failure_reasons", []) if r != "table_drop"]
        for event in confirmed:
            if event["event"] != "table_drop" and event["event"] not in failures:
                failures.append(event["event"])
        unknown = [r for r in old.get("unknown_reasons", []) if r != "event_evidence_unknown"]
        if retained:
            unknown.insert(0, "event_evidence_unknown")
        classification = "failure" if failures else "unknown" if unknown else "success"
        new.update(classification=classification, success=False if failures else None if unknown else True,
            failure_reasons=failures, unknown_reasons=unknown, event_unknown=retained,
            confirmed_events=[e for e in confirmed if e["event"] != "table_drop"])
    new["classification_changed"] = old["classification"] != new["classification"]
    new["classification_diff"] = {"old": old["classification"], "new": new["classification"],
        "old_failure_reasons": deepcopy(old.get("failure_reasons", [])), "new_failure_reasons": deepcopy(new.get("failure_reasons", [])),
        "old_unknown_reasons": deepcopy(old.get("unknown_reasons", [])), "new_unknown_reasons": deepcopy(new.get("unknown_reasons", []))}
    return new


def _official_signal(result):
    signals = []
    for frame in result.get("trace", []):
        values = frame.get("official_goal_values", frame.get("goals"))
        if not isinstance(values, list) or not values or any(type(v) is not bool for v in values):
            raise ValueError("raw official goal values must be explicit booleans")
        signal = all(values)
        if "official_goal_values" not in frame and "invariant_values" in frame:
            invariants = frame["invariant_values"]
            if not isinstance(invariants, list) or any(type(v) is not bool for v in invariants):
                raise ValueError("raw invariant values must be explicit booleans")
            signal = signal and all(invariants)
        if "official_success" in frame and (type(frame["official_success"]) is not bool or frame["official_success"] != signal):
            raise ValueError("raw official_success differs from complete official predicates")
        signals.append(signal)
    declared = result.get("official_goals_achieved")
    if declared is not None and (type(declared) is not bool or declared != any(signals)):
        raise ValueError("raw official_goals_achieved does not match any official signal")
    if not signals and result.get("status") == "completed":
        return None
    return any(signals) if signals else declared


def score_verified_result(episode, result, *, condition, source=None, legacy_row=None):
    """The caller verifies protocol/source evidence; this checks official facts.

Pass the runtime's legacy_row when its protocol adds preservation conditions.
All non-table-drop reasons in that row survive the new10 derivation.
"""
    condition = _condition(condition)
    signal = _official_signal(result)
    legacy = deepcopy(legacy_row) if legacy_row is not None else _score_verified_episode(
        episode, result, {"path_complete": len(result["trace"]) == result["n_steps"] + 1})
    if legacy.get("episode_id") != episode.get("episode_id"):
        raise ValueError("legacy row belongs to a different episode")
    if legacy.get("official_goals_achieved") != result.get("official_goals_achieved"):
        raise ValueError("legacy official signal differs from raw")
    from .protocols import get_protocol
    nine_versions = {get_protocol(key).protocol_version for key in ("nine-normal00", "nine-mask10")}
    if result.get("protocol_version") in nine_versions:
        legacy["invariant_regression"] = deepcopy(result.get("invariant_regression"))
        if condition == "10" and legacy["invariant_regression"] is True:
            if "invariant_regression" not in legacy["failure_reasons"]:
                legacy["failure_reasons"].append("invariant_regression")
            if legacy.get("execution_status") == "completed":
                legacy.update(classification="failure", success=False)
    legacy_available = not (condition == "00" and result.get("protocol_version") == get_protocol("nine-normal00").protocol_version)
    diagnostic_reason = None
    if not legacy_available:
        diagnostic_reason = "new normal00 uses the official-success endpoint; the legacy release-plus-five-observation execution was not collected"
        legacy.update(legacy_diagnostic_available=False, legacy_diagnostic_reason=diagnostic_reason,
                      goal_confirmed_step=None)
        if legacy.get("execution_status") == "completed":
            legacy.update(classification="unknown", success=None, failure_reasons=[],
                          unknown_reasons=["legacy_endpoint_not_collected"])
    facts = deepcopy(legacy)
    facts["official_goals_achieved"] = signal
    # The primary row still reports the actual protocol's recorded endpoint.
    facts["goal_confirmed_step"] = result.get("goal_confirmed_step")
    provenance = deepcopy(source or {})
    provenance.setdefault("original_protocol", result.get("protocol_version"))
    provenance.setdefault("original_endpoint", {k: deepcopy(result.get(k)) for k in
        ("status", "exit_reason", "configuration", "n_steps", "goal_completion_step", "goal_confirmed_step")})
    return {"condition": condition, "legacy": legacy, "legacy_diagnostic_available": legacy_available,
        "legacy_diagnostic_reason": diagnostic_reason,
        "primary": derive_row(facts, condition=condition, confirmed_events=result.get("confirmed_events", []),
                              event_unknown=result.get("event_unknown")), "source": provenance}


class _Files:
    def __init__(self):
        self.files = {}

    def bytes(self, path, kind, expected_sha=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        import hashlib
        sha = hashlib.sha256(raw).hexdigest()
        if expected_sha is not None and expected_sha != sha:
            raise ValueError(f"{kind} file hash differs: {path}")
        if path in self.files and self.files[path]["sha256"] != sha:
            raise ValueError(f"source changed during derivation: {path}")
        self.files[path] = {"path": str(path), "kind": kind, "sha256": sha}
        return raw

    def read(self, path, kind, expected_sha=None):
        return _json(self.bytes(path, kind, expected_sha))

    def finish(self):
        for path, reference in self.files.items():
            if file_sha(path) != reference["sha256"]:
                raise ValueError(f"source changed during derivation: {path}")
        return list(self.files.values())


def _contained(directory, relative):
    from .workflow import _contained as contained
    return contained(directory, relative)


def _summary_rows(summary, expected, *, protocol, batch_identity=None):
    from .protocols import get_protocol
    descriptor = get_protocol(protocol)
    if (summary.get("schema_version") != descriptor.summary_schema or summary.get("protocol_version") != descriptor.protocol_version
            or batch_identity is not None and summary.get("batch_identity_sha256") != batch_identity):
        raise ValueError("summary identity/protocol differs from frozen batch")
    rows = summary.get("episodes")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("summary fixed population differs")
    indexed = {}
    planned = {e["episode_id"]: e for e in expected}
    for row in rows:
        name = row.get("episode_id")
        if name not in planned or name in indexed or row.get("classification") not in CLASSES:
            raise ValueError("summary has duplicate/unplanned/unclassified episodes")
        for key in ("task_id", "suite", "initial_state_index", "initial_mask"):
            if row.get(key) != planned[name][key]:
                raise ValueError(f"summary differs from planned {key}")
        indexed[name] = row
    return indexed


def _row_facts(row):
    """Malformed report facts are unavailable evidence, never a main success."""
    if row["classification"] == "missing":
        return
    for key in ("failure_reasons", "unknown_reasons"):
        if not isinstance(row.get(key), list) or any(not isinstance(reason, str) for reason in row[key]):
            raise ValueError(f"summary {key} requires explicit reasons")
    if "execution_status" in row:
        expected = {"runtime_error", "invalid_initial_state"} if row["classification"] == "technical_error" else {"completed"}
        if row["execution_status"] not in expected:
            raise ValueError("summary classification/execution status differs")
    if type(row.get("n_steps")) is not int or row["n_steps"] < 0:
        raise ValueError("summary n_steps requires the recorded nonnegative count")
    length = row.get("path_length_m")
    if type(length) not in (float, int) or not math.isfinite(length) or length < 0:
        raise ValueError("summary path requires the recorded finite TCP length")
    if row["classification"] != "technical_error" and row.get("path_complete") is not True:
        raise ValueError("completed summary requires a complete observed TCP path")
    if row.get("official_goals_achieved") is not None and type(row["official_goals_achieved"]) is not bool:
        raise ValueError("summary official signal must be boolean or absent")


def _metadata(directory, batch, plans, files, *, task, scoped):
    from . import workflow
    metadata = files.read(directory / "task_run.json", "task_run")
    source = metadata["source_plan"]
    schema = "remaining-headless-scoped-source-run-v1" if scoped else "remaining-headless-task-run-v1"
    allowed = [row["source_plan"] if scoped else row for plan in plans
               for row in plan["sources" if scoped else "tasks"]
               if row["status"] == "ready" and row["task_id"] == task]
    if (metadata.get("schema_version") != schema or metadata.get("protocol_version") != batch["protocol_version"]
            or metadata.get("batch_identity_sha256") != batch["batch_identity_sha256"]
            or metadata.get("status") not in {"completed", "technical_pause"}
            or source not in allowed or source.get("source_plan_sha256") != canonical_hash(
                {k: v for k, v in source.items() if k != "source_plan_sha256"})
            or metadata.get("runtime_config") != batch["identity"]["runtime_configs"][TASKS[task]["suite"]]):
        raise ValueError("task run identity/runtime/source differs from frozen plan")
    if metadata.get("model_runtime") is not None and batch.get("loaded_model_identity") is not None:
        if workflow.shared_model_identity(metadata["model_runtime"]) != batch["loaded_model_identity"]:
            raise ValueError("task model/checkpoint/statistics differs from archived batch")
    episodes = {e["episode_id"]: e for e in source["episodes"]}
    references = {}
    for reference in metadata["results"]:
        name = reference["episode_id"]
        if name not in episodes or name in references or reference.get("validation") not in {"verified", "partial_evidence"}:
            raise ValueError("invalid or duplicate task result reference")
        _contained(directory, reference["path"])
        references[name] = reference
    if set(metadata["missing"]) != set(episodes) - set(references):
        raise ValueError("task result/missing ledger differs")
    return metadata, episodes, references


def _provenance(run, directory, batch, metadata, episode, reference, files, level):
    from . import workflow
    identity = workflow.evidence_identity(metadata, episode)
    dependencies = [run / "batch.json", directory / "task_run.json", *[
        _contained(run, invocation["plan"]) for invocation in batch["invocations"]]]
    return {"input_evidence_level": level, "run_path": str(run), "run_id": metadata["run_id"],
        "original_protocol": metadata["protocol_version"], "batch_identity_sha256": batch["batch_identity_sha256"],
        "batch_sha256": files.files[run / "batch.json"]["sha256"],
        "source_harness_sha256": batch["identity"]["harness_source_sha256"],
        "model_identity": deepcopy(identity["model_identity"]), "original_identity_sha256": canonical_hash(identity),
        "original_identity": identity, "source_plan_sha256": metadata["source_plan"]["source_plan_sha256"],
        "source_origin": deepcopy(metadata["source_plan"].get("source")),
        "task_run": {"path": str(directory / "task_run.json"),
            "verified_file_sha256": files.files[directory / "task_run.json"]["sha256"]},
        "raw": {"path": str(_contained(directory, reference["path"])), "recorded_sha256": reference["sha256"],
            "verified_file_sha256": None}, "new_execution": False, "reuse_only": True,
        "verified_files": [deepcopy(files.files[path]) for path in dependencies]}


def _read_raw(directory, metadata, episode, reference, files):
    from .workflow import evidence_identity
    from .evidence import validate_evidence
    raw = files.read(_contained(directory, reference["path"]), "raw", reference["sha256"])
    dependencies = [_contained(directory, reference["path"])]
    evidence = raw.get("execution_evidence", {})
    if evidence.get("path") is not None:
        path = _contained(directory, evidence["path"])
        index = files.read(path, "execution_evidence", evidence["sha256"])
        dependencies.append(path)
        observations = [index.get("initial_observation"), *[query["observation"] for query in index.get("queries", [])]]
        for observation in observations:
            if observation is not None:
                image_path = _contained(path.parent, observation["path"])
                files.bytes(image_path, "observation", observation["sha256"])
                dependencies.append(image_path)
    valid = validate_evidence(directory, raw, episode, evidence_identity(metadata, episode))
    expected = "partial_evidence" if valid.get("verified") is False else "verified"
    if reference["validation"] != expected:
        raise ValueError("raw evidence verification differs from task result reference")
    return raw, [deepcopy(files.files[path]) for path in dependencies]


def _normal_chain(directory, files, seen=None):
    from . import scoped_workflow
    directory = Path(directory).resolve()
    seen = set() if seen is None else set(seen)
    if directory in seen:
        raise ValueError("cyclic prior run reference")
    seen.add(directory)
    files.read(directory / "batch.json", "batch")
    batch, plans = scoped_workflow.read_batch(directory)
    if batch["protocol"] != "normal00-control":
        raise ValueError("historical00 requires the original normal00 protocol")
    for invocation in batch["invocations"]:
        files.read(_contained(directory, invocation["plan"]), "plan", invocation["sha256"])
    chain = []
    prior = batch.get("prior_run")
    if prior is not None:
        prior_dir = Path(prior["directory"]).resolve()
        files.read(prior_dir / "batch.json", "prior_batch", prior["batch_sha256"])
        chain = _normal_chain(prior_dir, files, seen)
        old = chain[-1][1]
        scoped_workflow._compatible_prior(batch, old)
        model = next((item[1].get("loaded_model_identity") for item in reversed(chain)
                      if item[1].get("loaded_model_identity") is not None), None)
        if model is not None:
            if batch.get("loaded_model_identity") not in (None, model):
                raise ValueError("actual loaded model differs across prior run chain")
            batch = deepcopy(batch); batch["loaded_model_identity"] = model
    if (directory / "summary.json").exists():
        summary = files.read(directory / "summary.json", "summary")
        rows = _summary_rows(summary, batch["expected"], protocol="normal00-control", batch_identity=batch["batch_identity_sha256"])
    else:
        summary = {}
        rows = {e["episode_id"]: _score_verified_episode(e, None, None) for e in batch["expected"]}
    chain.append((directory, batch, plans, summary, rows))
    return chain


def _collect_normal(run, records, files, issues, selected):
    chain = _normal_chain(run, files)
    attempted = set()
    for directory, batch, plans, summary, rows in chain:
        selected.update(name for name in batch["selected_episode_ids"] if name in records)
        for name, row in rows.items():
            if name not in records or name not in batch["selected_episode_ids"]:
                continue
            task_dir = directory / "episodes" / name
            if not task_dir.exists():
                if name not in attempted and row["classification"] == "missing":
                    records[name]["legacy"] = deepcopy(row)
                    records[name]["primary"] = derive_row(row, condition="00")
                elif name not in attempted:
                    issues.append({"condition": "00", "episode_id": name, "task_id": row["task_id"],
                                   "reason": "summary claims a recorded episode without its source directory"})
                continue
            if name in attempted:
                raise ValueError("a historical source was attempted twice; cannot select a preferred result")
            attempted.add(name)
            try:
                _row_facts(row)
                artifact_issue = next((i for i in summary.get("unverified_task_artifacts", [])
                    if i.get("episode_id", name) == name and i.get("task_id") == row["task_id"]), None)
                if artifact_issue:
                    raise ValueError(f"archived summary reports unverified source: {artifact_issue['reason']}")
                metadata, episodes, references = _metadata(task_dir, batch, plans, files, task=row["task_id"], scoped=True)
                if name not in references:
                    if row["classification"] != "missing":
                        raise ValueError("summary claims an unrecorded episode")
                    continue
                source = _provenance(directory, task_dir, batch, metadata, episodes[name], references[name], files,
                                     "summary_with_bound_metadata")
                if summary:
                    source["summary"] = {"path": str(directory / "summary.json"),
                        "verified_file_sha256": files.files[directory / "summary.json"]["sha256"]}
                    source["verified_files"].append(deepcopy(files.files[directory / "summary.json"]))
                if not summary or "official_goals_achieved" not in row or "execution_status" not in row:
                    raw, dependencies = _read_raw(task_dir, metadata, episodes[name], references[name], files)
                    source["input_evidence_level"] = "raw_and_execution_evidence_verified"
                    source["raw"]["verified_file_sha256"] = references[name]["sha256"]
                    source["verified_files"].extend(dependencies)
                    records[name] = score_verified_result(episodes[name], raw, condition="00", source=source)
                else:
                    if row["classification"] == "missing":
                        raise ValueError("summary does not verify the recorded episode")
                    source["original_endpoint"] = {k: deepcopy(row.get(k)) for k in
                        ("execution_status", "exit_reason", "n_steps", "goal_confirmed_step")}
                    source["original_endpoint"]["configuration"] = {key: deepcopy(batch["identity"]["budget"][key])
                        for key in ("horizon", "confirmation_steps", "max_chunk_steps")}
                    records[name] = {"condition": "00", "legacy": deepcopy(row),
                        "primary": derive_row(row, condition="00"), "source": source}
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append({"condition": "00", "episode_id": name, "task_id": row["task_id"], "reason": f"{type(error).__name__}: {error}"})


def _legacy_batch(run, files):
    from . import workflow
    run = Path(run).resolve()
    files.read(run / "batch.json", "batch")
    batch = workflow.read_batch(run)
    plans = [files.read(_contained(run, inv["plan"]), "plan", inv["sha256"]) for inv in batch["invocations"]]
    return run, batch, plans


def _collect_support(derived, run, records, files, issues, selected):
    derived = Path(derived).resolve()
    summary = files.read(derived / "summary.json", "support_v2_summary")
    if summary.get("schema_version") != SUPPORT_SCHEMA or summary.get("derived_only") is not True or summary.get("new_execution") is not False:
        raise ValueError("not an immutable support-v2 derived report")
    run = Path(run if run is not None else summary["source"]["batch_path"]).resolve()
    files.read(run / "batch.json", "batch", summary["source"]["batch_sha256"])
    run, batch, plans = _legacy_batch(run, files)
    if summary["source"]["batch_identity_sha256"] != batch["batch_identity_sha256"]:
        raise ValueError("support report original batch identity differs")
    expected = planned_episodes()
    if summary.get("expected") != expected:
        raise ValueError("support report historical denominator differs")
    old_rows = _summary_rows(summary["old_summary"], expected, protocol="mask10")
    rows = _summary_rows(summary["new_summary"], expected, protocol="mask10")
    references = {}
    for reference in summary["derived_episodes"]:
        name = reference["episode_id"]
        if name not in rows or name in references:
            raise ValueError("duplicate or unplanned support-derived episode")
        references[name] = reference
    metadata_cache = {}
    for name, row in rows.items():
        if name not in records:
            continue
        if name not in references:
            if row["classification"] != "missing":
                issues.append({"condition": "10", "episode_id": name, "reason": "support summary has no episode artifact"})
            else:
                records[name]["legacy"] = deepcopy(row); records[name]["primary"] = derive_row(row, condition="10")
            continue
        selected.add(name)
        try:
            _row_facts(row)
            artifact = files.read(_contained(derived, references[name]["path"]), "support_v2_episode", references[name]["sha256"])
            if (artifact.get("schema_version") != SUPPORT_EPISODE_SCHEMA or artifact.get("episode_id") != name
                    or artifact.get("derived_only") is not True or artifact.get("new_execution") is not False
                    or artifact.get("new") != row or artifact.get("old") != old_rows[name]):
                raise ValueError("support episode identity/old/new summary differs")
            task = row["task_id"]
            task_dir = run / "tasks" / task
            if task not in metadata_cache:
                metadata_cache[task] = _metadata(task_dir, batch, plans, files, task=task, scoped=False)
            metadata, episodes, raw_references = metadata_cache[task]
            reference = raw_references[name]
            source = _provenance(run, task_dir, batch, metadata, episodes[name], reference, files,
                                 "support_v2_report_with_bound_metadata")
            original = artifact["source"]
            for key in ("batch_sha256", "batch_identity_sha256", "source_harness_sha256", "source_plan_sha256", "original_identity_sha256"):
                if original.get(key) != source[key]:
                    raise ValueError(f"support original {key} differs")
            if (original.get("task_run_sha256") != source["task_run"]["verified_file_sha256"]
                    or _contained(run, original["task_run_path"]) != task_dir / "task_run.json"
                    or original.get("raw_sha256") != reference["sha256"]
                    or _contained(run, original["raw_path"]) != _contained(task_dir, reference["path"])):
                raise ValueError("support original task/raw references differ")
            if artifact["event_unknown"] != row.get("event_unknown"):
                raise ValueError("support event_unknown differs from its old compliant row")
            for key in ("n_steps", "path_length_m", "goal_confirmed_step", "official_goals_achieved"):
                if artifact["preserved"][key] != row[key]:
                    raise ValueError(f"support preserved {key} differs")
            if artifact["preserved"]["status"] != row["execution_status"]:
                raise ValueError("support preserved execution status differs")
            source.update(original_endpoint=deepcopy(artifact["preserved"]),
                original_execution_evidence=deepcopy(original.get("original_execution_evidence")),
                original_measurement_static_sha256=original.get("original_measurement_static_sha256"),
                preserved_actions_sha256=artifact["preserved_actions_sha256"], preserved_queries_sha256=artifact["preserved_queries_sha256"],
                derived_episode={"path": str(_contained(derived, references[name]["path"])), "verified_file_sha256": references[name]["sha256"]},
                diagnostics_reference={"table_drop_trace": "derived_episode.table_drop_trace", "other_event_candidates": "raw.trace.event_candidates"})
            source["verified_files"].extend(deepcopy(files.files[path]) for path in
                (derived / "summary.json", _contained(derived, references[name]["path"])))
            records[name] = {"condition": "10", "legacy_original": deepcopy(artifact["old"]), "legacy": deepcopy(row),
                "primary": derive_row(row, condition="10", confirmed_events=artifact["confirmed_events"], event_unknown=artifact["event_unknown"]),
                "source": source}
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"condition": "10", "episode_id": name, "task_id": row["task_id"], "reason": f"{type(error).__name__}: {error}"})


def _collect_raw(run, records, files, issues, selected):
    run, batch, plans = _legacy_batch(run, files)
    for task in REUSE_TASKS:
        names = [name for name in records if records[name]["condition"] == "10" and records[name]["primary"]["task_id"] == task]
        directory = run / "tasks" / task
        if not names or not directory.exists():
            continue
        try:
            metadata, episodes, references = _metadata(directory, batch, plans, files, task=task, scoped=False)
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"condition": "10", "task_id": task, "reason": f"{type(error).__name__}: {error}"})
            continue
        for name in names:
            if name not in references:
                continue
            selected.add(name)
            try:
                raw, dependencies = _read_raw(directory, metadata, episodes[name], references[name], files)
                source = _provenance(run, directory, batch, metadata, episodes[name], references[name], files,
                                     "raw_and_execution_evidence_verified")
                source["raw"]["verified_file_sha256"] = references[name]["sha256"]
                source["original_execution_evidence"] = deepcopy(raw.get("execution_evidence"))
                source["verified_files"].extend(dependencies)
                records[name] = score_verified_result(episodes[name], raw, condition="10", source=source)
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append({"condition": "10", "episode_id": name, "task_id": task, "reason": f"{type(error).__name__}: {error}"})


def collect_reuse(*, normal00_run=None, mask10_rescore=None, mask10_run=None, task_ids=REUSE_TASKS):
    """Return reuse-only records for every requested old task/index/condition.

    Missing roots/invalid artifacts remain missing with explicit issues; they
    are never returned as execution candidates. mask10_run alongside a rescore
    only relocates that report's original batch, checked by its recorded hash.
    """
    tasks = tuple(task_ids)
    if len(set(tasks)) != len(tasks) or not set(tasks) <= set(REUSE_TASKS):
        raise ValueError("reuse is restricted to the six historical LIBERO-10 tasks")
    records = {}
    for task in tasks:
        for condition in ("00", "10"):
            for index in range(10):
                episode = {"episode_id": f"{task}_s{index:03d}_{condition}", "task_id": task,
                    "suite": "libero_10", "initial_state_index": index, "initial_mask": [condition == "10", False]}
                legacy = _score_verified_episode(episode, None, None)
                legacy["missing_reason"] = "historical evidence not supplied or not recorded"
                records[episode["episode_id"]] = {"condition": condition, "legacy": legacy,
                    "primary": derive_row(legacy, condition=condition),
                    "source": {"input_evidence_level": "missing", "new_execution": False, "reuse_only": True, "verified_files": []}}
    files, issues = _Files(), []
    selected = {"00": set(), "10": set()}
    for condition, supplied, operation in (
        ("00", normal00_run, lambda: _collect_normal(normal00_run, records, files, issues, selected["00"])),
        ("10", mask10_rescore or mask10_run, lambda: _collect_support(mask10_rescore, mask10_run, records, files, issues, selected["10"])
         if mask10_rescore is not None else _collect_raw(mask10_run, records, files, issues, selected["10"]))):
        if supplied is None:
            continue
        before = deepcopy(records)
        try:
            operation()
        except (OSError, ValueError, KeyError, TypeError) as error:
            for name, record in before.items():
                if record["condition"] == condition:
                    records[name] = record
            issues.append({"condition": condition, "path": str(supplied), "reason": f"{type(error).__name__}: {error}"})
    for issue in issues:
        for name, record in records.items():
            if (record["condition"] == issue["condition"] and record["primary"]["classification"] == "missing"
                    and issue.get("episode_id", name) == name and issue.get("task_id", record["primary"]["task_id"]) == record["primary"]["task_id"]):
                record["primary"]["missing_reason"] = record["legacy"]["missing_reason"] = issue["reason"]
    return {"schema_version": "remaining-headless-historical-reuse-v1", "scoring_version": SCORING_VERSION,
        "episodes": records, "source_files": files.finish(), "issues": issues,
        "selected_episode_ids": {condition: sorted(names) for condition, names in selected.items()},
        "derived_only": True, "new_execution": False, "simulation_created": False, "weights_loaded": False}
