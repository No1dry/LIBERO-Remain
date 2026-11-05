"""Explicit Plan6 populations and file-only source/reuse validation."""
from copy import deepcopy
from pathlib import Path

from ..nine_catalog import NINE_TASKS, NEW_TASKS, REUSE_TASKS, get_task
from .planning import canonical_hash, file_sha, read_json, resolve
from .protocols import NINE_NORMAL00, NINE_MASK10, NINE_PROTOCOLS, get_protocol

CONFIG_SCHEMA = "remaining-headless-nine-config-v1"
PLAN_SCHEMA = "remaining-headless-nine-plan-v1"
REUSE_SCHEMA = "remaining-headless-nine-reuse-v1"
SOURCES_SCHEMA = "remaining-headless-composite-sources-v1"


def condition(protocol):
    if protocol not in NINE_PROTOCOLS:
        raise ValueError("an explicit nine-task protocol is required")
    return "00" if protocol == NINE_NORMAL00 else "10"


def expected_episodes(protocol):
    bits = condition(protocol)
    rows = []
    for key in NINE_TASKS:
        profile = get_task(key)
        for index in range(10):
            rows.append({"episode_id": f"{key}_s{index:03d}_{bits}", "task_id": key,
                "suite": "libero_10", "task_name": profile["name"],
                "libero_task_id": profile["official_task_id"], "initial_state_index": index,
                "initial_mask": [bits[0] == "1", False], "policy_seed": 7,
                "evaluation_track": "primary", "development_source": key == "basket" and index < 5})
    return rows


def budget_plan(protocol, population="new-three"):
    if population != "new-three":
        raise ValueError("only new-three is executable; historical six are reuse-only")
    expected = expected_episodes(protocol)
    selected = [e for e in expected if e["task_id"] in NEW_TASKS]
    return {"schema_version": "remaining-headless-nine-budget-v1", "protocol": protocol,
        "protocol_version": get_protocol(protocol).protocol_version, "population": population,
        "expected": expected, "selected": selected,
        "reuse_only": [e for e in expected if e["task_id"] in REUSE_TASKS],
        "selected_count": 30, "expected_count": 90, "reuse_count": 60,
        "expected_all_conditions": 180, "reuse_all_conditions": 120,
        "new_model_episode_target_all_conditions": 60, "maximum_policy_steps": 30 * 520,
        "horizon": 520, "max_chunk_steps": 8, "policy_seed": 7,
        "endpoint_rule": "official_success_or_horizon" if protocol == NINE_NORMAL00 else "all_goals_release_five_observations_or_horizon",
        "simulation_created": False, "weights_loaded": False}


def sources_template(protocol):
    return {"schema_version": SOURCES_SCHEMA, "protocol": protocol,
        "expected": expected_episodes(protocol), "entries": [
            {"task_id": row["task_id"], "initial_state_index": row["initial_state_index"], "origin": None}
            for row in expected_episodes(protocol)]}


def read_sources(path, protocol):
    path = Path(path).resolve()
    value = read_json(path)
    if (value.get("schema_version") != SOURCES_SCHEMA or value.get("protocol") != protocol
            or value.get("expected") != expected_episodes(protocol) or not isinstance(value.get("entries"), list)):
        raise ValueError("nine-task source inventory identity/population differs")
    entries = {}
    for row in value["entries"]:
        key = row.get("task_id"), row.get("initial_state_index")
        if key[0] not in NINE_TASKS or type(key[1]) is not int or key[1] not in range(10) or key in entries:
            raise ValueError("foreign or duplicate source identity")
        origin = deepcopy(row.get("origin"))
        if origin is not None:
            if not isinstance(origin, dict):
                raise ValueError("source origin must be an object or null")
            for field in ("manifest", "candidate_replay", "initialization", "rgb_certificate"):
                if field in origin:
                    origin[field] = str(resolve(path.parent, origin[field]))
        entries[key] = origin
    return value, entries


def reuse_index(collection):
    result = {**deepcopy(collection), "schema_version": REUSE_SCHEMA}
    result.pop("content_hash", None)
    result["content_hash"] = canonical_hash(result)
    return result


