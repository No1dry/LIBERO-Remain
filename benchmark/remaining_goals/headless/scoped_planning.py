"""File-only Task031 populations and per-source immutable provenance plans."""
from copy import deepcopy
from pathlib import Path

from .planning import (COMMON_TEN_TASKS, TASKS, HORIZON, CONFIRMATION, CHUNK,
    canonical_hash, file_sha, resolve, load_runtimes)
from .source_acceptance import _json

CONFIG_SCHEMA = "remaining-headless-scoped-config-v1"
SOURCES_SCHEMA = "remaining-headless-composite-sources-v1"
PLAN_SCHEMA = "remaining-headless-scoped-plan-v1"
MISSING_TASKS = ("frypan_stove9", "cabinet_close_top_bowl")
PROTOCOLS = {"normal00-control", "selected-mask10"}


def runtime_protocol(protocol):
    from .protocols import NINE_PROTOCOLS
    if protocol in NINE_PROTOCOLS:
        return protocol
    if protocol not in PROTOCOLS:
        raise ValueError("unknown scoped protocol")
    return "normal00-control" if protocol == "normal00-control" else "mask10"


def protocol_version(protocol):
    from .protocols import NINE_PROTOCOLS, get_protocol
    if protocol in NINE_PROTOCOLS:
        return get_protocol(protocol).protocol_version
    runtime_protocol(protocol)
    return ("remaining-headless-normal00-control-v1" if protocol == "normal00-control"
            else "remaining-headless-goal-endpoint-v1")


def expected_episodes(protocol):
    runtime_protocol(protocol)
    normal = protocol == "normal00-control"
    return [{"episode_id": f"{task}_s{index:03d}_{'00' if normal else '10'}", "task_id": task,
        "suite": TASKS[task]["suite"], "task_name": TASKS[task]["name"],
        "evaluation_track": "primary" if TASKS[task]["suite"] == "libero_10" else "extension",
        "initial_state_index": index, "initial_mask": [False, False] if normal else [True, False],
        "policy_seed": 7, "development_source": task == "basket" and index < 5}
        for task in (COMMON_TEN_TASKS if normal else MISSING_TASKS) for index in range(10)]


def budget_plan(protocol, population):
    if population not in {"existing-eight", "missing-two", "all"}:
        raise ValueError("unknown population")
    if protocol == "selected-mask10" and population != "missing-two":
        raise ValueError("selected-mask10 only authorizes the missing-two20; old80 must not rerun")
    expected = expected_episodes(protocol)
    selected = [e for e in expected if population == "all"
        or (e["task_id"] in MISSING_TASKS) == (population == "missing-two")]
    return {"schema_version": "remaining-headless-scoped-budget-v1", "protocol": protocol,
        "protocol_version": protocol_version(protocol), "population": population,
        "expected": expected, "selected": selected, "selected_count": len(selected),
        "horizon": HORIZON, "confirmation_steps": CONFIRMATION, "max_chunk_steps": CHUNK,
        "policy_seed": 7, "retention_steps": 0, "maximum_policy_steps": HORIZON * len(selected),
        "new_model_episode_target_all_phases": 120, "old_mask10_episodes_to_reuse": 80,
        "simulation_created": False, "weights_loaded": False}


def read_composite(path, protocol):
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = _json(raw)
    if (value.get("schema_version") != SOURCES_SCHEMA or value.get("protocol") != protocol
            or value.get("expected") != expected_episodes(protocol) or not isinstance(value.get("entries"), list)):
        raise ValueError("composite protocol or fixed denominator differs")
    allowed = {(e["task_id"], e["initial_state_index"]) for e in value["expected"]}
    entries = {}
    for row in value["entries"]:
        if not isinstance(row, dict) or not {"task_id", "initial_state_index", "origin"} <= row.keys():
            raise ValueError("malformed composite entry")
        key = (row["task_id"], row["initial_state_index"])
        if type(key[1]) is not int or key not in allowed:
            raise ValueError("unplanned composite source")
        if key in entries:
            raise ValueError("duplicate composite source")
        origin = deepcopy(row["origin"])
        if origin is not None:
            if not isinstance(origin, dict):
                raise ValueError("origin must be an object or null")
            for name in ("manifest", "candidate_replay", "initialization"):
                if origin.get(name) is not None:
                    origin[name] = str(resolve(path.parent, origin[name]))
        entries[key] = origin
    return value, entries


