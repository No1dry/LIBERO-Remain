"""Fixed, explicitly separate demonstration and official-initial-state domains."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

PROFILE_SCHEMA = "remaining-finish-data-profile-v2"
PROFILE_ID = "basket-two-source-domains-v1"
HEAD_DOMAIN = "head_demonstration"
EVAL_DOMAIN = "official_initial_state"
DEFAULT_PROFILE = {
    "schema_version": PROFILE_SCHEMA, "profile_id": PROFILE_ID,
    "domains": {
        HEAD_DOMAIN: {"groups": {
            "head_train": [f"demo_{i}" for i in range(5, 35)],
            "head_validation": [f"demo_{i}" for i in range(35, 40)],
            "head_unused": [f"demo_{i}" for i in (*range(5), *range(40, 50))],
        }},
        EVAL_DOMAIN: {"groups": {
            "normal_calibration": list(range(35, 40)),
            "normal_test": list(range(40, 50)),
            "remain_test": list(range(5)),
        }},
    },
}
ASSET_KEYS = {"hdf5_path": "hdf5_sha256", "init_states_path": "init_states_sha256",
              "bddl_path": "bddl_sha256"}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def require_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("source identity requires lowercase SHA256")
    return value


def validate_profile(profile):
    """Do not infer a domain, rename a role, or substitute a missing member."""
    if not isinstance(profile, dict) or set(profile) != set(DEFAULT_PROFILE):
        raise ValueError("two-domain profile needs its explicit version, id and domains")
    # Canonical bytes also distinguish bools/floats from declared integer indices.
    if canonical_hash(profile) != canonical_hash(DEFAULT_PROFILE):
        raise ValueError("unsupported data profile or changed fixed source-domain groups")
    return deepcopy(profile)


def validate_domain_config(config):
    if not isinstance(config, dict):
        raise ValueError("two-domain data config must be an object")
    if any(key in config for key in ("split", "trajectory_source_map", "alternative_confirmation")):
        raise ValueError("two-domain profile cannot mix legacy source mapping/split fields")
    profile = validate_profile(config.get("data_profile"))
    expected = config.get("expected_assets")
    if not isinstance(expected, dict) or set(expected) != set(ASSET_KEYS.values()):
        raise ValueError("two-domain config requires all three expected_assets SHA256 values")
    for digest in expected.values():
        require_hash(digest)
    for key in (*ASSET_KEYS, "original_instruction"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"two-domain config requires {key}")
    if type(config.get("state_stride", 8)) is not int or config.get("state_stride", 8) != 8:
        raise ValueError("two-domain sampling is fixed at stride8 plus the last saved state")
    return profile


def sampled_frames(count):
    if type(count) is not int or count < 1:
        raise ValueError("trajectory must have at least one saved state")
    return sorted(set(range(0, count, 8)) | {count - 1})
