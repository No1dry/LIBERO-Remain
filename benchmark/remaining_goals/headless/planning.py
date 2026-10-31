"""File-only frozen ten-task plan and independent task readiness."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from ..task_catalog import COMMON_TEN_TASKS, TASKS, TASK_TRACKS

PROTOCOL = "remaining-headless-goal-endpoint-v1"
CONFIG_SCHEMA = "remaining-headless-batch-config-v1"
PLAN_SCHEMA = "remaining-headless-batch-plan-v1"
HORIZON, CONFIRMATION, CHUNK = 520, 4, 8
VIDEO = {"enabled": True, "camera": "both", "fps": 20, "stride": 1}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def resolve(base, path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("nonempty file path required")
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (Path(base) / value).resolve()


def planned_episodes():
    return [{"episode_id": f"{task}_s{index:03d}_10", "task_id": task,
             "suite": TASKS[task]["suite"], "task_name": TASKS[task]["name"],
             "evaluation_track": "primary" if TASKS[task]["suite"] == "libero_10" else "extension",
             "initial_state_index": index, "initial_mask": [True, False], "policy_seed": 7,
             "development_source": task == "basket" and index < 5}
            for task in COMMON_TEN_TASKS for index in range(10)]


def budget_plan():
    return {"schema_version": "remaining-headless-budget-v1", "protocol_version": PROTOCOL,
            "episodes": planned_episodes(), "expected": 100, "horizon": HORIZON,
            "confirmation_steps": CONFIRMATION, "max_chunk_steps": CHUNK,
            "retention_steps": 0, "maximum_policy_steps": 52000,
            "primary": 60, "extension": 40, "policy_seed": 7,
            "extra_smoke_or_calibration_episodes": 0, "simulation_created": False,
            "weights_loaded": False, "notice": "Exactly ten official init indices 0..9 per task, mask10 only. State preparation/replay steps recorded separately. Basket 0..4 are development sources. No automatic retries."}


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    if (config.get("schema_version") != CONFIG_SCHEMA
            or set(config) != {"schema_version", "runtime_config", "extension_transfer", "sources"}
            or not isinstance(config["sources"], dict) or set(config["sources"]) != set(COMMON_TEN_TASKS)):
        raise ValueError("task011 requires the explicit ten-task configuration and no extra protocol overrides")
    runtime_path = resolve(path.parent, config["runtime_config"])
    primary = read_json(runtime_path)
    from ..regression import _validate_config
    from ..adapters.oft_transfer import validate_suite_transfer, validate_sog10_pair
    _validate_config(primary)
    if "finish" in primary or "finish" in primary.get("adapter_options", {}) or "suite_transfer" in primary["adapter_options"]:
        raise ValueError("task011 starts from the original SOG10 policy, without FINISH or an implicit transfer")
    # Paths in an existing model config keep the repository-root interpretation
    # used by the existing worker. New task source paths are config-relative.
    extension = deepcopy(primary)
    extension["suite"] = extension["adapter_options"]["suite"] = "libero_90"
    extension["adapter_options"]["suite_transfer"] = deepcopy(config["extension_transfer"])
    extension["policy_id"] = primary["policy_id"] + "-libero90-zero-shot"
    validate_suite_transfer(extension)
    validate_sog10_pair(primary, extension)
    for task, source in config["sources"].items():
        if not isinstance(source, dict) or set(source) != {"manifest", "candidate_replay"}:
            raise ValueError(f"{task}: explicit manifest and independent replay paths required")
        for key in source:
            source[key] = str(resolve(path.parent, source[key]))
    config["runtime_config"] = str(runtime_path)
    return config, {"libero_10": primary, "libero_90": extension}


def source_plan(task, source):
    """Use existing complete paired-bank and independent replay validation."""
    from ..pilot import _source
    manifest, raw, replay_raw, replay = _source(source["manifest"], source["candidate_replay"])
    catalog = TASKS[task]
    selected = [deepcopy(e) for e in manifest["episodes"] if e["task_id"] == task
                and e["initial_mask"] == [True, False] and e["initial_state_index"] in range(10)]
    selected.sort(key=lambda e: e["initial_state_index"])
    if [e["initial_state_index"] for e in selected] != list(range(10)):
        raise ValueError(f"{task}: all ten fixed mask10 sources 0..9 are required; never replace failed sources")
    for episode in selected:
        index = episode["initial_state_index"]
        if (episode["suite"] != catalog["suite"] or episode["task_name"] != catalog["name"]
                or episode["goal_specs"] != catalog["goals"]
                or episode["episode_id"] != f"{task}_s{index:03d}_10"):
            raise ValueError(f"{task}: task/goal order/source identity differs from the frozen catalog")
        episode["evaluation_track"] = "primary" if catalog["suite"] == "libero_10" else "extension"
        episode["development_source"] = task == "basket" and index < 5
        episode["policy_seed"] = 7
    result = {"task_id": task, "suite": catalog["suite"], "status": "ready",
              "episodes": selected, "manifest": manifest, "source": deepcopy(source),
              "source_files": {"manifest.json": hashlib.sha256(raw).hexdigest(),
                               "replay_report.json": hashlib.sha256(replay_raw).hexdigest()},
              "candidate_replay_evidence": replay,
              "environment_config": {"manifest_dir": str(Path(source["manifest"]).parent),
                  "environment": manifest["environment"], "image_size": 256, "control_freq": 20}}
    result["source_plan_sha256"] = canonical_hash(result)
    return result


def dry_plan(config_path):
    from ..evaluation import check_config
    from ..cli import _source_hash
    config, runtimes = load_config(config_path)
    checks = {suite: check_config(runtime, suite) for suite, runtime in runtimes.items()}
    tasks = []
    for task in COMMON_TEN_TASKS:
        try:
            row = source_plan(task, config["sources"][task])
            if checks[row["suite"]]["errors"]:
                raise ValueError("model runtime configuration: " + "; ".join(checks[row["suite"]]["errors"]))
        except (OSError, ValueError, KeyError, TypeError) as error:
            row = {"task_id": task, "suite": TASKS[task]["suite"], "status": "preparation_error",
                   "error": f"{type(error).__name__}: {error}", "episodes": []}
        tasks.append(row)
    identity = {"config": config, "runtime_configs": runtimes, "budget": budget_plan(),
                "harness_source_sha256": _source_hash()}
    plan = {"schema_version": PLAN_SCHEMA, "protocol_version": PROTOCOL,
            "identity": identity, "batch_identity_sha256": canonical_hash(identity),
            "expected": planned_episodes(), "tasks": tasks, "runtime_checks": checks,
            "ready_episodes": sum(10 for row in tasks if row["status"] == "ready"),
            "simulation_created": False, "weights_loaded": False}
    plan["plan_sha256"] = canonical_hash(plan)
    return plan


def validate_plan(plan):
    if (plan.get("schema_version") != PLAN_SCHEMA or plan.get("protocol_version") != PROTOCOL
            or plan.get("expected") != planned_episodes()
            or plan.get("plan_sha256") != canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
            or plan.get("batch_identity_sha256") != canonical_hash(plan["identity"])
            or plan["identity"].get("budget") != budget_plan()
            or [row.get("task_id") for row in plan.get("tasks", [])] != list(COMMON_TEN_TASKS)):
        raise ValueError("headless batch plan/identity differs from the frozen 100-episode protocol")
    for row in plan["tasks"]:
        if row["status"] == "ready" and row.get("source_plan_sha256") != canonical_hash(
                {k: v for k, v in row.items() if k != "source_plan_sha256"}):
            raise ValueError("headless source plan hash mismatch")
    return plan
