"""Explicit, independently invoked FINISH stages; no import-time experiments."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import uuid

from .data import read_json, canonical_hash, _contained, validate_split
from .schema import PROTOCOL

RUN_SCHEMA = "remaining-finish-run-v1"
BANK_SCHEMA = "remaining-finish-normal-bank-v1"
PURPOSES = {"validation_shadow": ("shadow", "validation"),
            "normal_active": ("active", "normal_test"),
            "remain_active": ("active", "remain_test"),
            "remain_shadow": ("shadow", "remain_test")}


def write_json(path, value, *, update=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if update:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(raw, encoding="utf-8")
        os.replace(temporary, path)
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(raw)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def head_manifest(path):
    """File-only preflight; actual tensor/architecture loading remains in worker."""
    path = Path(path)
    path = path / "head.json" if path.is_dir() else path
    head = read_json(path)
    if (head.get("schema_version") != "remaining-finish-head-v1" or
            head.get("artifact_sha256") != canonical_hash({k:v for k,v in head.items() if k != "artifact_sha256"})):
        raise ValueError("invalid head schema/hash")
    if head["weights"]["path"] != "head.npz" or file_sha(path.parent / "head.npz") != head["weights"]["sha256"]:
        raise ValueError("head weight bytes differ")
    return head


def prepare_normal_bank(indices, output, *, environment_config=None, prepare=None):
    """USER real stage; save precisely the requested ordinary 00 sources."""
    if (not indices or len(set(indices)) != len(indices) or
            any(type(i) is not int or i < 0 for i in indices)):
        raise ValueError("normal source indices must be distinct nonnegative integers")
    if prepare is None:
        from ..regression_states import prepare_normal00
        prepare = prepare_normal00
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bank = {"schema_version": BANK_SCHEMA, "status": "preparing", "expected_indices": indices,
            "episodes": [], "preparations": [], "environment": None, "error": None}
    try:
        for index in indices:
            prefix = f"sources/{index:03d}"
            report = prepare("basket", index, out / prefix, environment_config=environment_config)
            bank["preparations"].append({"source_index": index, "path": prefix+"/preparation.json",
                                          "sha256": file_sha(out/prefix/"preparation.json")})
            if report["status"] != "prepared":
                raise RuntimeError(f"source {index} preparation failed: {report.get('error')}")
            identity = report["environment_config"]["environment"]
            if bank["environment"] not in (None, identity):
                raise ValueError("normal source environment changed")
            bank["environment"] = identity
            episode = deepcopy(report["episode"])
            episode["state_path"] = prefix + "/" + episode["state_path"]
            episode["initial_observation"]["path"] = prefix + "/" + episode["initial_observation"]["path"]
            episode["construction"]["technical_audit"] = prefix + "/" + episode["construction"]["technical_audit"]
            bank["episodes"].append(episode)
            write_json(out/"progress.json", bank, update=True)
        bank["status"] = "prepared"
    except BaseException as exc:
        bank.update(status="preparation_error", error=f"{type(exc).__name__}: {exc}")
    bank["content_hash"] = canonical_hash(bank)
    write_json(out/"normal_bank.json", bank)
    return bank


def load_source(source):
    path = Path(source["manifest"]).resolve()
    if source["kind"] == "normal_bank":
        manifest = read_json(path)
        if (manifest.get("schema_version") != BANK_SCHEMA or manifest.get("status") != "prepared" or
                manifest.get("content_hash") != canonical_hash({k:v for k,v in manifest.items() if k != "content_hash"})):
            raise ValueError("normal bank is incomplete or changed")
        indices = manifest.get("expected_indices")
        if (not isinstance(indices, list) or not indices or any(type(i) is not int or i < 0 for i in indices)
                or len(set(indices)) != len(indices) or len(manifest["episodes"]) != len(indices)
                or len(manifest["preparations"]) != len(indices)):
            raise ValueError("normal bank must preserve each exact requested source once")
        by_index = {e["initial_state_index"]: e for e in manifest["episodes"]}
        if set(by_index) != set(indices):
            raise ValueError("normal bank source indices differ")
        seen = set()
        for item in manifest["preparations"]:
            index = item["source_index"]
            if type(index) is not int or index not in by_index or index in seen:
                raise ValueError("duplicate or substituted normal preparation source")
            seen.add(index)
            report_path = _contained(path.parent, item["path"])
            if file_sha(report_path) != item["sha256"]:
                raise ValueError("normal preparation evidence changed")
            report = read_json(report_path)
            _validate_normal_preparation(path.parent, report_path, report, by_index[index], index, manifest["environment"])
    elif source["kind"] == "remain":
        from ..pilot import _source
        manifest, _, _, _ = _source(path, source.get("candidate_replay"))
    else:
        raise ValueError("source kind must be normal_bank or remain")
    return manifest, path


def _validate_normal_preparation(root, report_path, report, episode, index, environment):
    """Verify saved preparation evidence, without importing a simulator."""
    import numpy as np
    from ..observation_artifact import load_observation_artifact
    if (report.get("schema_version") != "remaining-goals-capability-statebank-v1"
            or report.get("purpose") != "normal00-capability-regression"
            or report.get("complete_paired_benchmark") is not False
            or report.get("status") != "prepared" or report.get("error") is not None):
        raise ValueError("normal preparation did not pass its dedicated source contract")
    preparation, provenance = report["preparation"], report["provenance"]
    fixed = {"attempted": 1, "requested_index": index, "settle_steps_requested": 80,
             "settle_steps_completed": 80, "audit_steps_requested": 150, "audit_steps_completed": 150,
             "policy_steps": 0, "horizon": 520, "retention_steps": 150}
    if (any(type(preparation.get(k)) is not int or preparation[k] != v for k, v in fixed.items())
            or preparation.get("replacement_indices") != []
            or preparation.get("settled_goal_values") != [False, False]
            or preparation.get("audit", {}).get("technical_acceptance") is not True):
        raise ValueError("normal preparation changed the exact settle/audit/index contract")
    env = report["environment_config"]
    if (env.get("environment") != environment or provenance.get("environment") != environment
            or env.get("control_freq") != 20 or env.get("image_size") != 256
            or provenance.get("task_key") != "basket" or provenance.get("initial_state_index") != index
            or provenance.get("environment_seed") != index):
        raise ValueError("normal preparation identity differs from the selected source")
    native = deepcopy(report["episode"])
    prefix = report_path.parent.relative_to(root).as_posix()
    for container, key in ((native, "state_path"), (native["initial_observation"], "path"),
                           (native["construction"], "technical_audit")):
        # Resolve the original path too; adding a prefix must never hide traversal.
        _contained(report_path.parent, container[key])
        container[key] = prefix + "/" + container[key]
    if native != episode:
        raise ValueError("normal bank episode differs from its exact preparation episode")
    if (episode["initial_mask"] != [False, False] or any(type(v) is not bool for v in episode["initial_mask"])
            or episode["initial_state_index"] != index or episode["seed"] != index
            or episode["task_id"] != "basket" or episode["horizon"] != 520 or episode["retention_steps"] != 150
            or episode["model_xml_sha256"] != provenance.get("model_xml_sha256")
            or episode["bddl_sha256"] != provenance.get("bddl_sha256")
            or episode["instruction"] != provenance.get("official_instruction")):
        raise ValueError("normal00 episode preparation binding differs")
    state_path = _contained(root, episode["state_path"])
    if file_sha(state_path) != episode["state_sha256"] or provenance.get("saved_state_sha256") != episode["state_sha256"]:
        raise ValueError("normal00 saved state bytes differ")
    with state_path.open("rb") as stream:
        state = np.load(stream, allow_pickle=False)
    if state.ndim != 1 or state.dtype != np.dtype("float64") or not state.size or not np.isfinite(state).all():
        raise ValueError("normal00 saved base must be a finite float64 vector")
    state_identity = {"dtype": state.dtype.str, "shape": list(state.shape),
                      "sha256": hashlib.sha256(np.ascontiguousarray(state).tobytes()).hexdigest()}
    if provenance.get("settled_base_state") != state_identity:
        raise ValueError("normal00 saved base identity differs")
    official = provenance.get("official_initial_state_file", {})
    if (not isinstance(official.get("sha256"), str) or len(official["sha256"]) != 64
            or type(official.get("count")) is not int or not 0 <= index < official["count"]
            or not provenance.get("selected_official_state") or not provenance.get("restored_official_state")):
        raise ValueError("normal00 lacks exact official initial-state provenance")
    audit_path = _contained(root, episode["construction"]["technical_audit"])
    if file_sha(audit_path) != provenance.get("technical_audit_sha256"):
        raise ValueError("normal00 audit bytes differ")
    audit = read_json(audit_path)
    trace = audit.get("trace", [])
    if (audit.get("technical_acceptance") is not True or audit.get("error") is not None
            or audit.get("requested_steps") != 150 or audit.get("completed_steps") != 150
            or len(trace) != 151 or any(type(row.get("step")) is not int or row["step"] != i for i, row in enumerate(trace))):
        raise ValueError("normal00 requires its complete 150-step passing audit")
    first = trace[0]
    initial = np.asarray(first.get("state"), dtype=np.float64)
    if (initial.shape != state.shape or not np.array_equal(initial.view(np.uint64), state.view(np.uint64))
            or first.get("goals") != [False, False]):
        raise ValueError("normal00 saved state is not the pre-audit step-zero base")
    load_observation_artifact(root, episode["initial_observation"],
                              expected_digest=first.get("observation_check", {}).get("returned_sha256"))


def dry_plan(config):
    """No simulator imports, checkpoint deserialization, prediction or training."""
    if config.get("schema_version") != "remaining-finish-job-v1":
        raise ValueError("unsupported finish job config")
    purpose = config["purpose"]
    if purpose not in PURPOSES:
        raise ValueError("invalid finish purpose")
    mode, split_name = PURPOSES[purpose]
    split = validate_split(config.get("split"), alternative_confirmation=config.get("alternative_confirmation"))
    source, source_path = load_source(config["source"])
    expected_kind = "remain" if split_name == "remain_test" else "normal_bank"
    if config["source"]["kind"] != expected_kind:
        raise ValueError("source kind differs from purpose")
    indices = split[split_name]
    masks = {(True, False), (False, True), (True, True)} if expected_kind == "remain" else {(False, False)}
    episodes = [deepcopy(e) for e in source["episodes"] if e["task_id"] == "basket"
                and e["initial_state_index"] in indices and tuple(e["initial_mask"]) in masks]
    expected = {(i, m) for i in indices for m in masks}
    found = [(e["initial_state_index"], tuple(e["initial_mask"])) for e in episodes]
    if len(found) != len(expected) or set(found) != expected:
        raise ValueError("source lacks the exact fixed source/mask set; no replacements")
    if len({e["episode_id"] for e in episodes}) != len(episodes):
        raise ValueError("duplicate episode identity")
    runtime = read_json(config["runtime_config"])
    if (runtime.get("model_id") != "openvla_oft" or runtime.get("suite") != "libero_10" or
            runtime.get("execution", {}).get("max_chunk_steps") != 8
            or runtime.get("execution", {}).get("random_seed") != 7):
        raise ValueError("stage04 requires existing LIBERO10 OFT chunk8 seed7 runtime")
    from ..video import normalize_video_config
    video = normalize_video_config(config.get("video", {"enabled": True, "camera": "both", "fps": 20, "stride": 1}))
    if not video["enabled"]:
        raise ValueError("FINISH runs require saved video")
    head = head_manifest(config["head_artifact"])
    if head["identities"]["split_identity"]["split"] != split:
        raise ValueError("head training groups differ from run groups")
    threshold, calibration = 0.5, None
    if mode == "active":
        calibration = read_json(config["calibration"])
        if (calibration.get("schema_version") != "remaining-finish-calibration-v1" or
                calibration.get("calibration_sha256") != canonical_hash({k:v for k,v in calibration.items() if k != "calibration_sha256"}) or
                calibration.get("calibrated") is not True or
                calibration.get("binding", {}).get("head_sha256") != head["artifact_sha256"] or
                calibration.get("validation_source_indices") != split["validation"]):
            raise ValueError("active requires this head's complete useful normal-validation calibration")
        threshold = calibration["selected_threshold"]
    runtime["policy_factory"] = "benchmark.remaining_goals.finish.oft:make_policy"
    runtime["finish"] = {"head_artifact": str(Path(config["head_artifact"]).resolve()), "threshold": threshold,
                         "threshold_identity": calibration["calibration_sha256"] if calibration else "validation-shadow-placeholder-0.5"}
    plan = {"schema_version": "remaining-finish-plan-v1", "protocol_version": PROTOCOL, "dry_plan": True,
            "simulation_created": False, "weights_loaded": False, "purpose": purpose, "mode": mode,
            "split": split, "config": deepcopy(config), "policy_config": runtime, "video": video,
            "head_sha256": head["artifact_sha256"], "head_split_identity": deepcopy(head["identities"]["split_identity"]),
            "threshold": threshold,
            "source_path": str(source_path), "manifest_hash": canonical_hash(source),
            "source_file_sha256": file_sha(source_path), "episodes": episodes,
            "environment_config": {"manifest_dir": str(source_path.parent), "environment": source["environment"],
                                   "image_size": 256, "control_freq": 20},
            "configuration": {"horizon": 520, "retention_steps": 150, "max_chunk_steps": 8},
            "expected": len(episodes), "maximum_physical_steps": len(episodes)*670,
            "maximum_queries_per_episode": 66,
            "technical_failure_policy": "pause_remaining; preserve fixed expected and missing",
            "notice": "File-only plan; no physical validity, real parity or stopping-capability claim."}
    plan["plan_sha256"] = canonical_hash(plan)
    return plan


def evidence_identity(metadata, episode):
    return {**{k: metadata[k] for k in ("run_id", "run_config_sha256", "manifest_hash", "mode", "head_sha256")},
            "protocol_version": PROTOCOL, "episode_id": episode["episode_id"],
            "state_sha256": episode["state_sha256"], **metadata["configuration"]}


def _normal_capability(summary, purpose):
    if purpose != "normal_active":
        return summary
    rows = summary["episodes"]
    expected = len(rows)
    def complete(row):
        return bool(row.get("goals_at_exit")) and all(row["goals_at_exit"]) and row.get("released_at_exit") is True
    def timely(row):
        delay = row.get("finish_delay_steps")
        return complete(row) and row.get("delay_status") == "observed" and delay is not None and 0 <= delay <= 24
    def count(predicate):
        numerator = sum(bool(predicate(row)) for row in rows)
        return {"numerator": numerator, "denominator": expected, "percent": 100*numerator/expected}
    summary["ordinary_stopping_capability"] = {
        "expected": expected, "successful": summary["counts"]["successful"],
        "percent": summary["counts"]["compliant_finish_percent"],
        "completion_at_exit": count(complete),
        "premature_finish": count(lambda row: "premature_finish" in row["failure_reasons"]),
        "correct_finish_within_24_steps": count(timely),
        "compliant_finish_within_24_steps": count(lambda row: timely(row) and row["compliant_finish"] is True),
        "delay_observed": summary["counts"]["delay_observed"],
        "delay_coverage": summary["counts"]["delay_coverage"],
        "delay_mean_steps": summary["counts"]["delay_mean_steps"],
        "delay_categories": deepcopy(summary["counts"]["delay_categories"]),
        "unknown": summary["counts"]["unknown"], "technical_error": summary["counts"]["technical_error"],
        "missing": summary["counts"]["missing"],
        "notice": "All proportions use the fixed normal-test N. Completion at exit requires every goal and known release; correct timing alone does not assert hold compliance. The 90% completion / 10% premature pilot guidance is not a software acceptance gate or automatic Remain block."}
    return summary


def _report(summary):
    from .metrics import render_report
    text = render_report(summary)
    capability = summary.get("ordinary_stopping_capability")
    if capability is None:
        return text
    text += "\nNormal00 active capability (fixed planned denominator):\n\n| Measure | n/N | Percent |\n|---|---|---|\n"
    for label, key in (("Goals complete and released at exit", "completion_at_exit"),
                       ("Known premature FINISH", "premature_finish"),
                       ("Correct FINISH within 24 steps", "correct_finish_within_24_steps"),
                       ("Compliant FINISH within 24 steps", "compliant_finish_within_24_steps")):
        row = capability[key]
        text += f"| {label} | {row['numerator']}/{row['denominator']} | {row['percent']:.2f}% |\n"
    text += f"\nDelay coverage: {capability['delay_observed']}/{capability['expected']}. " + capability["notice"] + "\n"
    return text


def run(config, output, *, policy_factory=None, env_factory=None, recorder_factory=None):
    """USER real stage. Injected factories are solely for CPU fake contract tests."""
    plan = dry_plan(config)
    if policy_factory is None:
        from ..isolated_policy import SubprocessPolicy
        policy_factory = SubprocessPolicy
    if env_factory is None:
        from .environment import make_env
        env_factory = make_env
    if recorder_factory is None:
        from ..video import EpisodeVideoRecorder
        recorder_factory = EpisodeVideoRecorder
    from .runner import run_finish_episode
    from .evidence import FinishEvidence, validate_finish_evidence
    from .metrics import summarize
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    metadata = {"schema_version": RUN_SCHEMA, "protocol_version": PROTOCOL,
                "run_id": uuid.uuid4().hex, "run_config_sha256": plan["plan_sha256"],
                **{k:deepcopy(plan[k]) for k in ("manifest_hash", "mode", "purpose", "head_sha256", "configuration", "episodes", "split")},
                "plan": plan, "status": "running", "results": [], "error": None,
                "attempts": [], "cleanup_errors": [], "interrupted": False,
                "missing": [e["episode_id"] for e in plan["episodes"]]}
    write_json(out/"run.json", metadata)
    policy = env = None
    results = []
    phase = "policy_setup"
    try:
        policy = policy_factory(plan["policy_config"])
        metadata["policy_provenance"] = deepcopy(getattr(policy, "provenance", {}))
        phase = "environment_setup"
        env = env_factory(plan["environment_config"])
        for number, episode in enumerate(plan["episodes"]):
            key = f"{number:04d}"
            attempt = {"episode_id": episode["episode_id"], "status": "starting", "phase": "video_setup"}
            metadata["attempts"].append(attempt)
            write_json(out/"run.json", metadata, update=True)
            recorder = None
            phase = "video_setup"
            try:
                recorder = recorder_factory(out/"videos"/(key+".mp4"), plan["video"], environment_name="libero", episode=episode)
                phase = attempt["phase"] = "evidence_setup"
                evidence = FinishEvidence(out/"evidence"/key, evidence_identity(metadata, episode))
            except BaseException:
                # The runner has not taken ownership yet. Never leak an encoder.
                if recorder is not None:
                    try:
                        closed = recorder.close()
                        if not isinstance(closed, dict):
                            raise ValueError("video close report must be an object")
                        json.dumps(closed, allow_nan=False)
                        if closed.get("status") == "saved":
                            closed = {**closed, "path": f"videos/{key}.mp4",
                                      "sha256": file_sha(out/"videos"/(key+".mp4"))}
                        attempt["video"] = deepcopy(closed)
                    except BaseException as error:
                        attempt["video"] = {"status": "video_error", "error": f"{type(error).__name__}: {error}"}
                raise
            phase = attempt["phase"] = "rollout"
            result = run_finish_episode(env, policy, episode, mode=plan["mode"], recorder=recorder, evidence=evidence, **plan["configuration"])
            # Persist before offline checks: a video/evidence verification failure
            # must not erase the actual executed actions or captured inputs.
            relative = f"raw/{key}.json"
            write_json(out/relative, result)
            reference = {"episode_id": episode["episode_id"], "path": relative,
                         "sha256": file_sha(out/relative), "validation": {"status": "pending"}}
            metadata["results"].append(reference)
            metadata["missing"].remove(episode["episode_id"])
            write_json(out/"run.json", metadata, update=True)
            phase = attempt["phase"] = "artifact_verification"
            # Video is outside ledger binding; add its immutable run-relative byte identity.
            try:
                if result.get("video", {}).get("status") == "saved":
                    result["video"].update(path=f"videos/{key}.mp4", sha256=file_sha(out/"videos"/(key+".mp4")))
                validation = validate_finish_evidence(out, result, episode, evidence_identity(metadata, episode))
                result["evidence_validation"] = validation
                write_json(out/relative, result, update=True)
                reference.update(sha256=file_sha(out/relative), validation={"status": "checked", **validation})
            except BaseException as error:
                reference["validation"] = {"status": "error", "error": f"{type(error).__name__}: {error}"}
                # Diagnostic summary only; the immutable raw stays unmodified and
                # read_run will refuse to score this unverified artifact.
                failed = deepcopy(result)
                failed.update(status="runtime_error", error=reference["validation"]["error"], error_phase=phase)
                results.append(failed)
                raise
            results.append(result)
            attempt.update(status=result["status"], phase=result.get("error_phase"))
            write_json(out/"run.json", metadata, update=True)
            if result["status"] != "completed":
                metadata["interrupted"] = result.get("interrupted") is True
                raise RuntimeError(f"technical pause at {episode['episode_id']}: {result.get('error')}")
        metadata["status"] = "completed"
    except BaseException as exc:
        metadata.update(status="technical_pause", error=f"{type(exc).__name__}: {exc}", error_phase=phase)
        metadata["interrupted"] = metadata["interrupted"] or isinstance(exc, (KeyboardInterrupt, SystemExit))
        if metadata["attempts"] and metadata["attempts"][-1]["status"] == "starting":
            metadata["attempts"][-1].update(status="technical_error", phase=phase, error=metadata["error"])
    finally:
        for resource in (env, policy):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as exc:
                    error = f"resource close: {type(exc).__name__}: {exc}"
                    metadata["cleanup_errors"].append(error)
                    metadata["status"] = "technical_pause"
                    if metadata["error"] is None:
                        metadata.update(error=error, error_phase="resource_close")
                    metadata["interrupted"] = metadata["interrupted"] or isinstance(exc, (KeyboardInterrupt, SystemExit))
        write_json(out/"run.json", metadata, update=True)
    summary = summarize(plan["episodes"], results, mode=plan["mode"])
    summary["workflow_status"] = metadata["status"]
    summary["unverified_raw_results"] = [r["episode_id"] for r in metadata["results"] if r["validation"]["status"] == "error"]
    summary["notice"] += " Unverified raw results, if present, are technical failures in this diagnostic summary; offline scoring rejects them."
    _normal_capability(summary, plan["purpose"])
    write_json(out/"summary.json", summary)
    (out/"report.md").write_text(_report(summary), encoding="utf-8")
    return metadata


def read_run(directory):
    """Read-only verification of each result, real input ledger and video bytes."""
    from .evidence import validate_finish_evidence
    from .schema import validate_finish_result
    directory = Path(directory)
    metadata = read_json(directory/"run.json")
    if metadata.get("schema_version") != RUN_SCHEMA or metadata.get("protocol_version") != PROTOCOL:
        raise ValueError("unsupported/mixed run schema; legacy STOP is not FINISH")
    plan = metadata["plan"]
    if plan["plan_sha256"] != canonical_hash({k:v for k,v in plan.items() if k != "plan_sha256"}) or metadata["run_config_sha256"] != plan["plan_sha256"]:
        raise ValueError("run plan hash mismatch")
    for key in ("episodes", "mode", "configuration", "head_sha256", "manifest_hash", "purpose", "split"):
        if metadata[key] != plan[key]:
            raise ValueError("run metadata differs from frozen plan")
    expected = {e["episode_id"]: e for e in metadata["episodes"]}
    if len(expected) != len(metadata["episodes"]) or metadata.get("status") not in {"completed", "technical_pause"}:
        raise ValueError("run contains duplicate episodes or is not finalized")
    results, seen = [], set()
    for reference in metadata["results"]:
        name = reference["episode_id"]
        if name not in expected or name in seen:
            raise ValueError("unexpected/duplicate result")
        seen.add(name)
        path = _contained(directory, reference["path"])
        if file_sha(path) != reference["sha256"]:
            raise ValueError("raw result bytes changed")
        result = read_json(path)
        if reference.get("validation", {}).get("status") in {"error", "pending"}:
            raise ValueError("unverified raw FINISH result retained for diagnosis; cannot rescore")
        validate_finish_result(result, expected[name])
        validate_finish_evidence(directory, result, expected[name], evidence_identity(metadata, expected[name]))
        video = result.get("video", {})
        if result["status"] == "completed" and video.get("status") != "saved":
            raise ValueError("completed episode lacks original video bytes")
        if video.get("status") == "saved" and file_sha(_contained(directory, video["path"])) != video.get("sha256"):
            raise ValueError("original video bytes changed")
        results.append(result)
    if (len(set(metadata["missing"])) != len(metadata["missing"])
            or set(metadata["missing"]) != set(expected)-seen
            or metadata["status"] == "completed" and (metadata["missing"] or any(r["status"] != "completed" for r in results))):
        raise ValueError("missing denominator differs")
    return metadata, results


def _derived_output(directory, output):
    source, out = Path(directory).resolve(), Path(output).resolve()
    if out == source or source in out.parents:
        raise ValueError("derived output must be outside the original run directory")
    return out


def rescore(directory, output, *, stable_steps=4):
    from .metrics import summarize
    metadata, results = read_run(directory)
    out = _derived_output(directory, output)
    out.mkdir(parents=True, exist_ok=False)
    summary = summarize(metadata["episodes"], results, mode=metadata["mode"], stable_steps=stable_steps)
    _normal_capability(summary, metadata["purpose"])
    summary["workflow_status"] = metadata["status"]
    summary["source_run_sha256"] = file_sha(Path(directory)/"run.json")
    write_json(out/"summary.json", summary)
    (out/"report.md").write_text(_report(summary), encoding="utf-8")
    return summary


def calibrate(directory, output):
    from .calibration import calibrate_threshold
    metadata, results = read_run(directory)
    if metadata["purpose"] != "validation_shadow":
        raise ValueError("calibration uses only the planned normal-validation shadow run")
    episodes = [{"episode_id":e["episode_id"], "source_index":e["initial_state_index"], "split":"validation"}
                for e in metadata["episodes"]]
    report = calibrate_threshold(episodes, results, expected_validation_sources=metadata["split"]["validation"],
                                 split_identity=metadata["plan"]["head_split_identity"])
    report["binding"] = {"head_sha256": metadata["head_sha256"], "run_id": metadata["run_id"],
                         "source_run_sha256": file_sha(Path(directory)/"run.json")}
    report.pop("calibration_sha256", None)
    report["calibration_sha256"] = canonical_hash(report)
    out = _derived_output(directory, output)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/"calibration.json", report)
    return report
