"""Explicit normal-state capability regression, separate from paired benchmarks."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from .cli import _add_video_arguments, _video_config_from_args
from .task_catalog import TASKS, select_tasks
from .video import normalize_video_config

PLAN_SCHEMA = "remaining-goals-normal00-plan-v1"
PURPOSE = "normal00-capability-regression"
SOG10_REPOSITORY = "moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10"
SOG10_REVISION = "638918f3d1c2e43a39a8a20772bdb8b91835e4b7"
OFT_REVISION = "e4287e94541f459edc4feabc4e181f537cd569a8"
FACTORY = "benchmark.remaining_goals.adapters.openvla_oft:make_policy"
STATUSES = ("completed", "preparation_error", "model_load_error", "runtime_error")


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _write(path, value):
    path = Path(path)
    body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, path)


def _string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("model config must be an object")
    if (config.get("model_id") != "openvla_oft" or config.get("policy_factory") != FACTORY
            or config.get("suite") != "libero_10"):
        raise ValueError("normal00 v1 supports the official OpenVLA-OFT adapter on libero_10")
    for field in ("runtime", "execution", "adapter_options", "checkpoint_source"):
        if not isinstance(config.get(field), dict):
            raise ValueError(f"{field} must be an object")
    execution, options, source = config["execution"], config["adapter_options"], config["checkpoint_source"]
    if type(execution.get("random_seed")) is not int or execution["random_seed"] != 7:
        raise ValueError("the first normal00 regression requires policy seed 7")
    if type(execution.get("max_chunk_steps")) is not int or execution["max_chunk_steps"] != 8:
        raise ValueError("the official OFT execution chunk must be 8")
    if options.get("suite") != "libero_10" or options.get("repo_revision") != OFT_REVISION:
        raise ValueError("adapter must declare the pinned OFT revision and libero_10 suite")
    for key in ("normalization_suite", "checkpoint_suite"):
        if key in options and options[key] != "libero_10":
            raise ValueError(f"adapter_options.{key} conflicts with libero_10")
    if source.get("repository") != SOG10_REPOSITORY or source.get("revision") != SOG10_REVISION:
        raise ValueError("declare the same pinned SOG10 checkpoint_source as the reviewed smoke")
    for name in ("seed", "random_seed"):
        if name in options and (type(options[name]) is not int or options[name] != 7):
            raise ValueError("adapter and worker policy seeds must both be 7")
    for key in ("repo_path", "checkpoint"):
        _string(options.get(key), f"adapter_options.{key}")
    _string(config.get("policy_id"), "policy_id")
    _string(config["runtime"].get("python_executable"), "runtime.python_executable")
    if "official_libero_config_path" in config["runtime"]:
        _string(config["runtime"]["official_libero_config_path"], "runtime.official_libero_config_path")
    for key, default in (("startup_timeout_seconds", 1200), ("predict_timeout_seconds", 180)):
        value = config["runtime"].get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"runtime.{key} must be finite and positive")


def build_plan(config, *, task_key="basket", indices=(0, 1, 2, 3, 4), protocol="both", video_config=None):
    """Pure planning: no model/simulator import, file existence checks or output writes."""
    _validate_config(config)
    select_tasks([task_key])
    task = TASKS[task_key]
    if task["suite"] != "libero_10":
        raise ValueError("normal00 v1 does not mix or extend the checkpoint's libero_10 suite")
    if not isinstance(indices, (list, tuple)) or not indices:
        raise ValueError("provide a nonempty explicit initial-state index list")
    if any(type(index) is not int or index < 0 for index in indices) or len(set(indices)) != len(indices):
        raise ValueError("initial-state indices must be unique nonnegative integers; no replacements")
    if protocol not in ("official", "remain", "both"):
        raise ValueError("protocol must be official, remain or both")
    protocols = ["official", "remain"] if protocol == "both" else [protocol]
    cases = []
    for index in indices:
        for name in protocols:
            cases.append({"id": f"{task_key}_i{index:03d}_{name}_seed7", "task_key": task_key,
                "task_name": task["name"], "suite": task["suite"], "initial_state_index": index,
                "protocol": name, "policy_seed": 7, "env_seed": 0 if name == "official" else index,
                "horizon": 520, "retention_steps": 0 if name == "official" else 150,
                "warmup_steps": 10 if name == "official" else 0,
                "settle_steps": 0 if name == "official" else 80,
                "preparation_audit_steps": 0 if name == "official" else 150, "max_chunk_steps": 8,
                "termination": "evaluator_success_or_budget" if name == "official" else "full_horizon_and_retention",
                "instruction_source": "exact official suite task.language at runtime",
                "environment_interpreter": config["runtime"]["python_executable"] if name == "official" else sys.executable})
    policy_steps = sum(case["horizon"] + case["retention_steps"] for case in cases)
    warmup = sum(case["warmup_steps"] for case in cases)
    preparation = sum(case["settle_steps"] + case["preparation_audit_steps"] for case in cases)
    plan = {"schema_version": PLAN_SCHEMA, "purpose": PURPOSE, "complete_paired_benchmark": False,
            "policy_id": config["policy_id"], "model_id": config["model_id"], "suite": task["suite"],
            "task_key": task_key, "task_name": task["name"], "indices": list(indices), "protocol": protocol,
            "model_identity": {"factory": FACTORY, "declared_repo_revision": OFT_REVISION,
                               "declared_checkpoint_source": deepcopy(config["checkpoint_source"]),
                               "checkpoint": config["adapter_options"]["checkpoint"],
                               "repo_path": config["adapter_options"]["repo_path"],
                               "normalization_suite": "libero_10", "resolved_unnorm_key": None},
            "resource_validation": "not_checked; actual versions, source status and checkpoint identity are recorded at execution",
            "checkpoint_bytes_verified": False, "config_sha256": _hash(config),
            "policy_seed_scope": "Each isolated case/worker reset uses seed 7; this differs from the upstream multi-episode script's single initial seeding. No CUDA determinism claim.",
            "environment_difference": {"official": "model Python native LIBERO; upstream robosuite requirement 1.4.1; actual packages recorded",
                                       "remain": "installed Remain simulator Python and strict pinned state restoration; robosuite 1.4.0"},
            "video_config": normalize_video_config(video_config), "cases": cases,
            "expected": len(cases), "expected_by_protocol": {name: len(indices) for name in protocols},
            "budget": {"max_policy_control_steps": policy_steps, "official_warmup_steps": warmup,
                       "max_rollout_physics_steps": policy_steps + warmup,
                       "separate_remain_preparation_steps": preparation,
                       "max_policy_queries": sum(math.ceil((case["horizon"] + case["retention_steps"]) / 8) for case in cases),
                       "model_loads": len(cases), "wall_clock_estimate_seconds": None,
                       "note": "Sequential isolated cases; preparation/restore internals and rendering cost excluded from policy budget. No measured wall-clock estimate."}}
    plan["plan_hash"] = _hash(plan)
    return plan


def summarize(plan, results, *, attempted_ids=None):
    """Keep all planned cases, error categories and missing records in denominators."""
    expected = {case["id"]: case for case in plan["cases"]}
    if len(expected) != len(plan["cases"]):
        raise ValueError("duplicate planned case")
    attempted = set(attempted_ids if attempted_ids is not None else [row["id"] for row in results])
    if not attempted <= expected.keys():
        raise ValueError("unknown attempted case")
    found = {}
    for row in results:
        identifier = row.get("id")
        if identifier not in expected or identifier in found:
            raise ValueError("unknown or duplicate regression result")
        case = expected[identifier]
        for key in ("protocol", "task_key", "task_name", "suite", "initial_state_index", "policy_seed", "env_seed"):
            if type(row.get(key)) is not type(case[key]) or row[key] != case[key]:
                raise ValueError(f"regression result identity mismatch: {key}")
        if row.get("plan_hash") != plan["plan_hash"] or row.get("status") not in STATUSES:
            raise ValueError("invalid regression result status or plan hash")
        if row.get("attempted") is not True or identifier not in attempted:
            raise ValueError("a result must belong to an attempted case")
        for key in ("prepared", "policy_started"):
            if row.get(key) is not None and type(row[key]) is not bool:
                raise ValueError(f"{key} must be boolean or unknown/null")
        if row["status"] == "completed":
            if not row["prepared"] or not row["policy_started"]:
                raise ValueError("completed case must be prepared and policy-started")
            if any(type(row.get(key)) is not bool for key in ("common_success", "native_success")):
                raise ValueError("completed success labels must be booleans")
        elif row.get("common_success") is not None or row.get("native_success") is not None:
            raise ValueError("error cases cannot contribute scored success labels")
        found[identifier] = row
    groups = []
    for protocol in plan["expected_by_protocol"]:
        cases = [case for case in plan["cases"] if case["protocol"] == protocol]
        rows = [found[case["id"]] for case in cases if case["id"] in found]
        valid = [row for row in rows if row["status"] == "completed"]
        group = {"protocol": protocol, "expected": len(cases),
                 "attempted": sum(case["id"] in attempted for case in cases),
                 "prepared": sum(row["prepared"] is True for row in rows),
                 "preparation_status_unknown": sum(row["prepared"] is None for row in rows),
                 "policy_started": sum(row["policy_started"] is True for row in rows),
                 "policy_start_status_unknown": sum(row["policy_started"] is None for row in rows),
                 "completed": len(valid), "missing": len(cases) - len(rows),
                 "missing_ids": [case["id"] for case in cases if case["id"] not in found],
                 **{status: sum(row["status"] == status for row in rows) for status in STATUSES if status != "completed"}}
        for metric in ("common_success", "native_success"):
            numerator = sum(row[metric] for row in valid)
            group[metric] = {"numerator": numerator, "denominator": len(valid),
                             "rate": numerator / len(valid) if valid else None,
                             "conservative_expected_rate": numerator / len(cases)}
        if protocol == "remain":
            group["remain_metrics"] = {}
            for metric in ("joint_success", "stable_final_success", "task_success_by_horizon"):
                values = [row.get("metrics", {}).get(metric) for row in valid]
                if any(type(value) is not bool for value in values):
                    raise ValueError("completed Remain cases must retain their native metric booleans")
                group["remain_metrics"][metric] = {"numerator": sum(values), "denominator": len(values),
                                                  "rate": sum(values) / len(values) if values else None}
        groups.append(group)
    return {"schema_version": "remaining-goals-normal00-summary-v1", "purpose": PURPOSE,
            "plan_hash": plan["plan_hash"], "complete_paired_benchmark": False, "pool_protocol_scores": False,
            "expected": len(expected), "attempted": len(attempted), "missing": len(expected) - len(found),
            "completed": sum(row["status"] == "completed" for row in found.values()), "by_protocol": groups,
            "common_metric_definition": "all goals satisfied at least once in policy observations 0..H; only protocol-complete records scored",
            "native_metric_definition": {"official": "official done in a policy step; evaluator stops on success",
                                         "remain": "joint_success after the full H+W retention contract"},
            "uir": None, "release_authorized": False,
            "notice": "Capability regression only. Errors/missing are not policy failures; conservative scores retain all requested cases."}


def _normalise_runtime_paths(config):
    config = deepcopy(config)
    # Same cwd-relative convention as the current adapters; never resolve interpreter symlinks.
    config["runtime"]["python_executable"] = os.path.abspath(Path(config["runtime"]["python_executable"]).expanduser())
    if "official_libero_config_path" in config["runtime"]:
        config["runtime"]["official_libero_config_path"] = str(Path(config["runtime"]["official_libero_config_path"]).expanduser().resolve())
    for key in ("repo_path", "checkpoint"):
        config["adapter_options"][key] = str(Path(config["adapter_options"][key]).expanduser().resolve())
    return config


def _terminate(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            if process.poll() is None:
                process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def _execute_process(config, case, directory, video_config, *, request_path, log_path, timeout):
    executable = config["runtime"]["python_executable"] if case["protocol"] == "official" else sys.executable
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONHASHSEED"] = str(case["policy_seed"])
    if config["runtime"].get("cuda_visible_devices") is not None:
        environment["CUDA_VISIBLE_DEVICES"] = str(config["runtime"]["cuda_visible_devices"])
    # The official parent must use native upstream packages, not inherited Remain config.
    if case["protocol"] == "official":
        environment.pop("LIBERO_CONFIG_PATH", None)
        if config["runtime"].get("official_libero_config_path"):
            environment["LIBERO_CONFIG_PATH"] = config["runtime"]["official_libero_config_path"]
    command = [executable, "-m", "benchmark.remaining_goals.regression_worker",
               "--request", str(request_path), "--out", str(directory)]
    with Path(log_path).open("x", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2], env=environment,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            _terminate(process)
            raise
    result_path = directory / "episode.json"
    if not result_path.is_file():
        raise RuntimeError(f"case child exit={code} left no episode.json; inspect {log_path.name}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if code and result.get("status") == "completed":
        raise RuntimeError(f"case child exit={code} conflicts with completed result")
    return result


def run_plan(config, plan, output, *, executor=None, case_timeout_seconds=None):
    """Execute exactly the fixed plan in fresh outputs; a failed case is never replaced."""
    if plan != build_plan(config, task_key=plan["task_key"], indices=plan["indices"],
                          protocol=plan["protocol"], video_config=plan["video_config"]):
        raise ValueError("plan/config identity or fixed protocol contract changed")
    timeout = case_timeout_seconds
    if timeout is None:
        timeout = config["runtime"].get("startup_timeout_seconds", 1200) + 84 * config["runtime"].get("predict_timeout_seconds", 180) + 600
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("case timeout must be finite and positive")
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name in ("requests", "logs", "cases"):
        (output / name).mkdir()
    _write(output / "plan.json", plan)
    runtime_config = _normalise_runtime_paths(config)
    _write(output / "model_config.json", runtime_config)
    state = {"schema_version": "remaining-goals-normal00-run-v1", "purpose": PURPOSE,
             "plan_hash": plan["plan_hash"], "runtime_config_sha256": _hash(runtime_config),
             "status": "running", "attempted_ids": [],
             "created_at_utc": datetime.now(timezone.utc).isoformat(), "results": []}
    execute = executor or _execute_process
    started = time.monotonic()
    try:
        for index, planned_case in enumerate(plan["cases"]):
            case = {**planned_case, "plan_hash": plan["plan_hash"]}
            directory = output / "cases" / f"{index:04d}"
            request = output / "requests" / f"{index:04d}.json"
            log = output / "logs" / f"{index:04d}.log"
            state["attempted_ids"].append(case["id"])
            _write(output / "run.json", state)
            _write(request, {"config": runtime_config, "case": case, "video_config": plan["video_config"]})
            case_start = time.monotonic()
            try:
                result = execute(runtime_config, case, directory, plan["video_config"],
                                 request_path=request, log_path=log, timeout=timeout)
                # Validate this case against the original plan before accepting any score.
                if not isinstance(result, dict) or result.get("id") != case["id"]:
                    raise ValueError("case process returned a result for a different case")
                summarize(plan, [result], attempted_ids=state["attempted_ids"])
            except Exception as error:
                result = {**case, "status": "runtime_error", "attempted": True,
                          "prepared": None, "policy_started": None, "common_success": None, "native_success": None,
                          "error_phase": "case_process_or_result_validation", "error": f"{type(error).__name__}: {error}",
                          "elapsed_seconds": time.monotonic() - case_start,
                          "partial_artifacts": directory.relative_to(output).as_posix()}
            state["results"].append(result)
            _write(output / "run.json", state)
            _write(output / "summary.json", summarize(plan, state["results"], attempted_ids=state["attempted_ids"]))
        state["status"] = "finished" if all(row["status"] == "completed" for row in state["results"]) else "finished_with_errors"
    except BaseException as error:
        state["status"] = "aborted"
        state["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        state["elapsed_seconds"] = time.monotonic() - started
        _write(output / "run.json", state)
        _write(output / "summary.json", summarize(plan, state["results"], attempted_ids=state["attempted_ids"]))
    return json.loads((output / "summary.json").read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task", default="basket")
    parser.add_argument("--indices", type=int, nargs="+", required=True)
    parser.add_argument("--protocol", choices=("official", "remain", "both"), default="both")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--case-timeout-seconds", type=float)
    _add_video_arguments(parser)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    plan = build_plan(config, task_key=args.task, indices=args.indices, protocol=args.protocol,
                      video_config=_video_config_from_args(args))
    if args.plan_out:
        if args.plan_out.resolve() == args.out.resolve() or args.plan_out.resolve().is_relative_to(args.out.resolve()):
            raise ValueError("plan-out must be outside the future run output")
        args.plan_out.parent.mkdir(parents=True, exist_ok=True)
        with args.plan_out.open("x", encoding="utf-8") as file:
            file.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    report = run_plan(config, plan, args.out, case_timeout_seconds=args.case_timeout_seconds)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["completed"] == report["expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
