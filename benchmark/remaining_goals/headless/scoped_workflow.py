"""Task031 per-source execution; immutable invocations and explicit continuation."""
from copy import deepcopy
from pathlib import Path

from . import workflow
from .planning import canonical_hash, file_sha
from .source_acceptance import _json
from .scoped_planning import (dry_plan, validate_plan, expected_episodes,
    runtime_protocol, protocol_version)

BATCH_SCHEMA = "remaining-headless-scoped-batch-run-v1"


def _read(path):
    return _json(Path(path).read_bytes())


def read_batch(directory):
    directory = Path(directory).resolve()
    batch = _read(directory / "batch.json")
    if (batch.get("schema_version") != BATCH_SCHEMA
            or batch.get("protocol_version") != protocol_version(batch["protocol"])
            or batch.get("expected") != expected_episodes(batch["protocol"])
            or batch.get("batch_identity_sha256") != canonical_hash(batch["identity"])
            or not isinstance(batch.get("episodes"), dict) or not isinstance(batch.get("invocations"), list)):
        raise ValueError("scoped batch identity/denominator invalid")
    plans = []
    for invocation in batch["invocations"]:
        path = workflow._contained(directory, invocation["plan"])
        if file_sha(path) != invocation["sha256"]:
            raise ValueError("frozen invocation plan bytes changed")
        plan = validate_plan(_read(path))
        if plan["identity"] != batch["identity"] or plan["protocol"] != batch["protocol"]:
            raise ValueError("invocation changes scoped batch identity")
        plans.append(plan)
    if not plans or batch.get("selected_episode_ids") != plans[0]["selected_episode_ids"]:
        raise ValueError("batch selection differs from frozen plan")
    if set(batch["episodes"]) - set(batch["selected_episode_ids"]):
        raise ValueError("unselected episode in scoped execution ledger")
    return batch, plans


def _compatible_prior(current, prior):
    # Population differs between first80 and remaining20; actual code/model and
    # normal protocol must agree. Never combine mask10 and normal00 as one run.
    if (current["protocol"] != "normal00-control" or prior["protocol"] != current["protocol"]
            or any(current["identity"][k] != prior["identity"][k]
                   for k in ("runtime_configs", "harness_source_sha256"))):
        raise ValueError("prior run must use the same normal00 code/model/protocol")


def _collect(directory, seen=None):
    directory = Path(directory).resolve()
    seen = set() if seen is None else set(seen)
    if directory in seen:
        raise ValueError("cyclic prior run reference")
    seen.add(directory)
    batch, plans = read_batch(directory)
    results, issues, attempted = [], [], set()
    prior = batch.get("prior_run")
    if prior is not None:
        path = Path(prior["directory"]).resolve()
        if file_sha(path / "batch.json") != prior["batch_sha256"]:
            raise ValueError("prior run changed; retain frozen original evidence")
        old, old_results, old_issues, old_attempted = _collect(path, seen)
        _compatible_prior(batch, old)
        old_model = old.get("loaded_model_identity")
        if old_model is not None:
            if batch.get("loaded_model_identity") not in (None, old_model):
                raise ValueError("actual loaded model differs across prior run chain")
            # An invocation which loaded no model still carries its ancestors'
            # actual identity forward for all subsequent action/reader checks.
            batch = deepcopy(batch)
            batch["loaded_model_identity"] = old_model
        # The combined report includes unavailable/technical prior sources too,
        # not only sources with raw results. Keep frozen files unchanged.
        execution = deepcopy(old["episodes"])
        for name, state in batch["episodes"].items():
            if state.get("status") == "reused_prior" and name in execution:
                execution[name] = {**execution[name], "reused_prior": True}
            else:
                execution[name] = deepcopy(state)
        batch = deepcopy(batch)
        batch["episodes"] = execution
        results.extend(old_results); issues.extend(old_issues); attempted.update(old_attempted)
    sources = {}
    for plan in plans:
        for row in plan["sources"]:
            if row["status"] == "ready":
                sources.setdefault(row["episode_id"], []).append(row["source_plan"])
    expected = {e["episode_id"]: e for e in batch["expected"]}
    for name in batch["selected_episode_ids"]:
        path = directory / "episodes" / name
        if not path.exists():
            continue
        if name in attempted:
            raise ValueError("a prior source was attempted twice; no implicit retries")
        attempted.add(name)
        try:
            _, rows = workflow._read_task(path, scoped=True,
                batch_identity=batch["batch_identity_sha256"],
                runtime=batch["identity"]["runtime_configs"][expected[name]["suite"]],
                sources=sources.get(name, []), model_identity=batch.get("loaded_model_identity"))
            if any(r["episode_id"] != name for r in rows):
                raise ValueError("source result directory identity differs")
            results.extend(rows)
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"task_id": expected[name]["task_id"], "episode_id": name,
                           "reason": f"{type(error).__name__}: {error}"})
    return batch, results, issues, attempted


def inspect_batch(directory, output=None):
    from .metrics import summarize
    directory = Path(directory).resolve()
    batch, results, issues, attempted = _collect(directory)
    summary = summarize(batch["expected"], results, protocol=runtime_protocol(batch["protocol"]))
    summary.update(protocol=batch["protocol"], population=batch["identity"]["config"]["population"],
        selected_count=len(batch["selected_episode_ids"]), attempted_count=len(attempted),
        task_execution=deepcopy(batch["episodes"]), unverified_task_artifacts=issues,
        batch_identity_sha256=batch["batch_identity_sha256"], prior_run=deepcopy(batch.get("prior_run")))
    for row in summary["episodes"]:
        if row["classification"] == "missing":
            state = batch["episodes"].get(row["episode_id"], {})
            row["missing_reason"] = next((i["reason"] for i in issues if i["episode_id"] == row["episode_id"]),
                state.get("error") or ("not selected in this phase" if row["episode_id"] not in batch["selected_episode_ids"] else "not run"))
    if output is not None:
        out = Path(output).resolve()
        if out == directory or directory in out.parents:
            raise ValueError("derived summary must be outside the original run")
        out.mkdir(parents=True, exist_ok=False)
        workflow.save_summary(out, summary)
    return summary