def read_reuse(path):
    value = read_json(path)
    if (value.get("schema_version") != REUSE_SCHEMA or value.get("content_hash") != canonical_hash(
            {k: v for k, v in value.items() if k != "content_hash"}) or not isinstance(value.get("episodes"), dict)):
        raise ValueError("reuse index schema/content hash differs")
    allowed = {e["episode_id"]: e for protocol in NINE_PROTOCOLS for e in expected_episodes(protocol)
               if e["task_id"] in REUSE_TASKS}
    if set(value["episodes"]) != set(allowed):
        raise ValueError("reuse index must retain exactly the historical six tasks in both conditions")
    for name, record in value["episodes"].items():
        expected = allowed[name]
        if not isinstance(record, dict) or record.get("condition") != name[-2:]:
            raise ValueError("reuse record condition differs")
        for kind in ("legacy", "primary"):
            row = record.get(kind)
            if not isinstance(row, dict) or any(row.get(key) != expected[key] for key in
                    ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")):
                raise ValueError("reuse row task/source identity differs")
        invalid = []
        for ref in record.get("source", {}).get("verified_files", []):
            try:
                if file_sha(ref["path"]) != ref["sha256"]:
                    raise ValueError("recorded source file changed")
            except (OSError, KeyError, ValueError, TypeError) as error:
                invalid.append(f"{ref.get('path')}: {type(error).__name__}: {error}")
        if invalid:
            record["primary"].update(classification="technical_error", success=None,
                failure_reasons=["reuse_artifact_changed"], error="; ".join(invalid))
            record["source"]["current_reference_issues"] = invalid
    return value


def load_runtime(path):
    from ..regression import _validate_config
    from ..adapters.oft_transfer import SOG10_SOURCE, FACTORY, REPO_REVISION
    config = read_json(path)
    _validate_config(config)
    options, execution = config.get("adapter_options", {}), config.get("execution", {})
    if (config.get("suite") != "libero_10" or options.get("suite") != "libero_10"
            or config.get("model_id") != "openvla_oft" or config.get("policy_factory") != FACTORY
            or config.get("checkpoint_source") != SOG10_SOURCE or "finish" in config
            or any(key in options for key in ("suite_transfer", "finish", "normalization_suite", "unnorm_key", "checkpoint_suite"))
            or options.get("repo_revision", REPO_REVISION) != REPO_REVISION
            or options.get("center_crop", True) is not True
            or options.get("load_in_8bit", False) is not False or options.get("load_in_4bit", False) is not False
            or execution.get("max_chunk_steps") != 8 or execution.get("random_seed") != 7
            or options.get("seed", 7) != 7):
        raise ValueError("nine-task execution requires original pinned SOG10 on LIBERO10, seed7/chunk8/crop/full precision")
    return config


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    if (set(config) != {"schema_version", "protocol", "population", "runtime_config", "sources", "reuse_manifest"}
            or config.get("schema_version") != CONFIG_SCHEMA):
        raise ValueError("explicit nine-task configuration required")
    budget_plan(config["protocol"], config["population"])
    for field in ("runtime_config", "sources", "reuse_manifest"):
        config[field] = str(resolve(path.parent, config[field]))
    return config, load_runtime(config["runtime_config"])


def dry_plan(config_path):
    from .scoped_sources import resolve_source
    from ..evaluation import check_config
    from ..cli import _source_hash
    config, runtime = load_config(config_path)
    budget = budget_plan(config["protocol"], config["population"])
    composite, entries = read_sources(config["sources"], config["protocol"])
    reuse = read_reuse(config["reuse_manifest"])
    checks = check_config(runtime, "libero_10")
    rows = []
    for episode in budget["expected"]:
        new = episode["task_id"] in NEW_TASKS
        row = {**episode, "selected": new, "execution_kind": "new" if new else "reuse_only",
            "status": "missing", "error": "no new source supplied" if new else "reuse only; never executed"}
        if not new:
            row["reuse_record"] = deepcopy(reuse["episodes"][episode["episode_id"]])
            row.update(status="reuse_only", error=None)
        else:
            origin = entries.get((episode["task_id"], episode["initial_state_index"]))
            if origin is not None:
                try:
                    source = resolve_source(config["protocol"], episode["task_id"], episode["initial_state_index"], origin)
                    if checks["errors"]:
                        raise ValueError("runtime configuration: " + "; ".join(checks["errors"]))
                    row.update(status="ready", error=None, source_plan=source)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    row.update(status="missing" if isinstance(error, FileNotFoundError) else "failed",
                               error=f"{type(error).__name__}: {error}")
        rows.append(row)
    identity = {"config": {k: v for k, v in config.items() if k != "sources"},
        "runtime_configs": {"libero_10": runtime}, "budget": budget,
        "reuse_manifest_sha256": file_sha(config["reuse_manifest"]), "harness_source_sha256": _source_hash()}
    plan = {"schema_version": PLAN_SCHEMA, "protocol": config["protocol"],
        "protocol_version": get_protocol(config["protocol"]).protocol_version,
        "identity": identity, "batch_identity_sha256": canonical_hash(identity),
        "expected": budget["expected"], "selected_episode_ids": [e["episode_id"] for e in budget["selected"]],
        "sources": rows, "composite": composite, "composite_sha256": file_sha(config["sources"]),
        "reuse": reuse, "runtime_checks": checks, "ready_episodes": sum(r["status"] == "ready" for r in rows),
        "simulation_created": False, "weights_loaded": False}
    plan["plan_sha256"] = canonical_hash(plan)
    return plan


def validate_plan(plan):
    if (plan.get("schema_version") != PLAN_SCHEMA or plan.get("plan_sha256") != canonical_hash(
            {k: v for k, v in plan.items() if k != "plan_sha256"})
            or plan.get("batch_identity_sha256") != canonical_hash(plan["identity"])):
        raise ValueError("nine-task plan identity/hash differs")
    budget = budget_plan(plan["protocol"], plan["identity"]["config"]["population"])
    if (plan["identity"]["budget"] != budget or plan["expected"] != budget["expected"]
            or plan["protocol_version"] != get_protocol(plan["protocol"]).protocol_version
            or plan["selected_episode_ids"] != [e["episode_id"] for e in budget["selected"]]
            or len(plan["sources"]) != 90):
        raise ValueError("nine-task plan scope/budget differs")
    for row, expected in zip(plan["sources"], budget["expected"]):
        if any(row.get(k) != v for k, v in expected.items()):
            raise ValueError("nine-task plan episode identity differs")
        new = row["task_id"] in NEW_TASKS
        if (row["selected"] is not new or row["execution_kind"] != ("new" if new else "reuse_only")
                or row["status"] not in ({"ready", "missing", "failed"} if new else {"reuse_only"})):
            raise ValueError("reuse cannot become an executable row")
        if row["status"] == "ready":
            source = row["source_plan"]
            if (source.get("protocol") != plan["protocol"] or source.get("source_plan_sha256") != canonical_hash(
                    {k: v for k, v in source.items() if k != "source_plan_sha256"})
                    or len(source.get("episodes", [])) != 1
                    or any(source["episodes"][0].get(k) != v for k, v in expected.items())):
                raise ValueError("nine-task source differs from fixed episode")
    if plan["ready_episodes"] != sum(r["status"] == "ready" for r in plan["sources"]):
        raise ValueError("nine-task readiness count differs")
    return plan
