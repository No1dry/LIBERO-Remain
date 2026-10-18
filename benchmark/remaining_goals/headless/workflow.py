"""Independent tasks within a fixed 100-source batch; no implicit retries."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import csv
import hashlib
import os
from pathlib import Path
import uuid

from .planning import (PROTOCOL, VIDEO, HORIZON, CONFIRMATION, CHUNK, TASK_TRACKS,
    COMMON_TEN_TASKS, TASKS, canonical_hash, file_sha, read_json, dry_plan,
    validate_plan, planned_episodes)


def write_json(path, value, *, update=False):
    path = Path(path)
    if path.exists() and not update:
        raise ValueError(f"refusing to overwrite {path}")
    body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _contained(directory, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("run artifact must use a relative path")
    path = (Path(directory) / relative).resolve()
    if not path.is_relative_to(Path(directory).resolve()):
        raise ValueError("artifact path escapes the task run")
    return path


def make_policy(config):
    from ..isolated_policy import SubprocessPolicy
    return SubprocessPolicy(config)


def make_environment(config):
    from .environment import make_env
    return make_env(config)


def make_recorder(path, episode):
    from ..video import EpisodeVideoRecorder
    return EpisodeVideoRecorder(path, VIDEO, environment_name="libero", episode=episode)


def evidence_identity(metadata, episode):
    identity = {"protocol_version": PROTOCOL, "run_id": metadata["run_id"],
            "batch_identity_sha256": metadata["batch_identity_sha256"],
            "source_plan_sha256": metadata["source_plan"]["source_plan_sha256"],
            "runtime_config_sha256": canonical_hash(metadata["runtime_config"]),
            "model_runtime_sha256": canonical_hash(metadata["model_runtime"]),
            "model_identity": _model_identity(metadata),
            "episode_id": episode["episode_id"], "state_sha256": episode["state_sha256"],
            "suite": episode["suite"], "evaluation_track": episode["evaluation_track"],
            "policy_seed": 7, "horizon": HORIZON, "confirmation_steps": CONFIRMATION,
            "max_chunk_steps": CHUNK}
    scope = metadata["source_plan"].get("source_acceptance")
    if scope is not None:
        identity["source_acceptance"] = {key: deepcopy(scope[key]) for key in
            ("schema_version", "acceptance_scope", "selection_sha256", "selected_episode_ids")}
    return identity


def _validate_source_snapshot(directory, plan):
    """Recheck selected evidence without consulting the live preparation tree."""
    if "source_acceptance" in plan:
        from .source_acceptance import validate_mask10_snapshot
        names = plan["source_snapshot_files"]
        validate_mask10_snapshot(plan["task_id"],
            _contained(directory / "source/manifest_files", names["manifest"]),
            _contained(directory / "source/replay_files", names["replay"]), plan["source_acceptance"])


def _archive_mask10_source(directory, plan):
    roots = {"manifest": Path(plan["source"]["manifest"]).parent,
             "replay": Path(plan["source"]["candidate_replay"]).parent}
    for item in plan["source_acceptance"]["selected_files"]:
        root = item["root"]
        raw = _contained(roots[root], item["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("selected mask10 evidence changed after planning")
        destination = _contained(directory / "source" / (root + "_files"), item["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
    _validate_source_snapshot(directory, plan)


def _model_identity(metadata):
    policy = metadata["model_runtime"]["policy_metadata"]
    return {"checkpoint": metadata["runtime_config"]["adapter_options"]["checkpoint"],
            "checkpoint_source": metadata["runtime_config"]["checkpoint_source"],
            "policy_metadata": deepcopy(policy),
            "model_runtime_sha256": canonical_hash(metadata["model_runtime"])}


def shared_model_identity(metadata):
    """Actual loaded assets must agree across both tracks before any action."""
    policy = metadata["policy_metadata"]
    keys = ("checkpoint", "checkpoint_source", "checkpoint_training_suites", "repo_commit",
            "unnorm_key", "dataset_statistics_sha256", "normalization_statistics_sha256",
            "inference_source_sha256", "component_checkpoint_sha256", "inference_configuration",
            "prepared_checkpoint_code_sha256")
    if policy["unnorm_key"] != "libero_10_no_noops":
        raise ValueError("task011 requires the same actual SOG10 no_noops statistics on both tracks")
    return {key: deepcopy(policy.get(key)) for key in keys}


def _read_task(directory, *, batch_identity=None, runtime=None, sources=None, model_identity=None, allow_partial=False):
    from .schema import validate_result
    from .evidence import validate_evidence
    from ..adapters.oft_transfer import validate_policy_metadata
    directory = Path(directory)
    metadata = read_json(directory / "task_run.json")
    if (metadata.get("schema_version") != "remaining-headless-task-run-v1"
            or metadata.get("protocol_version") != PROTOCOL
            or metadata.get("status") not in {"completed", "technical_pause"}
            or batch_identity is not None and metadata["batch_identity_sha256"] != batch_identity):
        raise ValueError("incomplete or incompatible task run; preserve it, never silently rerun")
    plan = metadata["source_plan"]
    if runtime is not None and metadata["runtime_config"] != runtime:
        raise ValueError("task runtime differs from frozen batch configuration")
    if sources is not None and plan not in sources:
        raise ValueError("task sources do not belong to a frozen invocation plan")
    if plan["source_plan_sha256"] != canonical_hash({k: v for k, v in plan.items() if k != "source_plan_sha256"}):
        raise ValueError("source plan hash mismatch")
    for name, sha in plan["source_files"].items():
        if file_sha(_contained(directory / "source", name)) != sha:
            raise ValueError("archived source/replay bytes changed")
    if read_json(directory / "source/manifest.json") != plan["manifest"]:
        raise ValueError("source plan manifest differs from archived source")
    _validate_source_snapshot(directory, plan)
    episodes = {e["episode_id"]: e for e in plan["episodes"]}
    if len(episodes) != 10 or sorted(e["initial_state_index"] for e in episodes.values()) != list(range(10)):
        raise ValueError("task source denominator differs")
    if metadata["model_runtime"] is not None:
        validate_policy_metadata(metadata["runtime_config"], metadata["model_runtime"]["policy_metadata"])
        if model_identity is not None and shared_model_identity(metadata["model_runtime"]) != model_identity:
            raise ValueError("task model/statistics differ from batch assets")
    results, seen, issues = [], set(), []
    for reference in metadata["results"]:
        name = reference["episode_id"]
        if name not in episodes or name in seen:
            raise ValueError("unexpected or duplicate task result")
        seen.add(name)
        try:
            path = _contained(directory, reference["path"])
            if file_sha(path) != reference["sha256"]:
                raise ValueError("raw episode bytes changed")
            result = read_json(path)
            identity = evidence_identity(metadata, episodes[name])
            if result.get("source_acceptance") != identity.get("source_acceptance"):
                raise ValueError("raw result source acceptance scope differs from its task run")
            validate_result(result, episodes[name], identity)
            if result.get("model_identity") != _model_identity(metadata):
                raise ValueError("raw model/normalization identity differs from its task run")
            validation = validate_evidence(directory, result, episodes[name], identity)
            expected_validation = "partial_evidence" if validation.get("verified") is False else "verified"
            if reference.get("validation") != expected_validation:
                raise ValueError("unverified raw result retained for diagnosis, cannot score")
            video = result.get("video", {})
            if result["status"] == "completed" and video.get("status") != "saved":
                raise ValueError("completed episode is missing its full video")
            if video.get("status") == "saved" and file_sha(_contained(directory, video["path"])) != video.get("sha256"):
                raise ValueError("video bytes changed")
            results.append(result)
        except (OSError, ValueError, KeyError, TypeError) as error:
            if not allow_partial:
                raise
            issues.append({"task_id": plan["task_id"], "episode_id": name, "reason": f"{type(error).__name__}: {error}"})
    if (set(metadata["missing"]) != set(episodes) - seen or len(metadata["missing"]) != len(set(metadata["missing"]))
            or metadata["status"] == "completed" and (metadata["missing"] or any(r["status"] != "completed" for r in results))):
        raise ValueError("fixed task denominator/missing ledger differs")
    metadata["artifact_issues"] = issues
    return metadata, results


def _run_task(directory, source, runtime, batch_identity, bind_model):
    from .runner import run_episode
    from .evidence import HeadlessEvidence, validate_evidence
    from ..adapters.oft_transfer import validate_policy_metadata
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "source").mkdir()
    for name, origin in (("manifest.json", source["source"]["manifest"]),
                         ("replay_report.json", source["source"]["candidate_replay"])):
        raw = Path(origin).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["source_files"][name]:
            raise ValueError("source changed after planning")
        (directory / "source" / name).write_bytes(raw)
    if "source_acceptance" in source:
        _archive_mask10_source(directory, source)
    metadata = {"schema_version": "remaining-headless-task-run-v1", "protocol_version": PROTOCOL,
                "run_id": uuid.uuid4().hex, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "batch_identity_sha256": batch_identity, "source_plan": source,
                "runtime_config": runtime, "model_runtime": None, "status": "running",
                "phase": "initialization", "error": None, "cleanup_errors": [], "attempts": [],
                "results": [], "missing": [e["episode_id"] for e in source["episodes"]]}
    write_json(directory / "task_run.json", metadata)
    policy = env = None
    interrupted = False
    try:
        metadata["phase"] = "policy_initialize"
        write_json(directory / "task_run.json", metadata, update=True)
        policy = make_policy(runtime)
        metadata["model_runtime"] = deepcopy(policy.provenance)
        validate_policy_metadata(runtime, metadata["model_runtime"]["policy_metadata"])
        bind_model(shared_model_identity(metadata["model_runtime"]))
        metadata["phase"] = "environment_initialize"
        write_json(directory / "task_run.json", metadata, update=True)
        environment_config = deepcopy(source["environment_config"])
        if "source_acceptance" in source:
            environment_config["manifest_dir"] = str(directory / "source/manifest_files")
        env = make_environment(environment_config)
        for episode in source["episodes"]:
            name = episode["episode_id"]
            metadata["phase"] = "episode_setup"
            metadata["attempts"].append(name)
            write_json(directory / "task_run.json", metadata, update=True)
            identity = evidence_identity(metadata, episode)
            recorder = make_recorder(directory / "videos" / (name + ".mp4"), episode)
            try:
                evidence = HeadlessEvidence(directory / "evidence" / name, identity)
            except BaseException:
                try:
                    recorder.close()
                except BaseException as cleanup_error:
                    metadata["cleanup_errors"].append(f"{type(cleanup_error).__name__}: {cleanup_error}")
                raise
            result = run_episode(env, policy, episode, horizon=HORIZON, confirmation_steps=CONFIRMATION,
                                 max_chunk_steps=CHUNK, recorder=recorder, evidence=evidence, identity=identity)
            interrupted = bool(result.get("interrupted"))
            metadata["phase"] = "artifact_verification"
            # Even a failed video finalization must leave the executed trace.
            artifact_error = None
            try:
                if result.get("video", {}).get("status") == "saved":
                    result["video"].update(path=f"videos/{name}.mp4", sha256=file_sha(directory / "videos" / (name + ".mp4")))
                elif result["status"] == "completed":
                    raise ValueError("completed episode is missing its full video")
            except Exception as error:
                artifact_error = error
            raw_path = f"raw/{name}.json"
            write_json(directory / raw_path, result)
            ref = {"episode_id": name, "path": raw_path, "sha256": file_sha(directory / raw_path), "validation": "pending"}
            metadata["results"].append(ref)
            metadata["missing"].remove(name)
            write_json(directory / "task_run.json", metadata, update=True)
            if artifact_error is not None:
                raise artifact_error
            validation = validate_evidence(directory, result, episode, identity)
            ref["validation"] = "partial_evidence" if validation.get("verified") is False else "verified"
            write_json(directory / "task_run.json", metadata, update=True)
            if result.get("interrupted"):
                raise KeyboardInterrupt("episode interrupted; evidence retained, remaining tasks not started")
            if result["status"] != "completed":
                raise RuntimeError(f"technical pause for {name}: {result.get('error')}")
        metadata["status"] = "completed"
    except BaseException as error:
        metadata.update(status="technical_pause", error=f"{type(error).__name__}: {error}")
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        if interrupted:
            raise KeyboardInterrupt("episode interrupted; artifact error retained, remaining tasks not started") from error
    finally:
        for resource in (env, policy):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    metadata["cleanup_errors"].append(f"{type(error).__name__}: {error}")
                    metadata["status"] = "technical_pause"
        write_json(directory / "task_run.json", metadata, update=True)
    return metadata


def _bound_task(output, batch, task, *, allow_partial=False):
    sources = []
    for invocation in batch["invocations"]:
        path = _contained(output, invocation["plan"])
        if file_sha(path) != invocation["sha256"]:
            raise ValueError("batch plan bytes changed")
        plan = validate_plan(read_json(path))
        if plan["identity"] != batch["identity"]:
            raise ValueError("batch invocation changes model/code/config")
        sources.extend(row for row in plan["tasks"] if row["task_id"] == task and row["status"] == "ready")
    return _read_task(output / "tasks" / task, batch_identity=batch["batch_identity_sha256"],
                      runtime=batch["identity"]["runtime_configs"][TASKS[task]["suite"]],
                      sources=sources, model_identity=batch.get("loaded_model_identity"), allow_partial=allow_partial)


def _summary(output, batch):
    from .metrics import summarize
    results, issues, source_acceptance = [], [], {}
    for task in COMMON_TEN_TASKS:
        directory = output / "tasks" / task
        if not directory.exists():
            continue
        try:
            metadata, rows = _bound_task(output, batch, task, allow_partial=True)
            results.extend(rows)
            issues.extend(metadata["artifact_issues"])
            if "source_acceptance" in metadata["source_plan"]:
                source_acceptance[task] = deepcopy(metadata["source_plan"]["source_acceptance"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"task_id": task, "reason": f"{type(error).__name__}: {error}"})
    summary = summarize(planned_episodes(), results)
    summary["task_execution"] = deepcopy(batch["tasks"])
    summary["unverified_task_artifacts"] = issues
    summary["batch_identity_sha256"] = batch["batch_identity_sha256"]
    if "source_acceptance" in batch["identity"]["config"]:
        summary["source_acceptance_version"] = batch["identity"]["config"]["source_acceptance"]
        summary["source_acceptance"] = source_acceptance
    for row in summary["episodes"]:
        if row["classification"] == "missing":
            issue = next((i["reason"] for i in issues if i["task_id"] == row["task_id"]
                          and i.get("episode_id", row["episode_id"]) == row["episode_id"]), None)
            row["missing_reason"] = issue or batch["tasks"].get(row["task_id"], {}).get("error") or "not run"
    return summary


def save_summary(output, summary, *, update=False):
    from .metrics import render_report
    write_json(output / "summary.json", summary, update=update)
    report = render_report(summary)
    report += "\n## Task execution and artifact errors\n\n" + json.dumps(
        {"tasks": summary["task_execution"], "unverified": summary["unverified_task_artifacts"]},
        ensure_ascii=False, indent=2) + "\n"
    (output / "report.md").write_text(report, encoding="utf-8")
    fields = list(dict.fromkeys(key for row in summary["episodes"] for key in row))
    with (output / "episodes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in summary["episodes"]:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})


def run_batch(config_path, output, *, track="all"):
    if track not in {"all", "primary", "extension"}:
        raise ValueError("select all, primary or extension")
    plan = validate_plan(dry_plan(config_path))
    output = Path(output).resolve()
    batch_file = output / "batch.json"
    if output.exists():
        batch = read_json(batch_file)
        if batch.get("identity") != plan["identity"] or batch.get("batch_identity_sha256") != plan["batch_identity_sha256"]:
            raise ValueError("existing batch is bound to another config/code; do not overwrite or silently retry")
    else:
        output.mkdir(parents=True)
        batch = {"schema_version": "remaining-headless-batch-run-v1", "protocol_version": PROTOCOL,
                 "identity": plan["identity"], "batch_identity_sha256": plan["batch_identity_sha256"],
                 "expected": planned_episodes(), "tasks": {}, "invocations": []}
    invocation = len(batch["invocations"])
    plan_name = f"plans/{invocation:03d}.json"
    write_json(output / plan_name, plan)
    batch["invocations"].append({"track": track, "plan": plan_name, "sha256": file_sha(output / plan_name)})
    write_json(batch_file, batch, update=batch_file.exists())
    def bind_model(actual):
        if "loaded_model_identity" not in batch:
            batch["loaded_model_identity"] = actual
            write_json(batch_file, batch, update=True)
        elif batch["loaded_model_identity"] != actual:
            raise ValueError("loaded model/source/statistics changed across tasks; no actions executed")
    selected = set(COMMON_TEN_TASKS if track == "all" else TASK_TRACKS[track]["tasks"])
    try:
        for row in plan["tasks"]:
            task = row["task_id"]
            if task not in selected:
                continue
            directory = output / "tasks" / task
            if directory.exists():
                try:
                    prior, _ = _bound_task(output, batch, task)
                    status = {"status": prior["status"], "skipped_existing": True, "error": prior["error"]}
                except (OSError, ValueError, KeyError, TypeError) as error:
                    status = {"status": "artifact_error", "skipped_existing": True, "error": str(error)}
            elif row["status"] != "ready":
                status = {"status": "preparation_error", "error": row["error"], "model_queries": 0}
            else:
                try:
                    result = _run_task(directory, row, plan["identity"]["runtime_configs"][row["suite"]],
                                       batch["batch_identity_sha256"], bind_model)
                    status = {"status": result["status"], "error": result["error"], "skipped_existing": False}
                except BaseException as error:
                    status = {"status": "technical_pause", "error": f"{type(error).__name__}: {error}"}
                    if isinstance(error, (KeyboardInterrupt, SystemExit)):
                        batch["tasks"][task] = status
                        write_json(batch_file, batch, update=True)
                        raise
            batch["tasks"][task] = status
            write_json(batch_file, batch, update=True)
    finally:
        save_summary(output, _summary(output, batch), update=(output / "summary.json").exists())
    return batch


def read_batch(directory):
    """Read the frozen batch and invocation identities without scoring episodes."""
    directory = Path(directory).resolve()
    batch = read_json(directory / "batch.json")
    if (batch.get("schema_version") != "remaining-headless-batch-run-v1" or batch.get("protocol_version") != PROTOCOL
            or batch.get("expected") != planned_episodes()
            or batch["batch_identity_sha256"] != canonical_hash(batch["identity"])):
        raise ValueError("invalid headless batch identity or denominator")
    for item in batch["invocations"]:
        path = _contained(directory, item["plan"])
        if file_sha(path) != item["sha256"]:
            raise ValueError("batch plan bytes changed")
        plan = validate_plan(read_json(path))
        if plan["identity"] != batch["identity"]:
            raise ValueError("batch invocation changes model/code/config")
    return batch


def inspect_batch(directory, output=None):
    """Offline verification; never instantiate an environment or model."""
    directory = Path(directory).resolve()
    batch = read_batch(directory)
    summary = _summary(directory, batch)
    if output is not None:
        out = Path(output).resolve()
        if out == directory or directory in out.parents:
            raise ValueError("offline summary must use a new directory outside the original batch")
        out.mkdir(parents=True, exist_ok=False)
        save_summary(out, summary)
    return summary