def run_batch(config_path, output, *, allow_missing=False, continue_run=False, prior_run=None):
    plan = validate_plan(dry_plan(config_path))
    output = Path(output).resolve()
    batch_path = output / "batch.json"
    prior_attempted = set()
    prior_binding = None
    if prior_run is not None:
        prior_path = Path(prior_run).resolve()
        if prior_path == output or output in prior_path.parents or prior_path in output.parents:
            raise ValueError("prior and new run directories must be separate")
        prior, _, prior_issues, prior_attempted = _collect(prior_path)
        _compatible_prior(plan, prior)
        if prior_issues:
            raise ValueError("prior run has unverified artifacts; no automatic retry or imputation")
        prior_binding = {"directory": str(prior_path), "batch_sha256": file_sha(prior_path / "batch.json")}
    if output.exists():
        if not continue_run:
            raise ValueError("existing output requires explicit --continue; no automatic retry")
        batch, _ = read_batch(output)
        if batch["identity"] != plan["identity"] or batch.get("prior_run") != prior_binding:
            raise ValueError("continuation changes code/model/population or prior run")
    else:
        if continue_run:
            raise ValueError("--continue requires an existing scoped run")
        batch = {"schema_version": BATCH_SCHEMA, "protocol": plan["protocol"],
            "protocol_version": plan["protocol_version"], "identity": plan["identity"],
            "batch_identity_sha256": plan["batch_identity_sha256"], "expected": plan["expected"],
            "selected_episode_ids": plan["selected_episode_ids"], "prior_run": prior_binding,
            "episodes": {}, "invocations": []}
    pending = [r for r in plan["sources"] if r["selected"] and r["episode_id"] not in prior_attempted
               and not (output / "episodes" / r["episode_id"]).exists()]
    if not allow_missing and any(r["status"] != "ready" for r in pending):
        raise ValueError("selected source evidence is missing/failed; inspect it or explicitly use --allow-missing")
    output.mkdir(parents=True, exist_ok=True)
    plan_name = f"plans/{len(batch['invocations']):03d}.json"
    workflow.write_json(output / plan_name, plan)
    batch["invocations"].append({"plan": plan_name, "sha256": file_sha(output / plan_name),
                                 "allow_missing": bool(allow_missing), "explicit_continuation": bool(continue_run)})
    workflow.write_json(batch_path, batch, update=batch_path.exists())
    def bind_model(actual):
        if "loaded_model_identity" not in batch:
            if prior_run is not None and prior.get("loaded_model_identity") not in (None, actual):
                raise ValueError("loaded model differs from prior run")
            batch["loaded_model_identity"] = actual
            workflow.write_json(batch_path, batch, update=True)
        elif batch["loaded_model_identity"] != actual:
            raise ValueError("loaded model/statistics changed across sources")
    policy, suite = None, None
    try:
        # Reuse one loaded policy within each suite, close before the other suite.
        # Each source has its own archived origin/environment and failure record.
        for row in sorted(plan["sources"], key=lambda r: (r["suite"], r["task_id"], r["initial_state_index"])):
            if not row["selected"]:
                continue
            name = row["episode_id"]
            directory = output / "episodes" / name
            if name in prior_attempted:
                batch["episodes"][name] = {"status": "reused_prior", "error": None}
            elif directory.exists():
                try:
                    existing_sources = [r["source_plan"] for p in read_batch(output)[1]
                        for r in p["sources"] if r["episode_id"] == name and r["status"] == "ready"]
                    existing, _ = workflow._read_task(directory, scoped=True,
                        batch_identity=batch["batch_identity_sha256"],
                        runtime=plan["identity"]["runtime_configs"][row["suite"]],
                        sources=existing_sources, model_identity=batch.get("loaded_model_identity"))
                    batch["episodes"][name] = {"status": existing["status"], "error": existing["error"], "skipped_existing": True}
                except (OSError, ValueError, KeyError, TypeError) as error:
                    batch["episodes"][name] = {"status": "artifact_error", "error": str(error), "skipped_existing": True}
            elif row["status"] != "ready":
                batch["episodes"][name] = {"status": row["status"], "error": row["error"], "model_queries": 0}
            else:
                try:
                    if policy is None or suite != row["suite"]:
                        if policy is not None:
                            closing, policy = policy, None
                            closing.close()
                        suite = row["suite"]
                        policy = workflow.make_policy(plan["identity"]["runtime_configs"][suite])
                    result = workflow._run_task(directory, row["source_plan"],
                        plan["identity"]["runtime_configs"][suite], batch["batch_identity_sha256"], bind_model,
                        scoped=True, shared_policy=policy)
                    batch["episodes"][name] = {"status": result["status"], "error": result["error"]}
                except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                    batch["episodes"][name] = {"status": "technical_error", "error": f"{type(error).__name__}: {error}"}
            workflow.write_json(batch_path, batch, update=True)
    finally:
        try:
            if policy is not None:
                policy.close()
        finally:
            workflow.save_summary(output, inspect_batch(output), update=(output / "summary.json").exists())
    return batch
