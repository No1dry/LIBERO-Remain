"""Explicit subset execution; retain the complete source bank and fixed denominator.

This entry is deliberately separate from legacy full-bank ``evaluate``. Technical
failures pause the batch; completed policy failures do not. No model is constructed
by ``dry_plan``. Oracle instructions exist only at the policy-call boundary.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import uuid

from . import cli
from .metrics import compute_metrics
from .schema import load_manifest, manifest_hash, validate_manifest
from .selection import build_selection, selected_episodes
from .runner import run_episode
from .video import EpisodeVideoRecorder, normalize_video_config


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source(manifest_path, candidate_replay=None):
    path = Path(manifest_path).resolve()
    raw = path.read_bytes()
    replay_raw = None
    evidence = None
    if candidate_replay is None:
        manifest = load_manifest(path, check_files=True)
    else:
        from .replay_candidates import _candidate_pack
        from .package_audit import validate_replay_evidence
        manifest, _, states, hashes = _candidate_pack(path)
        if any(e["construction"]["legal"] is not False for e in manifest["episodes"]):
            raise ValueError("candidate pilot must preserve unreviewed legal=False declarations")
        validate_manifest(manifest, base_dir=path.parent, check_files=True, allow_unreviewed=True)
        replay_raw = Path(candidate_replay).read_bytes()
        _, summary = validate_replay_evidence(path, manifest, candidate_replay, states, hashes)
        if summary["technical_acceptance"] is not True:
            raise ValueError("candidate pilot requires complete passing independent replay evidence")
        if summary["requested_steps"] < max(e["retention_steps"] for e in manifest["episodes"]) or summary["repeats"] < 2:
            raise ValueError("subset pilot requires replay for the full retention window and at least two repeats")
        if Path(candidate_replay).read_bytes() != replay_raw:
            raise ValueError("source replay changed during validation")
        evidence = {"path": str(Path(candidate_replay).resolve()), "sha256": _sha(replay_raw),
                    "summary": summary}
    if len({e["suite"] for e in manifest["episodes"]}) != 1:
        raise ValueError("one pilot must use exactly one suite")
    # Detect a changed source between reads rather than archive a different manifest.
    if json.loads(raw.decode("utf-8-sig")) != manifest or path.read_bytes() != raw:
        raise ValueError("source manifest changed during validation")
    return manifest, raw, replay_raw, evidence


def _video(config):
    value = normalize_video_config(config)
    if not value["enabled"]:
        raise ValueError("subset pilot requires --save-video; missing video is a technical pause")
    return value


def dry_plan(manifest_path, *, policy_config, policy_id, max_chunk_steps, masks,
             instruction_mode="original", candidate_replay=None, environment_config=None,
             video_config=None):
    if type(max_chunk_steps) is not int or max_chunk_steps < 1:
        raise ValueError("max_chunk_steps must be a positive integer")
    manifest, raw, replay_raw, replay = _source(manifest_path, candidate_replay)
    selection = build_selection(manifest, masks=masks, instruction_mode=instruction_mode)
    rows = {r["episode_id"]: r for r in selection["episodes"]}
    episodes = selected_episodes(manifest, {"execution_selection": selection})
    video = _video(video_config)
    return {
        "schema_version": "remaining-goals-subset-plan-v1", "dry_plan": True,
        "weights_loaded": False, "simulation_created": False,
        "manifest_source": str(Path(manifest_path).resolve()),
        "manifest_hash": manifest_hash(manifest), "source_manifest_sha256": _sha(raw),
        "candidate_replay_evidence": replay,
        "source_files": {"manifest.json": _sha(raw), **({"source/replay_report.json": _sha(replay_raw)} if replay_raw is not None else {})},
        "execution_selection": selection,
        "policy_id": policy_id, "policy_config": deepcopy(policy_config),
        "max_chunk_steps": max_chunk_steps, "environment_config": deepcopy(environment_config or {}),
        "video_config": video, "technical_failure_policy": "pause_remaining_selected",
        "evidence_protocol": "actual-reset-step0-and-policy-query-v1",
        "expected": len(episodes), "source_expected": len(manifest["episodes"]),
        "not_selected_ids": selection["not_selected_ids"],
        "planned_model_loads": 1, "planned_policy_resets": len(episodes),
        "episodes": [{**rows[e["episode_id"]], "task_id": e["task_id"], "suite": e["suite"],
                      "source_id": e["source_id"], "initial_state_index": e["initial_state_index"],
                      "mask": "".join(str(int(v)) for v in e["initial_mask"]),
                      "state_sha256": e["state_sha256"], "seed": e["seed"],
                      "horizon": e["horizon"], "retention_steps": e["retention_steps"],
                      "scheduled_steps": e["retention_steps"] if all(e["initial_mask"]) else e["horizon"] + e["retention_steps"]}
                     for e in episodes],
        "notice": "Plan only; configuration and identities are recorded, no model inference or physical validity conclusion.",
    }


def evidence_identity(metadata, episode):
    selection = metadata["execution_selection"]
    row = next(r for r in selection["episodes"] if r["episode_id"] == episode["episode_id"])
    return {**{k: metadata[k] for k in ("run_id", "manifest_hash", "run_config_sha256")},
            "episode_id": episode["episode_id"], "state_sha256": episode["state_sha256"],
            "selection_sha256": selection["selection_sha256"],
            "instruction_mode": selection["instruction_mode"],
            "max_chunk_steps": metadata["max_chunk_steps"],
            "effective_instruction_sha256": row["effective_instruction_sha256"]}


class _InstructionBoundary:
    def __init__(self, policy, effective_instruction, counts):
        self.policy, self.instruction, self.counts = policy, effective_instruction, counts

    def reset(self):
        self.counts["policy_reset_attempts"] += 1
        self.policy.reset()
        self.counts["policy_resets_completed"] += 1

    def predict(self, observation, original_instruction):
        # Only this fixed string is overridden; no mask/goal/episode enters policy.
        return self.policy.predict(observation, self.instruction)


def _unstarted(episode, phase, error):
    result = {k: deepcopy(episode[k]) for k in (
        "episode_id", "task_id", "suite", "task_name", "instruction", "seed",
        "initial_mask", "horizon", "retention_steps")}
    result.update(status="runtime_error", trace=[], n_steps=0, policy_queries=0, stop_step=None,
                  scheduled_steps=episode["retention_steps"] if all(episode["initial_mask"]) else episode["horizon"] + episode["retention_steps"],
                  error=f"{type(error).__name__}: {error}", error_phase=phase,
                  execution_evidence={"status": "unavailable", "reason": "episode_not_started"})
    return result


def validate_source_snapshot(directory, metadata):
    files = metadata.get("source_files")
    expected = {"manifest.json"}
    if metadata.get("candidate_replay_evidence") is not None:
        expected.add("source/replay_report.json")
    if not isinstance(files, dict) or set(files) != expected:
        raise ValueError("subset source snapshot identity is missing or unexpected")
    for name, digest in files.items():
        path = Path(directory) / name
        if not path.is_file() or _sha(path.read_bytes()) != digest:
            raise ValueError(f"source snapshot hash mismatch: {name}")
    if "source/replay_report.json" in files:
        if files["source/replay_report.json"] != metadata["candidate_replay_evidence"]["sha256"]:
            raise ValueError("source replay snapshot identity mismatch")


def evaluate_subset(manifest_path, output, *, policy_factory, policy_config, policy_id,
                    max_chunk_steps, masks, instruction_mode="original", candidate_replay=None,
                    environment_config=None, video_config=None):
    from .pilot_evidence import EpisodeEvidence, validate_execution_evidence
    plan = dry_plan(manifest_path, policy_config=policy_config, policy_id=policy_id,
                    max_chunk_steps=max_chunk_steps, masks=masks, instruction_mode=instruction_mode,
                    candidate_replay=candidate_replay, environment_config=environment_config,
                    video_config=video_config)
    manifest, raw, replay_raw, replay = _source(manifest_path, candidate_replay)
    if _sha(raw) != plan["source_manifest_sha256"] or replay != plan["candidate_replay_evidence"]:
        raise ValueError("source/replay changed after planning")
    selection = plan["execution_selection"]
    episodes = selected_episodes(manifest, {"execution_selection": selection})
    instructions = {r["episode_id"]: r["effective_instruction"] for r in selection["episodes"]}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "episodes").mkdir()
    (output / "manifest.json").write_bytes(raw)
    if replay_raw is not None:
        (output / "source").mkdir()
        (output / "source/replay_report.json").write_bytes(replay_raw)
    cli._write_json(output / "plan.json", plan)
    env_config = dict(environment_config or {})
    env_config.update(manifest_dir=str(Path(manifest_path).resolve().parent), environment=manifest["environment"])
    metadata = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": uuid.uuid4().hex,
                "manifest_hash": plan["manifest_hash"], "manifest_source": plan["manifest_source"],
                "source_files": plan["source_files"], "execution_selection": selection,
                "policy_id": policy_id, "policy_factory": policy_factory, "policy_config": deepcopy(policy_config),
                "environment_config": env_config, "max_chunk_steps": max_chunk_steps,
                "harness_source_sha256": cli._source_hash(), "python": platform.python_version(),
                "status": "running", "evaluation_kind": "candidate_pilot" if candidate_replay else "reviewed_manifest",
                "candidate_replay_evidence": replay, "video_config": plan["video_config"],
                "technical_failure_policy": plan["technical_failure_policy"], "evidence_protocol": plan["evidence_protocol"],
                "runtime_counts": {"model_load_attempts": 0, "model_loads_completed": 0,
                                   "policy_reset_attempts": 0, "policy_resets_completed": 0},
                "attempted_ids": [], "stop_reason": None,
                "notice": "TOY FIXTURE: not VLA evidence" if manifest["environment"]["name"] == "toy" else "Exploratory subset pilot; independent review required"}
    metadata["run_config_sha256"] = cli._config_hash(metadata)
    cli._write_json(output / "run.json", metadata)
    policy = env = None
    results = []
    phase = "model_load"

    def save_result(result, episode, index):
        result.update({k: metadata[k] for k in ("manifest_hash", "policy_id", "run_id", "run_config_sha256")})
        result.update(state_sha256=episode["state_sha256"], selection_sha256=selection["selection_sha256"],
                      instruction_mode=instruction_mode, effective_instruction=instructions[episode["episode_id"]])
        if result["status"] == "completed":
            result["metrics"] = compute_metrics(episode, result["trace"])
        cli._write_json(output / "episodes" / f"{index:06d}.json", result)
        results.append(result)
        metadata["attempted_ids"].append(episode["episode_id"])

    def pause(episode, phase, message):
        metadata["status"] = "technical_paused"
        metadata["stop_reason"] = {"episode_id": episode["episode_id"], "phase": phase, "error": message}

    try:
        metadata["runtime_counts"]["model_load_attempts"] += 1
        policy = cli._factory(policy_factory)(policy_config)
        metadata["runtime_counts"]["model_loads_completed"] += 1
        metadata["model_runtime"] = getattr(policy, "provenance", None)
        metadata["run_config_sha256"] = cli._config_hash(metadata)
        cli._write_json(output / "run.json", metadata)
        phase = "env_init"
        if manifest["environment"]["name"] == "libero":
            from .libero_env import LiberoGoalEnv
            env = LiberoGoalEnv(env_config)
        elif manifest["environment"]["name"] == "toy":
            from .toy import ToyGoalEnv
            env = ToyGoalEnv(env_config)
        else:
            raise ValueError("unsupported environment")
        for index, episode in enumerate(episodes):
            phase = "video_setup"
            try:
                recorder = EpisodeVideoRecorder(output / "videos" / f"{index:06d}.mp4", plan["video_config"],
                                                environment_name=manifest["environment"]["name"], episode=episode)
            except Exception as error:
                result = _unstarted(episode, phase, error)
                result["video"] = {"status": "video_error", "path": None, "frames": 0, "error": result["error"]}
                save_result(result, episode, index)
                pause(episode, phase, result["error"])
                break
            phase = "episode"
            identity = evidence_identity(metadata, episode)
            try:
                evidence = EpisodeEvidence(output / "evidence" / f"{index:06d}", identity)
            except Exception as error:
                result = _unstarted(episode, "evidence_setup", error)
                try:
                    closed_video = recorder.close()
                    if not isinstance(closed_video, dict):
                        raise TypeError("video recorder close() must return a dictionary")
                    json.dumps(closed_video, allow_nan=False)
                    if closed_video.get("path"):
                        closed_video["path"] = (Path("videos") / closed_video["path"]).as_posix()
                    result["video"] = closed_video
                except Exception as close_error:
                    result["video"] = {"status": "video_error", "path": None,
                                       "error": f"{type(close_error).__name__}: {close_error}"}
                save_result(result, episode, index)
                pause(episode, "evidence_setup", result["error"])
                break
            result = run_episode(env, _InstructionBoundary(policy, instructions[episode["episode_id"]], metadata["runtime_counts"]),
                                 episode, max_chunk_steps=max_chunk_steps, recorder=recorder,
                                 evidence=evidence)
            if result.get("video", {}).get("path"):
                result["video"]["path"] = (Path("videos") / result["video"]["path"]).as_posix()
            technical_error = None
            if result["status"] != "completed":
                technical_error = (result.get("error_phase", result["status"]), result.get("error"))
            try:
                validate_execution_evidence(output, result, episode, identity)
            except Exception as error:
                technical_error = ("evidence_validation", f"{type(error).__name__}: {error}")
            video = result.get("video", {})
            video_path = output / (video.get("path") or "__missing_video__")
            if video.get("status") != "saved" or not video_path.is_file() or video_path.stat().st_size == 0:
                technical_error = technical_error or ("video", video.get("error") or "required video is missing or unsaved")
                if video.get("status") == "saved":
                    video.update(status="video_error", error="claimed video file is missing or empty")
            save_result(result, episode, index)
            if technical_error:
                pause(episode, *technical_error)
                break
            cli._write_json(output / "run.json", metadata)
        else:
            metadata["status"] = "finished"
    except Exception as error:
        # Initialization failure is one failed selected attempt; the remainder stay missing.
        episode = episodes[len(results)] if len(results) < len(episodes) else episodes[-1]
        if phase in ("model_load", "env_init"):
            save_result(_unstarted(episode, phase, error), episode, len(results))
        pause(episode, phase, f"{type(error).__name__}: {error}")
    except BaseException as error:
        pause(episodes[min(len(results), len(episodes)-1)], phase, type(error).__name__)
        raise
    finally:
        for name, resource in (("environment", env), ("policy", policy)):
            if resource is not None and callable(getattr(resource, "close", None)):
                try:
                    resource.close()
                except Exception as error:
                    metadata.setdefault("cleanup_errors", []).append(f"{name}: {type(error).__name__}: {error}")
                    if metadata["stop_reason"] is None:
                        pause(episodes[-1], "cleanup", metadata["cleanup_errors"][-1])
        cli._write_json(output / "run.json", metadata)
        cli._save_report(output, manifest, results)
    return json.loads((output / "summary.json").read_text(encoding="utf-8"))
