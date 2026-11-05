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
from .evaluation import (JOB_SCHEMA_V3, PLAN_SCHEMA_V3, RUN_SCHEMA_V3, CALIBRATION_SCHEMA_V3,
                         validate_evaluation_contract, budget_plan)

RUN_SCHEMA = "remaining-finish-run-v1"
BANK_SCHEMA = "remaining-finish-normal-bank-v1"
RUN_SCHEMA_V2 = "remaining-finish-run-v2"
BANK_SCHEMA_V2 = "remaining-finish-normal-bank-v2"
EVAL_ROLES = {"validation_shadow": "normal_calibration", "normal_active": "normal_test",
              "remain_active": "remain_test", "remain_shadow": "remain_test"}
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
    if (head.get("schema_version") not in {"remaining-finish-head-v1", "remaining-finish-head-v2"} or
            head.get("artifact_sha256") != canonical_hash({k:v for k,v in head.items() if k != "artifact_sha256"})):
        raise ValueError("invalid head schema/hash")
    if head["weights"]["path"] != "head.npz" or file_sha(path.parent / "head.npz") != head["weights"]["sha256"]:
        raise ValueError("head weight bytes differ")
    if head["schema_version"] == "remaining-finish-head-v2":
        from .data import validate_head_identities
        identities = validate_head_identities(head.get("identities"))
        if (identities["split_identity"].get("schema_version") != "remaining-finish-source-domains-identity-v2"
                or head.get("identity_sha256") != {key: canonical_hash(value) for key, value in identities.items()}):
            raise ValueError("two-domain head identity hashes/schema differ")
    return head


def _registry(value, *, verify_files):
    from .data_registry import validate_source_registry
    registry = deepcopy(value) if isinstance(value, dict) else read_json(value)
    validate_source_registry(registry, verify_files=verify_files)
    return registry


def _normal_member_binding(report, member, registry):
    from .data_registry import source_identity
    assets = source_identity(registry)["assets"]
    provenance = report["provenance"]
    restored = provenance.get("restored_official_state", {})
    if (provenance.get("official_initial_state_file", {}).get("sha256") != assets["init_states_sha256"]
            or provenance.get("initial_state_index") != member["initial_state_index"]
            or restored.get("dtype") not in {"<f8", "=f8"}
            or restored.get("shape") != [member["state_dimension"]]
            or restored.get("sha256") != member["state_sha256"]
            or provenance.get("bddl_sha256") != assets["bddl_sha256"]):
        raise ValueError("normal preparation official init file/state/BDDL differs from its registered eval source")


