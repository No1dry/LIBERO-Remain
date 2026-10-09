"""One interface for six isolated model environments, pilots and frozen evaluations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import numpy as np

from .cli import (evaluate, rescore, _add_video_arguments, _video_config_from_args,
                  _add_reporting_arguments, _reporting_command)
from .isolated_policy import SubprocessPolicy
from .runner import _actions, _observation
from .video import normalize_video_config

MODELS = ("openvla", "openvla_oft", "pi0", "pi05", "groot_n1_7", "univla")


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def check_config(config, suite=None):
    """Static readiness only; never assert checkpoint performance or compatibility."""
    errors = []
    for key in ("model_id", "policy_id", "policy_factory", "suite"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            errors.append(f"{key}: required nonempty string")
    if config.get("model_id") not in MODELS:
        errors.append(f"model_id: expected one of {MODELS}")
    factory = config.get("policy_factory", "")
    if (not isinstance(factory, str) or factory.count(":") != 1
            or not all(part.isidentifier() for part in factory.split(":")[0].split("."))
            or not factory.split(":")[-1].isidentifier()):
        errors.append("policy_factory: expected module:callable")
    if suite is not None and config.get("suite") != suite:
        errors.append(f"suite: config={config.get('suite')!r}, manifest={suite!r}")
    def object_field(key):
        value = config.get(key)
        if not isinstance(value, dict):
            errors.append(f"{key}: JSON object required")
            return {}
        return value
    execution = object_field("execution")
    count = execution.get("max_chunk_steps")
    if type(count) is not int or count < 1:
        errors.append("execution.max_chunk_steps: positive integer required")
    seed = execution.get("random_seed", 0)
    if type(seed) is not int or not 0 <= seed < 2**32:
        errors.append("execution.random_seed: integer in [0, 2**32) required")
    runtime = object_field("runtime")
    python = runtime.get("python_executable")
    if not isinstance(python, str) or not Path(python).expanduser().is_file():
        errors.append("runtime.python_executable: existing model-environment Python required")
    options = object_field("adapter_options")
    if options.get("suite") != config.get("suite"):
        errors.append("adapter_options.suite must equal suite")
    repo = options.get("repo_path")
    if repo is not None and (not isinstance(repo, str) or not Path(repo).expanduser().is_dir()):
        errors.append("adapter_options.repo_path: directory does not exist")
    checkpoint = options.get("checkpoint")
    if not isinstance(checkpoint, str) or not checkpoint.strip():
        errors.append("adapter_options.checkpoint: must select real fine-tuned weights")
    elif checkpoint.startswith(("/", "~", ".")) or ":\\" in checkpoint:
        if not Path(checkpoint).expanduser().exists():
            errors.append("adapter_options.checkpoint: local path does not exist")
    for key in ("checkpoint_suite", "normalization_suite"):
        if options.get(key) is not None and options[key] != config.get("suite"):
            errors.append(f"adapter_options.{key} must equal suite")
    for key in ("random_seed", "seed"):
        if key in options and options[key] != seed:
            errors.append(f"adapter_options.{key} must equal execution.random_seed")
    return {"model_id": config.get("model_id"), "static_configuration_ready": not errors,
            "weights_loaded": False, "policy_regression_verified": False, "errors": errors}


def run(config_path, manifest_path, output, *, candidate_replay=None, environment_config=None, video_config=None):
    config = read_json(config_path)
    manifest = read_json(manifest_path)
    suites = {episode["suite"] for episode in manifest["episodes"]}
    if len(suites) != 1:
        raise ValueError("one model run must contain exactly one suite")
    checked = check_config(config, next(iter(suites)))
    if checked["errors"]:
        raise ValueError("configuration is not ready:\n" + "\n".join(checked["errors"]))
    return evaluate(Path(manifest_path), Path(output),
                    policy_factory="benchmark.remaining_goals.isolated_policy:make_policy",
                    policy_config=config, policy_id=config["policy_id"],
                    max_chunk_steps=config["execution"]["max_chunk_steps"],
                    environment_config=environment_config, candidate_replay=candidate_replay,
                    video_config=normalize_video_config(video_config))


def _relative(base, value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def matrix(plan_path, output, *, max_workers=1, video_config=None):
    """Run isolated jobs with one explicit video configuration for the matrix."""
    video_config = normalize_video_config(video_config)
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = read_json(plan_path)
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs or type(max_workers) is not int or max_workers < 1:
        raise ValueError("matrix requires nonempty jobs and positive max_workers")
    prepared, identifiers, gpu_sets = [], set(), []
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("matrix jobs must be JSON objects")
        name = job.get("id", "")
        if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name) or name in identifiers:
            raise ValueError("matrix job ids must be unique simple directory names")
        identifiers.add(name)
        config = _relative(plan_path.parent, job["config"])
        manifest = _relative(plan_path.parent, job["manifest"])
        checkpoint_config = read_json(config)
        suites = {e["suite"] for e in read_json(manifest)["episodes"]}
        if len(suites) != 1:
            raise ValueError("matrix job contains mixed suites")
        readiness = check_config(checkpoint_config, next(iter(suites)))
        if readiness["errors"]:
            raise ValueError(f"{name}: " + "; ".join(readiness["errors"]))
        gpu = checkpoint_config.get("runtime", {}).get("cuda_visible_devices")
        if max_workers > 1:
            if gpu is None or not str(gpu).strip():
                raise ValueError("parallel runs require explicit disjoint runtime.cuda_visible_devices in every config")
            devices = {item.strip() for item in str(gpu).split(",")}
            if "" in devices or "-1" in devices:
                raise ValueError("parallel GPU assignments must identify nonempty visible devices")
            if any(devices & prior for prior in gpu_sets):
                raise ValueError("parallel runs require disjoint GPU assignments")
            gpu_sets.append(devices)
        command = [sys.executable, "-m", "benchmark.remaining_goals.evaluation", "run", "--config", str(config),
                   "--manifest", str(manifest), "--out", str(output / name)]
        command += ["--save-video" if video_config["enabled"] else "--no-save-video",
                    "--video-fps", str(video_config["fps"]), "--video-camera", video_config["camera"],
                    "--video-stride", str(video_config["stride"])]
        if job.get("candidate_replay"):
            command += ["--candidate-replay", str(_relative(plan_path.parent, job["candidate_replay"]))]
        if job.get("environment_config"):
            command += ["--environment-config", str(_relative(plan_path.parent, job["environment_config"]))]
        prepared.append((name, command, gpu))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "matrix_plan.json", plan)
    report = {"kind": "six_model_evaluation_matrix", "pool_suite_scores": False, "jobs": [], "status": "running",
              "video_config": video_config}
    write_json(output / "matrix_report.json", report)
    children = []
    cancelled = threading.Event()
    child_lock = threading.Lock()
    root = Path(__file__).resolve().parents[2]
    def execute(item):
        name, command, gpu = item
        environment = os.environ.copy()
        if gpu is not None:
            environment["CUDA_VISIBLE_DEVICES"] = str(gpu)
        start = time.monotonic()
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
            with child_lock:
                if cancelled.is_set():
                    raise RuntimeError("matrix was cancelled before launch")
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           env=environment, cwd=root,
                                           start_new_session=os.name != "nt",
                                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                children.append(process)
            code = process.wait()
        summary = output / name / "summary.json"
        return {"id": name, "exit_code": code, "elapsed_seconds": time.monotonic() - start,
                "summary": str(summary) if summary.is_file() else None,
                "log": str(output / f"{name}.log")}
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = []
    try:
        futures = [executor.submit(execute, item) for item in prepared]
        for future in as_completed(futures):
            row = future.result()
            report["jobs"].append(row)
            write_json(output / "matrix_report.json", report)
            print(f"{row['id']}: exit={row['exit_code']} ({row['elapsed_seconds']:.1f}s)", flush=True)
        report["status"] = "finished" if all(row["exit_code"] == 0 for row in report["jobs"]) else "finished_with_errors"
    except BaseException:
        report["status"] = "aborted"
        cancelled.set()
        for future in futures:
            future.cancel()
        with child_lock:
            launched = list(children)
        for child in launched:
            if child.poll() is None:
                # Each simulator owns a GPU worker child. Cancel that tree too.
                if os.name == "nt":
                    try:
                        tree = subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                        if tree.returncode and child.poll() is None:
                            child.terminate()
                    except (OSError, subprocess.SubprocessError) as error:
                        report.setdefault("cleanup_errors", []).append(f"process {child.pid}: {error}")
                        if child.poll() is None:
                            child.terminate()
                else:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        child.kill()
                    child.wait(timeout=5)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        write_json(output / "matrix_report.json", report)
    return report


def probe(config_path, manifest_path, output, index=0):
    """One real inference on a saved observation, not a simulator success test."""
    from .observation_artifact import load_observation_artifact
    config = read_json(config_path)
    manifest_path = Path(manifest_path)
    manifest = read_json(manifest_path)
    if type(index) is not int or not 0 <= index < len(manifest["episodes"]):
        raise ValueError("episode_index is outside the manifest")
    episode = manifest["episodes"][index]
    checked = check_config(config, episode["suite"])
    if checked["errors"]:
        raise ValueError("; ".join(checked["errors"]))
    observation = _observation(load_observation_artifact(manifest_path.parent, episode["initial_observation"]))
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    policy = SubprocessPolicy(config)
    try:
        policy.reset()
        start = time.monotonic()
        raw_action = policy.predict(observation, episode["instruction"])
        action = _actions(raw_action)
        report = {"kind": "model_inference_probe", "model_id": config["model_id"],
                  "policy_config": config, "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                  "episode_index": index, "observation": episode["initial_observation"],
                  "action_shape": list(action.shape), "action": action.tolist(),
                  "inference_seconds": time.monotonic() - start,
                  "provenance": policy.provenance, "success_rate_measured": False}
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, report)
        return report
    finally:
        policy.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="static config checks; no model loading")
    check.add_argument("--config", type=Path, action="append", required=True)
    check.add_argument("--out", type=Path)
    for name in ("run", "probe"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        if name == "run":
            command.add_argument("--candidate-replay", type=Path)
            command.add_argument("--environment-config", type=Path)
            _add_video_arguments(command)
        else:
            command.add_argument("--episode-index", type=int, default=0)
    batch = commands.add_parser("matrix")
    batch.add_argument("--plan", type=Path, required=True)
    batch.add_argument("--out", type=Path, required=True)
    batch.add_argument("--max-workers", type=int, default=1)
    _add_video_arguments(batch)
    score = commands.add_parser("summarize")
    score.add_argument("--run-dir", type=Path, required=True)
    _add_reporting_arguments(commands)
    args = parser.parse_args(argv)
    if args.command in ("uir-template", "report"):
        return _reporting_command(args)
    if args.command == "check":
        report = {"models": [check_config(read_json(path)) for path in args.config]}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if all(row["static_configuration_ready"] for row in report["models"]) else 2
    if args.command == "run":
        report = run(args.config, args.manifest, args.out, candidate_replay=args.candidate_replay,
                     environment_config=read_json(args.environment_config) if args.environment_config else None,
                     video_config=_video_config_from_args(args))
        print((args.out / "report.md").read_text(encoding="utf-8"))
        return 0 if report.get("run_status") == "finished" and report["counts"]["completed"] == report["counts"]["expected"] else 1
    if args.command == "matrix":
        return 0 if matrix(args.plan, args.out, max_workers=args.max_workers,
                           video_config=_video_config_from_args(args))["status"] == "finished" else 1
    if args.command == "probe":
        probe(args.config, args.manifest, args.out, args.episode_index)
    else:
        rescore(args.run_dir)
        print((args.run_dir / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