def load_config(path):
    path = Path(path).resolve()
    config = _json(path.read_bytes())
    if (set(config) != {"schema_version", "protocol", "population", "runtime_config", "extension_transfer", "sources"}
            or config.get("schema_version") != CONFIG_SCHEMA):
        raise ValueError("explicit scoped config required; protocol overrides are not accepted")
    budget_plan(config["protocol"], config["population"])
    config["runtime_config"] = str(resolve(path.parent, config["runtime_config"]))
    config["sources"] = str(resolve(path.parent, config["sources"]))
    return config, load_runtimes(config["runtime_config"], config["extension_transfer"])


def dry_plan(config_path):
    from .scoped_sources import resolve_source
    from ..evaluation import check_config
    from ..cli import _source_hash
    config, runtimes = load_config(config_path)
    budget = budget_plan(config["protocol"], config["population"])
    composite, entries = read_composite(config["sources"], config["protocol"])
    checks = {suite: check_config(runtime, suite) for suite, runtime in runtimes.items()}
    selected = {e["episode_id"] for e in budget["selected"]}
    rows = []
    for expected in budget["expected"]:
        origin = entries.get((expected["task_id"], expected["initial_state_index"]))
        row = {**expected, "status": "missing", "error": "no source origin supplied", "selected": expected["episode_id"] in selected}
        if not row["selected"]:
            row.update(status="not_selected", error="outside this explicit model population")
        elif origin is not None:
            try:
                source = resolve_source(config["protocol"], expected["task_id"], expected["initial_state_index"], origin)
                if checks[expected["suite"]]["errors"]:
                    raise ValueError("runtime configuration: " + "; ".join(checks[expected["suite"]]["errors"]))
                row.update(status="ready", error=None, source_plan=source)
            except (OSError, ValueError, KeyError, TypeError) as error:
                row.update(status="missing" if isinstance(error, FileNotFoundError) else "failed",
                           error=f"{type(error).__name__}: {error}")
        rows.append(row)
    # Source inventory can grow in a separate explicit continuation. Code/model/
    # protocol/population cannot drift; each invocation freezes inventory bytes.
    identity = {"config": {k: v for k, v in config.items() if k != "sources"},
        "runtime_configs": runtimes, "budget": budget, "harness_source_sha256": _source_hash()}
    plan = {"schema_version": PLAN_SCHEMA, "protocol": config["protocol"],
        "protocol_version": protocol_version(config["protocol"]), "identity": identity,
        "batch_identity_sha256": canonical_hash(identity), "expected": budget["expected"],
        "selected_episode_ids": [e["episode_id"] for e in budget["selected"]],
        "composite": composite, "composite_sha256": file_sha(config["sources"]),
        "sources": rows, "runtime_checks": checks,
        "ready_episodes": sum(r["status"] == "ready" for r in rows),
        "simulation_created": False, "weights_loaded": False}
    plan["plan_sha256"] = canonical_hash(plan)
    return plan


def validate_plan(plan):
    if (plan.get("schema_version") != PLAN_SCHEMA
            or plan.get("plan_sha256") != canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
            or plan.get("batch_identity_sha256") != canonical_hash(plan["identity"])):
        raise ValueError("scoped plan hash/schema differs")
    protocol = plan["protocol"]
    config = plan["identity"]["config"]
    budget = budget_plan(protocol, config["population"])
    if (plan["protocol_version"] != protocol_version(protocol) or config["protocol"] != protocol
            or plan["identity"]["budget"] != budget or plan["expected"] != budget["expected"]
            or plan["selected_episode_ids"] != [e["episode_id"] for e in budget["selected"]]
            or len(plan["sources"]) != len(plan["expected"])):
        raise ValueError("scoped plan population/protocol differs")
    for row, expected in zip(plan["sources"], plan["expected"]):
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError("scoped source order/identity differs")
        selected = row["episode_id"] in plan["selected_episode_ids"]
        if (row.get("selected") is not selected or row.get("status") not in {"ready", "missing", "failed", "not_selected"}
                or (row["status"] == "not_selected") == selected):
            raise ValueError("scoped source selection differs")
        if row["status"] == "ready":
            source = row["source_plan"]
            if (source.get("protocol") != protocol or source.get("source_plan_sha256") != canonical_hash(
                    {k: v for k, v in source.items() if k != "source_plan_sha256"})
                    or len(source.get("episodes", [])) != 1
                    or any(source["episodes"][0].get(k) != v for k, v in expected.items())):
                raise ValueError("scoped ready source differs from planned episode")
    if plan["ready_episodes"] != sum(r["status"] == "ready" for r in plan["sources"]):
        raise ValueError("scoped readiness count differs")
    return plan