def prepare_normal_bank(indices, output, *, environment_config=None, prepare=None, source_registry=None):
    """USER real stage; save precisely the requested ordinary 00 sources."""
    if (not indices or len(set(indices)) != len(indices) or
            any(type(i) is not int or i < 0 for i in indices)):
        raise ValueError("normal source indices must be distinct nonnegative integers")
    registry, members = None, None
    if source_registry is not None:
        from .data_registry import source_identity, registry_members
        from .data_profiles import EVAL_DOMAIN
        registry = _registry(source_registry, verify_files=True)
        members = {item["initial_state_index"]: item for role in ("normal_calibration", "normal_test")
                   for item in registry_members(registry, EVAL_DOMAIN, role)}
        if any(index not in members for index in indices):
            raise ValueError("new normal preparation accepts only registered normal_calibration/normal_test init sources")
    if prepare is None:
        from ..regression_states import prepare_normal00
        prepare = prepare_normal00
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bank = {"schema_version": BANK_SCHEMA_V2 if registry is not None else BANK_SCHEMA, "status": "preparing", "expected_indices": indices,
            "episodes": [], "preparations": [], "environment": None, "error": None}
    if registry is not None:
        bank.update(source_registry=registry, source_identity=source_identity(registry),
                    eval_sources=[deepcopy(members[index]) for index in indices], ancestry_independence="unproven")
    try:
        for index in indices:
            prefix = f"sources/{index:03d}"
            report = prepare("basket", index, out / prefix, environment_config=environment_config)
            bank["preparations"].append({"source_index": index, "path": prefix+"/preparation.json",
                                          "sha256": file_sha(out/prefix/"preparation.json")})
            if report["status"] != "prepared":
                raise RuntimeError(f"source {index} preparation failed: {report.get('error')}")
            if registry is not None:
                _normal_member_binding(report, members[index], registry)
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
        if (manifest.get("schema_version") not in {BANK_SCHEMA, BANK_SCHEMA_V2} or manifest.get("status") != "prepared" or
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
        members, registry = None, None
        if manifest["schema_version"] == BANK_SCHEMA_V2:
            from .data_registry import source_identity, registry_members
            from .data_profiles import EVAL_DOMAIN
            registry = _registry(manifest["source_registry"], verify_files=False)
            members = {item["initial_state_index"]: item for role in ("normal_calibration", "normal_test")
                       for item in registry_members(registry, EVAL_DOMAIN, role)}
            if (manifest.get("source_identity") != source_identity(registry)
                    or any(index not in members for index in indices)
                    or manifest.get("eval_sources") != [members[index] for index in indices]
                    or manifest.get("ancestry_independence") != "unproven"):
                raise ValueError("normal bank source domain/role/registry identity differs")
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
            if registry is not None:
                _normal_member_binding(report, members[index], registry)
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
    version = config.get("schema_version")
    if version not in {"remaining-finish-job-v1", "remaining-finish-job-v2", JOB_SCHEMA_V3}:
        raise ValueError("unsupported finish job config")
    versioned = version == JOB_SCHEMA_V3
    contract = validate_evaluation_contract(config.get("evaluation_contract")) if versioned else None
    if not versioned and "evaluation_contract" in config:
        raise ValueError("legacy job cannot silently select a new evaluation contract")
    two_domains = version in {"remaining-finish-job-v2", JOB_SCHEMA_V3}
    purpose = config["purpose"]
    if purpose not in PURPOSES:
        raise ValueError("invalid finish purpose")
    if versioned and purpose == "remain_shadow":
        raise ValueError("task010 budget authorizes new calibration, normal active and Remain active only")
    mode, split_name = PURPOSES[purpose]
    registry, source_id, members = None, None, None
    if two_domains:
        from .data_registry import source_identity, registry_members
        from .data_profiles import EVAL_DOMAIN
        if "split" in config or "alternative_confirmation" in config or not config.get("source_registry"):
            raise ValueError("two-domain job requires source_registry and cannot use legacy integer split")
        registry = _registry(config["source_registry"], verify_files=True)
        source_id = source_identity(registry)
        members = registry_members(registry, EVAL_DOMAIN, EVAL_ROLES[purpose])
        indices = [item["initial_state_index"] for item in members]
    else:
        if "source_registry" in config:
            raise ValueError("legacy job cannot consume a two-domain source registry")
        split = validate_split(config.get("split"), alternative_confirmation=config.get("alternative_confirmation"))
        indices = split[split_name]
    source, source_path = load_source(config["source"])
    expected_kind = "remain" if split_name == "remain_test" else "normal_bank"
    if config["source"]["kind"] != expected_kind:
        raise ValueError("source kind differs from purpose")
    if expected_kind == "normal_bank":
        if two_domains and (source.get("schema_version") != BANK_SCHEMA_V2 or source.get("source_identity") != source_id):
            raise ValueError("two-domain job requires this registry's v2 normal bank")
        if not two_domains and source.get("schema_version") != BANK_SCHEMA:
            raise ValueError("legacy job cannot consume a two-domain normal bank")
    masks = {(True, False), (False, True), (True, True)} if expected_kind == "remain" else {(False, False)}
    episodes = [deepcopy(e) for e in source["episodes"] if e["task_id"] == "basket"
                and e["initial_state_index"] in indices and tuple(e["initial_mask"]) in masks]
    expected = {(i, m) for i in indices for m in masks}
    found = [(e["initial_state_index"], tuple(e["initial_mask"])) for e in episodes]
    if len(found) != len(expected) or set(found) != expected:
        raise ValueError("source lacks the exact fixed source/mask set; no replacements")
    if len({e["episode_id"] for e in episodes}) != len(episodes):
        raise ValueError("duplicate episode identity")
    if two_domains:
        by_index = {member["initial_state_index"]: member for member in members}
        for episode in episodes:
            if (type(episode["initial_state_index"]) is not int or episode.get("seed") != episode["initial_state_index"]
                    or episode.get("bddl_sha256") != source_id["assets"]["bddl_sha256"]):
                raise ValueError("selected episode index/seed/BDDL differs from its registered eval source")
            episode["eval_source"] = deepcopy(by_index[episode["initial_state_index"]])
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
    if two_domains:
        from .data_registry import validate_source_identity
        if head.get("schema_version") != "remaining-finish-head-v2":
            raise ValueError("two-domain job requires a v2 head; legacy artifacts cannot be mixed")
        validate_source_identity(head["identities"]["split_identity"])
        if head["identities"]["split_identity"] != source_id:
            raise ValueError("head and evaluation source registries/profiles differ")
    elif head.get("schema_version") != "remaining-finish-head-v1" or head["identities"]["split_identity"].get("split") != split:
        raise ValueError("legacy head training groups differ from run groups")
    threshold, calibration = 0.5, None
    if mode == "active":
        calibration = read_json(config["calibration"])
        expected_schema = CALIBRATION_SCHEMA_V3 if versioned else "remaining-finish-calibration-v2" if two_domains else "remaining-finish-calibration-v1"
        if (calibration.get("schema_version") != expected_schema or
                calibration.get("calibration_sha256") != canonical_hash({k:v for k,v in calibration.items() if k != "calibration_sha256"}) or
                calibration.get("calibrated") is not True or
                calibration.get("binding", {}).get("head_sha256") != head["artifact_sha256"]):
            raise ValueError("active requires this head's complete useful normal-validation calibration")
        if versioned:
            _validate_active_calibration(calibration, contract, source_id)
        elif "evaluation_contract" in calibration or calibration.get("sensitivity_only") is True:
            raise ValueError("legacy active cannot consume versioned or sensitivity calibration")
        if two_domains:
            expected_members = registry_members(registry, EVAL_DOMAIN, "normal_calibration")
            if (calibration.get("source_identity") != source_id
                    or calibration.get("calibration_domain") != EVAL_DOMAIN
                    or calibration.get("calibration_role") != "normal_calibration"
                    or calibration.get("calibration_members") != expected_members
                    or calibration.get("calibration_source_keys") != [item["source_key"] for item in expected_members]
                    or calibration.get("validation_source_indices") != [item["initial_state_index"] for item in expected_members]):
                raise ValueError("active threshold belongs to a different source domain/role/profile or calibration group")
        elif calibration.get("validation_source_indices") != split["validation"]:
            raise ValueError("active calibration differs from the legacy validation group")
        threshold = calibration["selected_threshold"]
    runtime["policy_factory"] = "benchmark.remaining_goals.finish.oft:make_policy"
    runtime["finish"] = {"head_artifact": str(Path(config["head_artifact"]).resolve()), "threshold": threshold,
                         "threshold_identity": calibration["calibration_sha256"] if calibration else "validation-shadow-placeholder-0.5"}
    plan = {"schema_version": "remaining-finish-plan-v2" if two_domains else "remaining-finish-plan-v1", "protocol_version": PROTOCOL, "dry_plan": True,
            "simulation_created": False, "weights_loaded": False, "purpose": purpose, "mode": mode,
            "config": deepcopy(config), "policy_config": runtime, "video": video,
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
    if two_domains:
        plan.update(source_registry=registry, source_identity=source_id, eval_domain=EVAL_DOMAIN,
                    eval_role=EVAL_ROLES[purpose], eval_members=members, ancestry_independence="unproven",
                    source_binding_scope=("Fresh normal preparation binds original official init file and pre-settle state bytes."
                        if expected_kind == "normal_bank" else
                        "Legacy Remain index, saved edited states, model XML, BDDL and source/replay evidence are validated. Registered raw init state identity is an index association, not a claim that edited/saved state equals raw init or a retroactive pre-settle provenance record."))
    else:
        plan["split"] = split
    if versioned:
        plan.update(schema_version=PLAN_SCHEMA_V3, evaluation_contract=deepcopy(contract), budget_revision=budget_plan())
        plan["environment_config"]["evaluation_contract"] = deepcopy(contract)
        _validate_plan_evaluation(plan)
    plan["plan_sha256"] = canonical_hash(plan)
    return plan


def _validate_active_calibration(report, contract, source_id):
    """A derived table or a mismatched observer is never an active threshold."""
    if (validate_evaluation_contract(report.get("evaluation_contract")) != contract
            or report.get("release_method") != contract["release_method"]
            or report.get("calibration_rule") != contract["calibration_rule"]
            or report.get("thresholds") != contract["thresholds"]
            or report.get("sensitivity_only") is not False or report.get("active_eligible") is not True
            or report.get("validation_evidence_valid") is not True
            or report.get("status") != "candidate_threshold_frozen"
            or report.get("binding", {}).get("evaluation_contract_sha256") != contract["contract_sha256"]
            or report.get("binding", {}).get("source_identity_sha256") != canonical_hash(source_id)):
        raise ValueError("active requires a formally bound task010 calibration, never sensitivity-only data")
    threshold = report.get("selected_threshold")
    if type(threshold) not in (int, float) or threshold not in contract["thresholds"]:
        raise ValueError("active calibration has no valid frozen threshold; no fallback")
    if report.get("timely_steps") != 24 or report.get("confirmation_steps") != 4:
        raise ValueError("active calibration timing rule differs from task010")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or [item.get("threshold") for item in candidates] != contract["thresholds"]:
        raise ValueError("active calibration is missing its full frozen threshold search")
    feasible = [item for item in candidates if item.get("premature") == 0
                and item.get("unknown_first_hit") == 0 and item.get("timing_unknown") == 0]
    chosen = max(feasible, key=lambda row: (row.get("robust_timely", -1), row["threshold"])) if feasible else None
    if (report.get("expected") != 5 or report.get("completed") != 5 or report.get("errors") != 0
            or report.get("missing") != 0 or report.get("issues") != []
            or chosen is None or chosen.get("robust_timely", 0) <= 0 or chosen["threshold"] != threshold):
        raise ValueError("active calibration selected no useful robust candidate on all five sources")


def _validate_plan_evaluation(plan):
    if plan.get("schema_version") != PLAN_SCHEMA_V3:
        if ("evaluation_contract" in plan or "budget_revision" in plan
                or "evaluation_contract" in plan.get("environment_config", {})
                or "evaluation_contract" in plan.get("config", {})):
            raise ValueError("legacy plan cannot silently upgrade its measurement contract")
        return None
    contract = validate_evaluation_contract(plan.get("evaluation_contract"))
    if (plan["config"].get("schema_version") != JOB_SCHEMA_V3
            or plan["config"].get("evaluation_contract") != contract
            or plan["environment_config"].get("evaluation_contract") != contract
            or plan.get("budget_revision") != budget_plan()
            or plan.get("purpose") == "remain_shadow"):
        raise ValueError("versioned job/plan/environment/budget contracts differ")
    if "evaluation_contract" in plan["policy_config"] or "measurement" in plan["policy_config"]:
        raise ValueError("evaluator contract must stay outside policy configuration")
    threshold = plan.get("threshold")
    if (type(threshold) not in (int, float) or threshold not in contract["thresholds"]
            or plan["policy_config"].get("finish", {}).get("threshold") != threshold
            or plan["mode"] == "shadow" and threshold != 0.5):
        raise ValueError("frozen plan and policy threshold differ")
    return contract


def evidence_identity(metadata, episode):
    identity = {**{k: metadata[k] for k in ("run_id", "run_config_sha256", "manifest_hash", "mode", "head_sha256")},
            "protocol_version": PROTOCOL, "episode_id": episode["episode_id"],
            "state_sha256": episode["state_sha256"], **metadata["configuration"]}
    if metadata.get("schema_version") == RUN_SCHEMA_V3:
        identity["evaluation_contract"] = validate_evaluation_contract(metadata.get("evaluation_contract"))
        identity["threshold"] = metadata["plan"]["threshold"]
    return identity


def _identity_fields(plan):
    common = ("manifest_hash", "mode", "purpose", "head_sha256", "configuration", "episodes")
    fields = common + (("source_identity", "eval_domain", "eval_role", "eval_members", "ancestry_independence")
                     if plan.get("schema_version") in {"remaining-finish-plan-v2", PLAN_SCHEMA_V3} else ("split",))
    return fields + (("evaluation_contract", "budget_revision") if plan.get("schema_version") == PLAN_SCHEMA_V3 else ())


def _validate_plan_domains(plan):
    from .data_registry import source_identity, registry_members, validate_source_identity
    from .data_profiles import EVAL_DOMAIN
    registry = _registry(plan["source_registry"], verify_files=False)
    identity = source_identity(registry)
    validate_source_identity(plan["source_identity"])
    role = EVAL_ROLES[plan["purpose"]]
    members = registry_members(registry, EVAL_DOMAIN, role)
    if (plan["source_identity"] != identity or plan["head_split_identity"] != identity
            or plan["eval_domain"] != EVAL_DOMAIN or plan["eval_role"] != role
            or plan["eval_members"] != members or plan.get("ancestry_independence") != "unproven"
            or "split" in plan):
        raise ValueError("frozen FINISH plan source domain/profile/registry differs")
    masks = {"10", "01", "11"} if role == "remain_test" else {"00"}
    expected = {(member["source_key"], mask) for member in members for mask in masks}
    actual = []
    for episode in plan["episodes"]:
        member = episode.get("eval_source")
        if (member not in members or type(episode.get("initial_state_index")) is not int
                or episode["initial_state_index"] != member["initial_state_index"]):
            raise ValueError("frozen episode differs from its actual eval registry member")
        actual.append((member["source_key"], "".join(str(int(v)) for v in episode["initial_mask"])))
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("frozen run differs from the fixed eval source/mask population")


def _normal_capability(summary, purpose):
    if purpose != "normal_active":
        return summary
    rows = summary["episodes"]
    expected = len(rows)
    def complete(row):
        return bool(row.get("goals_at_exit")) and all(row["goals_at_exit"]) and row.get("released_at_exit") is True
    def timely(row):
        if "evaluation_contract" in summary:
            return complete(row) and (row.get("timing_diagnostic") or {}).get("timely") is True
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
    if "evaluation_contract" in summary:
        summary["ordinary_stopping_capability"].update(
            evaluation_contract=deepcopy(summary["evaluation_contract"]),
            timing_unknown=count(lambda row: (row.get("timing_diagnostic") or {}).get("timing_unknown") is True),
            timely_rule="first-hit correct and timely under every permitted unknown completion")
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
    metadata = {"schema_version": RUN_SCHEMA_V3 if plan.get("schema_version") == PLAN_SCHEMA_V3 else RUN_SCHEMA_V2 if plan.get("schema_version") == "remaining-finish-plan-v2" else RUN_SCHEMA, "protocol_version": PROTOCOL,
                "run_id": uuid.uuid4().hex, "run_config_sha256": plan["plan_sha256"],
                **{k:deepcopy(plan[k]) for k in _identity_fields(plan)},
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
            result = run_finish_episode(env, policy, episode, mode=plan["mode"], recorder=recorder, evidence=evidence,
                **plan["configuration"], **({"evaluation_contract": plan["evaluation_contract"],
                    "expected_threshold": plan["threshold"]} if "evaluation_contract" in plan else {}))
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
    summary = summarize(plan["episodes"], results, mode=plan["mode"],
        **({"evaluation_contract": plan["evaluation_contract"]} if "evaluation_contract" in plan else {}))
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
    if metadata.get("schema_version") not in {RUN_SCHEMA, RUN_SCHEMA_V2, RUN_SCHEMA_V3} or metadata.get("protocol_version") != PROTOCOL:
        raise ValueError("unsupported/mixed run schema; legacy STOP is not FINISH")
    plan = metadata["plan"]
    if plan["plan_sha256"] != canonical_hash({k:v for k,v in plan.items() if k != "plan_sha256"}) or metadata["run_config_sha256"] != plan["plan_sha256"]:
        raise ValueError("run plan hash mismatch")
    contract = _validate_plan_evaluation(plan)
    if metadata["schema_version"] in {RUN_SCHEMA_V2, RUN_SCHEMA_V3}:
        expected_plan = PLAN_SCHEMA_V3 if metadata["schema_version"] == RUN_SCHEMA_V3 else "remaining-finish-plan-v2"
        if plan.get("schema_version") != expected_plan:
            raise ValueError("two-domain run cannot contain a legacy plan")
        _validate_plan_domains(plan)
    elif plan.get("schema_version") != "remaining-finish-plan-v1":
        raise ValueError("legacy run cannot contain a two-domain plan")
    if metadata["schema_version"] != RUN_SCHEMA_V3 and ("evaluation_contract" in metadata or "budget_revision" in metadata):
        raise ValueError("legacy run metadata cannot contain a new evaluation contract")
    for key in _identity_fields(plan):
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
        from .evaluation import result_contract
        actual_contract = result_contract(result, contract)
        if actual_contract != contract:
            raise ValueError("result and run measurement versions differ")
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
    summary = summarize(metadata["episodes"], results, mode=metadata["mode"], stable_steps=stable_steps,
        **({"evaluation_contract": metadata["evaluation_contract"]} if "evaluation_contract" in metadata else {}))
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
    if metadata["schema_version"] in {RUN_SCHEMA_V2, RUN_SCHEMA_V3}:
        episodes = [{"episode_id": e["episode_id"], "initial_state_index": e["initial_state_index"],
                     "eval_source": deepcopy(e["eval_source"])} for e in metadata["episodes"]]
        report = calibrate_threshold(episodes, results, source_registry=metadata["plan"]["source_registry"],
            split_identity=metadata["source_identity"],
            **({"evaluation_contract": metadata["evaluation_contract"]} if "evaluation_contract" in metadata else {}))
    else:
        episodes = [{"episode_id":e["episode_id"], "source_index":e["initial_state_index"], "split":"validation"}
                    for e in metadata["episodes"]]
        report = calibrate_threshold(episodes, results, expected_validation_sources=metadata["split"]["validation"],
                                     split_identity=metadata["plan"]["head_split_identity"])
    report["binding"] = {"head_sha256": metadata["head_sha256"], "run_id": metadata["run_id"],
                         "source_run_sha256": file_sha(Path(directory)/"run.json")}
    if metadata["schema_version"] == RUN_SCHEMA_V3:
        report["binding"].update(evaluation_contract_sha256=metadata["evaluation_contract"]["contract_sha256"],
                                 source_identity_sha256=canonical_hash(metadata["source_identity"]))
    report.pop("calibration_sha256", None)
    report["calibration_sha256"] = canonical_hash(report)
    out = _derived_output(directory, output)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/"calibration.json", report)
    return report


def sensitivity(directory, output):
    """Derived 2x2 table from one fully verified new five-episode shadow run."""
    from .calibration_v2 import sensitivity_table
    metadata, results = read_run(directory)
    if metadata["schema_version"] != RUN_SCHEMA_V3 or metadata["purpose"] != "validation_shadow":
        raise ValueError("sensitivity requires the new task010 normal-calibration shadow evidence")
    episodes = [{"episode_id": e["episode_id"], "initial_state_index": e["initial_state_index"],
                 "eval_source": deepcopy(e["eval_source"])} for e in metadata["episodes"]]
    report = sensitivity_table(episodes, results, evaluation_contract=metadata["evaluation_contract"],
                              source_registry=metadata["plan"]["source_registry"], split_identity=metadata["source_identity"])
    report["binding"] = {"head_sha256": metadata["head_sha256"], "run_id": metadata["run_id"],
                         "source_run_sha256": file_sha(Path(directory)/"run.json"),
                         "evaluation_contract_sha256": metadata["evaluation_contract"]["contract_sha256"],
                         "source_identity_sha256": canonical_hash(metadata["source_identity"])}
    report.pop("sensitivity_sha256", None)
    report["sensitivity_sha256"] = canonical_hash(report)
    out = _derived_output(directory, output)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/"sensitivity.json", report)
    return report
