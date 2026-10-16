"""File-only, content-bound source registries. No simulator or policy imports."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .data_profiles import (ASSET_KEYS, HEAD_DOMAIN, EVAL_DOMAIN, canonical_hash,
    require_hash, sampled_frames, validate_domain_config, validate_profile)

REGISTRY_SCHEMA = "remaining-finish-source-registry-v2"
SOURCE_IDENTITY_SCHEMA = "remaining-finish-source-domains-identity-v2"


def _asset_digests(assets):
    if not isinstance(assets, dict) or set(assets) != set(ASSET_KEYS):
        raise ValueError("source registry requires HDF, initial-state and BDDL assets")
    return {target: require_hash(assets[source]["sha256"]) for source, target in ASSET_KEYS.items()}


def _registry_digest(registry):
    payload = deepcopy({key: value for key, value in registry.items() if key != "registry_sha256"})
    # Paths are relocation metadata. Every source's actual bytes remain bound.
    payload["assets"] = _asset_digests(payload["assets"])
    return canonical_hash(payload)


def _groups(profile, digests):
    return {
        HEAD_DOMAIN: {role: [f"hdf:{digests['hdf5_sha256']}:{name}" for name in names]
            for role, names in profile["domains"][HEAD_DOMAIN]["groups"].items()},
        EVAL_DOMAIN: {role: [f"init:{digests['init_states_sha256']}:{index}" for index in indices]
            for role, indices in profile["domains"][EVAL_DOMAIN]["groups"].items()},
    }


def build_source_registry(config):
    """Inspect actual files; no first-state matching, manual mapping or restoration."""
    from .data import _file_hash, read_demonstrations, read_initial_states, state_sha256
    profile = validate_domain_config(config)
    assets = {key: {"path": str(Path(config[key])), "sha256": _file_hash(config[key])} for key in ASSET_KEYS}
    digests = _asset_digests(assets)
    if digests != config["expected_assets"]:
        raise ValueError("actual source bytes differ from expected_assets")
    trajectories = read_demonstrations(config["hdf5_path"])
    initials = read_initial_states(config["init_states_path"])
    groups = _groups(profile, digests)
    head_owners = {name: role for role, names in profile["domains"][HEAD_DOMAIN]["groups"].items() for name in names}
    eval_owners = {index: role for role, indices in profile["domains"][EVAL_DOMAIN]["groups"].items() for index in indices}
    if {item["trajectory_id"] for item in trajectories} != set(head_owners) or len(trajectories) != len(head_owners):
        raise ValueError("HDF trajectory groups differ from the fixed fifty actual group names")
    if len(initials) != 50 or any(index >= len(initials) for index in eval_owners):
        raise ValueError("official initial-state file must contain the fifty declared vectors")
    records = []
    for trajectory in trajectories:
        name, states, xml = trajectory["trajectory_id"], trajectory["states"], trajectory["model_xml"]
        if not isinstance(xml, str) or not xml.strip():
            raise ValueError(f"trajectory {name} lacks actual model XML")
        import hashlib
        role = head_owners[name]
        records.append({"domain": HEAD_DOMAIN, "role": role, "trajectory_id": name,
            "source_key": f"hdf:{digests['hdf5_sha256']}:{name}", "saved_states": len(states),
            "state_dimension": int(states.shape[1]), "state_sha256s": [state_sha256(state) for state in states],
            "model_xml_sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(),
            "sampled_frame_indices": sampled_frames(len(states)) if role != "head_unused" else []})
    head = {"domain": HEAD_DOMAIN, "groups": groups[HEAD_DOMAIN], "records": records,
            "trajectory_count": len(records)}
    head["sha256"] = canonical_hash(head)
    evaluation = {"domain": EVAL_DOMAIN, "groups": groups[EVAL_DOMAIN], "state_count": len(initials),
        "state_dimension": int(initials.shape[1]), "records": [
            {"domain": EVAL_DOMAIN, "role": eval_owners.get(index), "initial_state_index": index,
             "source_key": f"init:{digests['init_states_sha256']}:{index}",
             "state_dimension": int(state.size), "state_sha256": state_sha256(state)}
            for index, state in enumerate(initials)]}
    evaluation["sha256"] = canonical_hash(evaluation)
    registry = {"schema_version": REGISTRY_SCHEMA, "profile": profile,
        "profile_sha256": canonical_hash(profile), "assets": assets, "expected_assets": deepcopy(digests),
        "head_registry": head, "eval_registry": evaluation, "status": "registered",
        "simulation_created": False, "labels_generated": 0, "ready_for_feature_export": False,
        "ancestry_independence": "unproven", "demo_to_init_mapping": None}
    registry["registry_sha256"] = _registry_digest(registry)
    return validate_source_registry(registry, verify_files=True)


def validate_source_registry(registry, *, verify_files=False):
    if not isinstance(registry, dict) or registry.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError("unsupported source registry schema")
    legacy = {"source_index", "split", "trajectory_source_map", "alternative_confirmation",
              "collection_provenance", "manually_confirmed", "edited_variant"}
    if legacy.intersection(registry):
        raise ValueError("source registry cannot mix legacy mapping or edited evaluation provenance")
    profile = validate_profile(registry.get("profile"))
    digests = _asset_digests(registry.get("assets"))
    if registry.get("expected_assets") != digests or registry.get("profile_sha256") != canonical_hash(profile):
        raise ValueError("registry profile or expected asset binding differs")
    if registry.get("registry_sha256") != _registry_digest(registry):
        raise ValueError("source registry hash mismatch")
    if (registry.get("status") != "registered" or registry.get("simulation_created") is not False
            or type(registry.get("labels_generated")) is not int or registry["labels_generated"] != 0
            or registry.get("ready_for_feature_export") is not False
            or registry.get("ancestry_independence") != "unproven" or registry.get("demo_to_init_mapping") is not None):
        raise ValueError("file registry cannot claim labels, physical readiness or cross-domain ancestry")
    expected_groups = _groups(profile, digests)
    head, evaluation = registry.get("head_registry"), registry.get("eval_registry")
    for domain, part in ((HEAD_DOMAIN, head), (EVAL_DOMAIN, evaluation)):
        if (not isinstance(part, dict) or part.get("domain") != domain or part.get("groups") != expected_groups[domain]
                or part.get("sha256") != canonical_hash({k: v for k, v in part.items() if k != "sha256"})):
            raise ValueError("source subregistry domain, group or content hash mismatch")
    records = head.get("records")
    if not isinstance(records, list) or len(records) != 50 or head.get("trajectory_count") != 50:
        raise ValueError("head registry lacks fixed trajectory coverage")
    owners = {name: role for role, names in profile["domains"][HEAD_DOMAIN]["groups"].items() for name in names}
    seen, states = set(), {}
    for record in records:
        if not isinstance(record, dict) or (legacy | {"initial_state_index"}).intersection(record):
            raise ValueError("head registry contains a legacy or evaluation-state record")
        name, role = record.get("trajectory_id"), record.get("role")
        if (name not in owners or name in seen or owners[name] != role or record.get("domain") != HEAD_DOMAIN
                or record.get("source_key") != f"hdf:{digests['hdf5_sha256']}:{name}"):
            raise ValueError("head registry trajectory domain/role/key mismatch")
        seen.add(name)
        n, dimension = record.get("saved_states"), record.get("state_dimension")
        if type(n) is not int or n < 1 or type(dimension) is not int or dimension < 1:
            raise ValueError("invalid head state layout")
        require_hash(record.get("model_xml_sha256"))
        if record.get("sampled_frame_indices") != (sampled_frames(n) if role != "head_unused" else []):
            raise ValueError("head sampling differs from stride8 plus last state")
        hashes = record.get("state_sha256s")
        if not isinstance(hashes, list) or len(hashes) != n:
            raise ValueError("head frame hashes are incomplete")
        for digest in hashes:
            require_hash(digest)
            if digest in states and states[digest] != role:
                raise ValueError("direct saved-state duplicate across head groups")
            states[digest] = role
    records = evaluation.get("records")
    if (not isinstance(records, list) or len(records) != 50 or evaluation.get("state_count") != 50
            or type(evaluation.get("state_dimension")) is not int or evaluation["state_dimension"] < 1):
        raise ValueError("eval registry lacks fixed initial-state coverage/layout")
    owners = {index: role for role, indices in profile["domains"][EVAL_DOMAIN]["groups"].items() for index in indices}
    seen = set()
    for record in records:
        if not isinstance(record, dict) or (legacy | {"trajectory_id", "saved_state_index"}).intersection(record):
            raise ValueError("eval registry contains a legacy or demonstration record")
        index = record.get("initial_state_index")
        if (type(index) is not int or not 0 <= index < 50 or index in seen or record.get("domain") != EVAL_DOMAIN
                or record.get("role") != owners.get(index) or record.get("state_dimension") != evaluation["state_dimension"]
                or record.get("source_key") != f"init:{digests['init_states_sha256']}:{index}"):
            raise ValueError("official initial-state registry key/role/layout mismatch")
        require_hash(record.get("state_sha256"))
        seen.add(index)
    if verify_files:
        from .data import _file_hash
        for key, entry in registry["assets"].items():
            if not isinstance(entry.get("path"), str) or _file_hash(entry["path"]) != entry["sha256"]:
                raise ValueError(f"actual source file changed: {key}")
    return registry


def registry_members(registry, domain, role):
    validate_source_registry(registry)
    if domain not in (HEAD_DOMAIN, EVAL_DOMAIN) or role not in registry["profile"]["domains"][domain]["groups"]:
        raise ValueError("unknown source domain or role")
    part = registry["head_registry" if domain == HEAD_DOMAIN else "eval_registry"]
    by_key = {row["source_key"]: row for row in part["records"]}
    return [deepcopy(by_key[key]) for key in part["groups"][role]]


def source_identity(registry):
    validate_source_registry(registry)
    result = {"schema_version": SOURCE_IDENTITY_SCHEMA, "profile": deepcopy(registry["profile"]),
        "profile_sha256": registry["profile_sha256"], "registry_sha256": registry["registry_sha256"],
        "head_registry_sha256": registry["head_registry"]["sha256"],
        "eval_registry_sha256": registry["eval_registry"]["sha256"],
        "groups": {HEAD_DOMAIN: deepcopy(registry["head_registry"]["groups"]),
                   EVAL_DOMAIN: deepcopy(registry["eval_registry"]["groups"])},
        "assets": _asset_digests(registry["assets"]), "ancestry_independence": "unproven"}
    return validate_source_identity(result)


def validate_source_identity(identity):
    keys = {"schema_version", "profile", "profile_sha256", "registry_sha256", "head_registry_sha256",
            "eval_registry_sha256", "groups", "assets", "ancestry_independence"}
    if not isinstance(identity, dict) or set(identity) != keys or identity.get("schema_version") != SOURCE_IDENTITY_SCHEMA:
        raise ValueError("unsupported or mixed source-domain identity")
    profile = validate_profile(identity["profile"])
    if identity["profile_sha256"] != canonical_hash(profile) or identity["ancestry_independence"] != "unproven":
        raise ValueError("source-domain profile/ancestry mismatch")
    for key in ("registry_sha256", "head_registry_sha256", "eval_registry_sha256"):
        require_hash(identity[key])
    if not isinstance(identity["assets"], dict) or set(identity["assets"]) != set(ASSET_KEYS.values()):
        raise ValueError("source-domain identity lacks the three assets")
    for value in identity["assets"].values():
        require_hash(value)
    if identity["groups"] != _groups(profile, identity["assets"]):
        raise ValueError("source-domain groups differ from actual asset keys")
    return deepcopy(identity)
