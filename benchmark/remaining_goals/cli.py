"""CLI for frozen-state validation, evaluation, and offline rescoring."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .metrics import compute_metrics, summarize_results
from .reporting import build_display, render_report
from .runner import run_episode
from .schema import load_manifest, manifest_hash, validate_manifest
from .video import EpisodeVideoRecorder, normalize_video_config


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _factory(name: str):
    module, separator, symbol = name.partition(":")
    if not separator:
        raise ValueError("factory must use module:callable syntax")
    result = getattr(importlib.import_module(module), symbol)
    if not callable(result):
        raise ValueError("factory must be callable")
    return result


def _config(path: Path | None) -> dict:
    value = {} if path is None else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object")
    return value


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.rglob("*.py")):
        digest.update(path.relative_to(Path(__file__).parent).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _config_hash(metadata: dict) -> str:
    fields = ("manifest_hash", "policy_id", "policy_factory", "policy_config",
              "environment_config", "max_chunk_steps", "harness_source_sha256")
    payload = {key: metadata[key] for key in fields}
    for key in ("evaluation_kind", "candidate_replay_evidence", "model_runtime", "video_config"):
        if key in metadata:
            payload[key] = metadata[key]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _summarize_run(manifest: dict, results: list[dict], metadata: dict | None = None) -> dict:
    """Return the original report schema without writing experiment files."""
    summary = summarize_results(manifest["episodes"], results)
    summary["manifest_hash"] = manifest_hash(manifest)
    summary["environment"] = manifest["environment"]
    summary["is_toy_fixture"] = manifest["environment"]["name"] == "toy"
    summary["physical_validity"] = "not assessed by this scorer"
    if metadata is not None:
        summary["evaluation_kind"] = metadata.get("evaluation_kind", "reviewed_manifest")
        summary["run_status"] = metadata.get("status")
        # A legal declaration and completed rollout do not grant publication
        # approval, establish calibration, or validate checkpoint provenance.
        summary["release_authorized"] = False
        if metadata.get("video_config", {}).get("enabled"):
            videos = [result["video"] for result in results if "video" in result]
            summary["video_summary"] = {
                "enabled": True, "expected": len(manifest["episodes"]), "reported": len(videos),
                "saved": sum(video.get("status") == "saved" for video in videos),
                "video_error": sum(video.get("status") == "video_error" for video in videos),
                "empty": sum(video.get("status") == "empty" for video in videos),
                "missing": len(manifest["episodes"]) - len(videos),
                "affects_metrics": False,
            }
    return summary


def _save_report(output: Path, manifest: dict, results: list[dict]) -> dict:
    run_metadata = output / "run.json"
    metadata = json.loads(run_metadata.read_text(encoding="utf-8")) if run_metadata.is_file() else None
    summary = _summarize_run(manifest, results, metadata)
    _write_json(output / "summary.json", summary)
    fields = ["episode_id", "task_id", "mask", "status", "joint_success",
              "remaining_success", "preservation_success", "stable_final_success",
              "task_success_by_horizon", "goal_regression", "regression_steps",
              "first_all_success_step", "explicit_stop_step", "n_steps", "error"]
    expected = {e["episode_id"]: e for e in manifest["episodes"]}
    with (output / "episodes.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        found = {r["episode_id"]: r for r in results}
        for episode_id, episode in expected.items():
            result = found.get(episode_id, {"status": "missing", "error": "expected episode has no result"})
            metrics = compute_metrics(episode, result["trace"]) if result["status"] == "completed" else {}
            row = {**metrics, "episode_id": episode["episode_id"], "task_id": episode["task_id"],
                   "mask": "".join(str(int(v)) for v in episode["initial_mask"]),
                   "status": result["status"], "error": result.get("error")}
            if result["status"] != "completed":
                row["n_steps"] = result.get("n_steps")
            writer.writerow({key: row.get(key) for key in fields})
    display = build_display(manifest, results, summary)
    (output / "report.md").write_text(render_report(display), encoding="utf-8")
    return summary


def evaluate(manifest_path: Path, output: Path, *, policy_factory: str,
             policy_config: dict, policy_id: str, max_chunk_steps: int,
             environment_config: dict | None = None, candidate_replay: Path | None = None,
             video_config: dict | None = None) -> dict:
    """Evaluate in a fresh directory; explicit video settings override defaults.

    Video settings are independent of policy/environment configs. Recording is
    disabled by default; recording failures do not change episode scores.
    """
    if type(max_chunk_steps) is not int or max_chunk_steps < 1:
        raise ValueError("max_chunk_steps must be positive")
    video_config = normalize_video_config(video_config)
    manifest_path = Path(manifest_path).resolve()
    replay_evidence = None
    if candidate_replay is None:
        manifest = load_manifest(manifest_path, check_files=True)
    else:
        from .replay_candidates import _candidate_pack
        from .package_audit import validate_replay_evidence
        manifest, _, states, hashes = _candidate_pack(manifest_path)
        if any(e["construction"]["legal"] is not False for e in manifest["episodes"]):
            raise ValueError("candidate pilot must preserve unreviewed legal=False declarations")
        validate_manifest(manifest, base_dir=manifest_path.parent, check_files=True, allow_unreviewed=True)
        _, evidence = validate_replay_evidence(manifest_path, manifest, candidate_replay, states, hashes)
        if evidence["technical_acceptance"] is not True:
            raise ValueError("candidate pilot requires complete passing independent replay evidence")
        replay_evidence = {"path": str(Path(candidate_replay).resolve()),
                           "sha256": hashlib.sha256(Path(candidate_replay).read_bytes()).hexdigest(),
                           "summary": evidence}
    if len({e["suite"] for e in manifest["episodes"]}) != 1:
        raise ValueError("one run must use one suite; lock suite-specific policy normalization in policy_config")
    environment_config = dict(environment_config or {})
    environment_config.update(manifest_dir=str(manifest_path.parent), environment=manifest["environment"])
    name = manifest["environment"]["name"]
    if name == "libero":
        from .libero_env import LiberoGoalEnv
        env_class = LiberoGoalEnv
    elif name == "toy":
        from .toy import ToyGoalEnv
        env_class = ToyGoalEnv
    else:
        raise ValueError(f"unsupported environment: {name}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "episodes").mkdir()
    _write_json(output / "manifest.json", manifest)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": uuid.uuid4().hex,
        "manifest_hash": manifest_hash(manifest), "manifest_source": str(manifest_path),
        "policy_id": policy_id, "policy_factory": policy_factory,
        "policy_config": policy_config, "environment_config": environment_config,
        "max_chunk_steps": max_chunk_steps, "harness_source_sha256": _source_hash(),
        "python": platform.python_version(), "status": "running",
        "evaluation_kind": "candidate_pilot" if candidate_replay else "reviewed_manifest",
        "candidate_replay_evidence": replay_evidence,
        "video_config": video_config,
        "notice": "TOY FIXTURE: not VLA/LIBERO evidence" if name == "toy" else "Real environment run; inspect coverage and errors",
    }
    metadata["run_config_sha256"] = _config_hash(metadata)
    _write_json(output / "run.json", metadata)
    results = []
    env = policy = None
    try:
        policy = _factory(policy_factory)(policy_config)
        metadata["model_runtime"] = getattr(policy, "provenance", None)
        metadata["run_config_sha256"] = _config_hash(metadata)
        _write_json(output / "run.json", metadata)
        env = env_class(environment_config)
        for index, episode in enumerate(manifest["episodes"]):
            recorder = None
            recorder_error = None
            if video_config["enabled"]:
                try:
                    recorder = EpisodeVideoRecorder(output / "videos" / f"{index:06d}.mp4", video_config,
                                                    environment_name=name, episode=episode)
                except Exception as error:
                    # Unexpected recorder setup failures remain observable but
                    # cannot prevent the authorized policy rollout.
                    message = f"{type(error).__name__}: {error}"
                    recorder_error = {"status": "video_error", "path": None, "frames": 0,
                                      "error": message, "errors": [message], **video_config}
            result = run_episode(env, policy, episode, max_chunk_steps=max_chunk_steps, recorder=recorder)
            if recorder_error is not None:
                result["video"] = recorder_error
            if result.get("video", {}).get("path"):
                result["video"]["path"] = (Path("videos") / result["video"]["path"]).as_posix()
            result["manifest_hash"] = metadata["manifest_hash"]
            result["policy_id"] = policy_id
            result["run_id"] = metadata["run_id"]
            result["run_config_sha256"] = metadata["run_config_sha256"]
            result["state_sha256"] = episode["state_sha256"]
            if result["status"] == "completed":
                result["metrics"] = compute_metrics(episode, result["trace"])
            # Numeric filenames avoid leaking condition names to runtime adapters.
            _write_json(output / "episodes" / f"{index:06d}.json", result)
            results.append(result)
            print(f"[{index + 1}/{len(manifest['episodes'])}] {episode['episode_id']}: {result['status']}", flush=True)
        metadata["status"] = "finished" if all(r["status"] == "completed" for r in results) else "finished_with_errors"
    except BaseException as error:
        metadata["status"] = "aborted"
        metadata["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            if env is not None:
                env.close()
        except Exception as cleanup_error:
            metadata["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
            metadata["status"] = "aborted"
            raise
        finally:
            if policy is not None and callable(getattr(policy, "close", None)):
                try:
                    policy.close()
                except Exception as error:
                    metadata["policy_cleanup_error"] = f"{type(error).__name__}: {error}"
                    metadata["status"] = "aborted"
            _write_json(output / "run.json", metadata)
            _save_report(output, manifest, results)
    return json.loads((output / "summary.json").read_text(encoding="utf-8"))


def read_run(directory: Path) -> tuple[dict, dict, list[dict]]:
    """Read and validate saved identities without changing any experiment file."""
    directory = Path(directory)
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if metadata.get("evaluation_kind") == "candidate_pilot":
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        validate_manifest(manifest, check_files=False, allow_unreviewed=True)
        if any(e["construction"]["legal"] is not False for e in manifest["episodes"]):
            raise ValueError("candidate pilot changed its unreviewed declarations")
        evidence = metadata.get("candidate_replay_evidence")
        if not evidence or evidence.get("summary", {}).get("technical_acceptance") is not True:
            raise ValueError("candidate pilot is missing replay provenance")
    else:
        manifest = load_manifest(directory / "manifest.json", check_files=False)
    if metadata["manifest_hash"] != manifest_hash(manifest):
        raise ValueError("run metadata and manifest do not match")
    if metadata.get("run_config_sha256") != _config_hash(metadata):
        raise ValueError("run configuration hash mismatch")
    results = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((directory / "episodes").glob("*.json"))]
    expected = {episode["episode_id"]: episode for episode in manifest["episodes"]}
    for result in results:
        for field in ("manifest_hash", "policy_id", "run_id", "run_config_sha256"):
            if result.get(field) != metadata[field]:
                raise ValueError("mixed manifests/policies/run configurations in run directory")
        episode = expected.get(result["episode_id"])
        if episode is None:
            raise ValueError("unknown episode in run directory")
        for field in ("task_id", "suite", "task_name", "instruction", "seed", "state_sha256"):
            if result.get(field) != episode[field]:
                raise ValueError(f"episode metadata mismatch: {field}")
    if len({episode["suite"] for episode in manifest["episodes"]}) != 1:
        raise ValueError("one run must use exactly one suite; do not pool suites")
    summarize_results(manifest["episodes"], results)
    return metadata, manifest, results


def rescore(directory: Path) -> dict:
    """Legacy API: recompute summary/CSV in place; UIR uses a separate read-only path."""
    _, manifest, results = read_run(directory)
    return _save_report(Path(directory), manifest, results)


def _new_external_output(run_dir: Path, output: Path) -> Path:
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(Path(run_dir).resolve()):
        raise ValueError("annotation/derived output must be outside the source run directory")
    if output.exists():
        raise FileExistsError(output)
    return output


def annotation_template(run_dir: Path, output: Path, *, reviewer: str = "") -> dict:
    from .uir import make_annotation_template
    metadata, manifest, results = read_run(run_dir)
    template = make_annotation_template(metadata, manifest, results, reviewer=reviewer)
    output = _new_external_output(run_dir, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(template, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return template


def _video_evidence_hashes(run_dir: Path, normalized_annotations: list[dict]) -> dict:
    """Bind existing, contained videos; never load code or use external URLs."""
    directory = Path(run_dir).resolve()
    hashes = {}
    for annotation in normalized_annotations:
        for evidence in annotation["evidence"]:
            name = evidence["video_path"]
            path = (directory / name).resolve()
            if not path.is_relative_to(directory) or not path.is_file():
                raise ValueError(f"video evidence must be an existing file inside its run: {name}")
            if name not in hashes:
                digest = hashlib.sha256()
                with path.open("rb") as video:
                    for block in iter(lambda: video.read(1024 * 1024), b""):
                        digest.update(block)
                hashes[name] = digest.hexdigest()
    return hashes


def _read_annotations(raw: bytes) -> dict:
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate annotation JSON key: {key}")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError(f"annotation JSON requires finite values: {value}")

    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def derived_report(run_dir: Path, output: Path, *, annotations_path: Path | None = None) -> dict:
    """Create a new read-only derivation, preserving even the old summary bytes."""
    from .uir import summarize_annotations
    directory = Path(run_dir).resolve()
    metadata, manifest, results = read_run(directory)
    summary = _summarize_run(manifest, results, metadata)
    uir = None
    if annotations_path is not None:
        raw = Path(annotations_path).read_bytes()
        annotations = _read_annotations(raw)
        uir = summarize_annotations(metadata, manifest, results, annotations)
        uir["annotation_file_sha256"] = hashlib.sha256(raw).hexdigest()
        uir["video_evidence_sha256"] = _video_evidence_hashes(directory, uir["by_episode"])
    display = build_display(manifest, results, summary, uir=uir)
    source_paths = [directory / "run.json", directory / "manifest.json", *sorted((directory / "episodes").glob("*.json"))]
    provenance = {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in source_paths}
    report = {"schema_version": "remaining-goals-derived-report-v1",
              "run_id": metadata["run_id"], "manifest_hash": metadata["manifest_hash"],
              "source_file_sha256": provenance, "harness_source_sha256": _source_hash(),
              "legacy_metrics_unchanged": True, "summary": summary, "uir": uir, "display": display}
    output = _new_external_output(directory, output)
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "report.json", report)
    _write_json(output / "summary.json", summary)
    if uir is not None:
        _write_json(output / "uir.json", uir)
        (output / "annotations.json").write_bytes(raw)
    (output / "report.md").write_text(render_report(display), encoding="utf-8")
    return report


def _add_reporting_arguments(commands):
    template = commands.add_parser("uir-template", help="write a new external manual-UIR annotation template")
    template.add_argument("--run-dir", required=True, type=Path)
    template.add_argument("--out", required=True, type=Path)
    template.add_argument("--reviewer", default="")
    report = commands.add_parser("report", help="read-only derived report; optional manual UIR; never rewrites the source run")
    report.add_argument("--run-dir", required=True, type=Path)
    report.add_argument("--out", required=True, type=Path)
    report.add_argument("--annotations", type=Path)


def _reporting_command(args):
    if args.command == "uir-template":
        annotation_template(args.run_dir, args.out, reviewer=args.reviewer)
        print(f"Unreviewed annotation template: {args.out}")
    else:
        report = derived_report(args.run_dir, args.out, annotations_path=args.annotations)
        print(render_report(report["display"]))
        print(f"New derived report: {args.out / 'report.json'}")
    return 0


def _add_video_arguments(parser):
    """Shared CLI contract; flags override defaults, never model/job settings."""
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument("--save-video", dest="save_video", action="store_true",
                        help="save episode MP4s; recording errors do not change scores")
    switch.add_argument("--no-save-video", dest="save_video", action="store_false",
                        help="disable video recording (default)")
    parser.set_defaults(save_video=False)
    parser.add_argument("--video-fps", type=float, default=20, help="video playback FPS (default: 20)")
    parser.add_argument("--video-camera", choices=("agentview", "wrist", "both"), default="agentview")
    parser.add_argument("--video-stride", type=int, default=1, help="record every N control steps (default: 1)")


def _video_config_from_args(args):
    return normalize_video_config({"enabled": args.save_video, "fps": args.video_fps,
                                   "camera": args.video_camera, "stride": args.video_stride})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="CPU fixture only, not a research experiment")
    demo.add_argument("--out", required=True, type=Path)
    demo.add_argument("--scenes", type=int, default=2)
    demo.add_argument("--mode", choices=["reactive", "idle", "destructive"], default="reactive")
    _add_video_arguments(demo)
    validate = commands.add_parser("validate", help="validate manifest pairing and state file hashes")
    validate.add_argument("--manifest", required=True, type=Path)
    run = commands.add_parser("run", help="evaluate all frozen episodes")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--policy-factory", required=True)
    run.add_argument("--policy-id", required=True, help="model/checkpoint identifier, not just architecture")
    run.add_argument("--policy-config", type=Path)
    run.add_argument("--environment-config", type=Path)
    run.add_argument("--max-chunk-steps", required=True, type=int, help="native execution horizon for this model")
    run.add_argument("--candidate-replay", type=Path, help="explicit unreviewed pilot using a matching passing replay report")
    _add_video_arguments(run)
    report = commands.add_parser("summarize", help="recompute metrics from saved step traces")
    report.add_argument("--run-dir", required=True, type=Path)
    envinfo = commands.add_parser("libero-env-info", help="print runtime identity in the LIBERO environment")
    envinfo.add_argument("--control-freq", default=20, type=int)
    _add_reporting_arguments(commands)
    args = parser.parse_args(argv)
    if args.command in ("uir-template", "report"):
        return _reporting_command(args)
    if args.command == "demo":
        from .toy import build_toy_manifest
        video_config = _video_config_from_args(args)
        args.out.mkdir(parents=True, exist_ok=False)
        path = build_toy_manifest(args.out / "fixture", scenes=args.scenes)
        evaluate(path, args.out / "run", policy_factory="benchmark.remaining_goals.toy:make_policy",
                 policy_config={"mode": args.mode}, policy_id=f"toy-{args.mode}", max_chunk_steps=1,
                 video_config=video_config)
        print((args.out / "run" / "report.md").read_text(encoding="utf-8"))
        print(f"Toy smoke complete: {args.out / 'run' / 'summary.json'}")
    elif args.command == "validate":
        manifest = load_manifest(args.manifest, check_files=True)
        print(json.dumps({"valid": True, "episodes": len(manifest["episodes"]),
                          "content_hash": manifest_hash(manifest)}, indent=2))
    elif args.command == "run":
        summary = evaluate(args.manifest, args.out, policy_factory=args.policy_factory,
                 policy_config=_config(args.policy_config), policy_id=args.policy_id,
                 environment_config=_config(args.environment_config), max_chunk_steps=args.max_chunk_steps,
                 candidate_replay=args.candidate_replay, video_config=_video_config_from_args(args))
        print((args.out / "report.md").read_text(encoding="utf-8"))
        return 0 if summary.get("run_status") == "finished" else 1
    elif args.command == "summarize":
        rescore(args.run_dir)
        print((args.run_dir / "report.md").read_text(encoding="utf-8"))
        print(f"Rescored: {args.run_dir / 'summary.json'}")
    else:
        from .libero_env import environment_identity
        print(json.dumps(environment_identity(args.control_freq), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
