"""Explicit task010 evaluation contracts, independent of frozen head labels.

Missing fields always mean legacy. No simulator/model imports or implicit
upgrade of old files is performed by this module.
"""
from copy import deepcopy
import hashlib
import json

RELEASE_V1 = "panda-dualpad-contact-and-conservative-pinch-clearance-v1"
RELEASE_V2 = "panda-contact-pinch-world-axis-separation-v2"
CALIBRATION_LEGACY = "first-hit-full-trajectory-known-v1"
CALIBRATION_V2 = "first-hit-robust-tau-v2"
CONTRACT_SCHEMA = "remaining-finish-evaluation-contract-v1"
MEASUREMENT_SCHEMA = "remaining-finish-dual-measurement-v1"
RESULT_SCHEMA_V2 = "remaining-finish-episode-v2"
JOB_SCHEMA_V3 = "remaining-finish-job-v3"
PLAN_SCHEMA_V3 = "remaining-finish-plan-v3"
RUN_SCHEMA_V3 = "remaining-finish-run-v3"
CALIBRATION_SCHEMA_V3 = "remaining-finish-calibration-v3"
EVIDENCE_SCHEMA_V2 = "remaining-finish-evidence-v2"


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def evaluation_contract():
    """The one preregistered task010 method/rule pair; not a training label."""
    value = {"schema_version": CONTRACT_SCHEMA, "release_method": RELEASE_V2,
             "calibration_rule": CALIBRATION_V2, "legacy_release_method": RELEASE_V1,
             "clearance_margin_m": 0.002, "axes": ["x", "y", "z"],
             "supported_geom_types": [6, 7], "confirmation_steps": 4, "timely_steps": 24,
             "thresholds": [i / 20 for i in range(1, 20)] + [0.99],
             "training_label_contract": {"version": "current-state-passive-hold-v1", "confirmation_steps": 4,
                 "future_task_actions_allowed": False, "unknown_is_negative": False},
             "training_labels_changed": False, "physics_identity_changed": False}
    value["contract_sha256"] = canonical_hash(value)
    return value


def validate_evaluation_contract(value):
    if not isinstance(value, dict) or canonical_hash(value) != canonical_hash(evaluation_contract()):
        raise ValueError("unsupported/mismatched task010 evaluation method or calibration rule")
    return deepcopy(value)


def optional_contract(value):
    return None if value is None else validate_evaluation_contract(value)


def result_contract(result, expected=None):
    """Dispatch by explicit schema; never infer a new method from extra fields."""
    version = result.get("schema_version")
    if version == RESULT_SCHEMA_V2:
        contract = validate_evaluation_contract(result.get("evaluation_contract"))
        if expected is not None and contract != validate_evaluation_contract(expected):
            raise ValueError("result evaluation contract differs from its bound run")
        return contract
    if version != "remaining-finish-episode-v1" or "evaluation_contract" in result or "measurement_static" in result:
        raise ValueError("mixed/unsupported FINISH episode evaluation schema; legacy STOP is not FINISH")
    if expected is not None:
        raise ValueError("legacy result cannot be interpreted under task010 evaluation")
    return None


def budget_plan():
    return {"schema_version": "remaining-finish-budget-v2", "protocol_version": "remaining-finish-v1",
            "revision": "task010", "evaluation_contract": evaluation_contract(),
            "simulation_created": False, "weights_loaded": False,
            "previous_validation_shadow": 5, "validation_shadow": 5, "normal_active": 10,
            "remain_active": 15, "remain_shadow": 0, "rollouts": 35, "remaining_rollouts": 30,
            "horizon": 520, "retention_steps": 150, "chunk": 8, "maximum_physical_steps": 23450,
            "remaining_maximum_physical_steps": 20100,
            "notice": "Post-pilot versioned revision: 5 old exploratory + 5 new calibration + 10 independent normal + 15 Remain. Audit/features/parity and task009 replay separate. No automatic extra jobs or retraining."}
