"""Pure CPU contracts for FINISH inputs, decisions and execution ledgers."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re

import numpy as np

from ..pilot_evidence import observation_sha256

PROTOCOL = "remaining-finish-v1"
RESULT_SCHEMA = "remaining-finish-episode-v1"
POLICY_SCHEMA = "remaining-finish-policy-v1"
INPUT_SCHEMA = "remaining-finish-input-v1"
FEATURE_VERSION = "oft-l1-action56-mean-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
TENSOR_KEYS = {"input_ids", "attention_mask", "pixel_values", "proprio"}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def integer(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _array(value, name):
    if not isinstance(value, np.ndarray) or value.dtype.kind not in "fiu" or not value.size or not np.isfinite(value).all():
        raise ValueError(f"{name} requires a nonempty finite numeric array")
    if value.nbytes > 24 * 1024 * 1024:
        raise ValueError(f"{name} is too large for the worker protocol")
    return value.copy(order="C")


def validate_input_evidence(value):
    """Validate actual forward inputs, including lossless BF16 byte views.

    BF16 is stored as uint16 bits; boolean tensors as uint8 0/1. Source dtype
    labels are part of the digest, not silently replaced with NumPy's dtype.
    """
    if not isinstance(value, dict) or set(value) != {"schema_version", "tensors", "tensor_dtypes", "crops"}:
        raise ValueError("FINISH input evidence has missing or unapproved fields")
    if value["schema_version"] != INPUT_SCHEMA:
        raise ValueError("unsupported FINISH input evidence version")
    tensors, labels, crops = value["tensors"], value["tensor_dtypes"], value["crops"]
    if (not isinstance(tensors, dict) or set(tensors) != TENSOR_KEYS
            or not isinstance(labels, dict) or set(labels) != TENSOR_KEYS
            or not isinstance(crops, dict) or set(crops) != {"agentview", "wrist"}):
        raise ValueError("FINISH inputs require exactly the four model tensors and two camera crops")
    output = {}
    for name, item in tensors.items():
        array = _array(item, name)
        label = labels[name]
        if not isinstance(label, str) or "." not in label:
            raise ValueError("tensor source dtype must be explicit")
        owner, dtype = label.split(".", 1)
        if owner not in {"torch", "numpy"}:
            raise ValueError("unsupported tensor dtype namespace")
        if dtype == "bfloat16":
            if owner != "torch" or array.dtype != np.dtype("uint16"):
                raise ValueError("BF16 inputs require original uint16 bits")
            if np.any((array & np.uint16(0x7F80)) == np.uint16(0x7F80)):
                raise ValueError("BF16 input has NaN or infinity")
        elif dtype == "bool":
            if array.dtype != np.dtype("uint8") or not np.isin(array, [0, 1]).all():
                raise ValueError("boolean inputs require uint8 zero/one storage")
        else:
            allowed = {"float16", "float32", "float64", "int8", "int16", "int32", "int64",
                       "uint8", "uint16", "uint32", "uint64"}
            if dtype not in allowed or array.dtype != np.dtype(dtype):
                raise ValueError("tensor source dtype does not match its bytes")
        output[name] = array
    ids, attention = output["input_ids"], output["attention_mask"]
    if ids.ndim != 2 or ids.shape[0] != 1 or ids.dtype.kind not in "iu" or attention.shape != ids.shape:
        raise ValueError("input_ids and attention_mask must describe the same one-input batch")
    if attention.dtype.kind not in "iu" or not np.isin(attention, [0, 1]).all():
        raise ValueError("attention_mask must be an integer/boolean mask")
    if output["proprio"].shape not in {(7,), (1, 7)} or output["pixel_values"].ndim not in {4, 5}:
        raise ValueError("unexpected OFT proprio/pixel tensor shape")
    if output["pixel_values"].shape[0] != 1:
        raise ValueError("FINISH requires one actual observation per query")
    images = {}
    for name, item in crops.items():
        array = _array(item, name)
        if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3:
            raise ValueError("actual camera crops must be uint8 HxWx3 RGB")
        images[name] = array
    return {"schema_version": INPUT_SCHEMA, "tensors": output, "tensor_dtypes": deepcopy(labels), "crops": images}


def input_sha256(value):
    value = validate_input_evidence(value)
    return digest({"schema_version": INPUT_SCHEMA, "tensor_dtypes": value["tensor_dtypes"],
                   "arrays_sha256": observation_sha256({"tensors": value["tensors"], "crops": value["crops"]})})


def validate_head_identity(value):
    if not isinstance(value, dict) or set(value) != {"artifact_sha256", "feature_version", "base_identity_sha256"}:
        raise ValueError("FINISH head identity is incomplete")
    if value["feature_version"] != FEATURE_VERSION:
        raise ValueError("unsupported FINISH feature version")
    for key in ("artifact_sha256", "base_identity_sha256"):
        if not isinstance(value[key], str) or not HASH.fullmatch(value[key]):
            raise ValueError(f"invalid head identity {key}")
    return deepcopy(value)


def validate_decision(value):
    logit, probability, threshold = (_number(value[key], key) for key in ("logit", "p", "threshold"))
    if not 0 <= probability <= 1 or not 0 < threshold < 1:
        raise ValueError("FINISH probability/threshold is out of range")
    sigmoid = 1 / (1 + math.exp(-logit)) if logit >= 0 else math.exp(logit) / (1 + math.exp(logit))
    if abs(sigmoid - probability) > 2e-6:
        raise ValueError("FINISH probability differs from the FP32 head logit")
    decision = "finish" if probability >= threshold else "continue"
    if value["head_decision"] != decision:
        raise ValueError("head_decision differs from the fixed threshold rule")
    return {"logit": logit, "p": probability, "threshold": threshold, "head_decision": decision,
            "head_identity": validate_head_identity(value["head_identity"])}


def validate_policy_result(value):
    keys = {"schema_version", "candidate_actions", "logit", "p", "threshold", "head_decision", "head_identity", "input_evidence"}
    if not isinstance(value, dict) or set(value) != keys or value["schema_version"] != POLICY_SCHEMA:
        raise ValueError("policy must return a supported FINISH envelope; None/legacy actions are not FINISH")
    actions = _array(value["candidate_actions"], "candidate_actions")
    if actions.shape != (8, 7):
        raise ValueError("FINISH OFT requires exactly eight decoded seven-dimensional candidate actions")
    return {"schema_version": POLICY_SCHEMA, "candidate_actions": actions.astype(np.float64),
            **validate_decision(value), "input_evidence": validate_input_evidence(value["input_evidence"])}


def validate_evaluator_state(value, goal_count):
    if not isinstance(value, dict) or not {"goals", "released", "objects"}.issubset(value):
        raise ValueError("evaluator_state requires goals, released and objects")
    output = deepcopy(value)
    goals = output["goals"]
    if not isinstance(goals, list) or len(goals) != goal_count or any(type(item) is not bool for item in goals):
        raise ValueError("evaluator goal truth must be a boolean list matching the source episode")
    if output["released"] is not None and type(output["released"]) is not bool:
        raise ValueError("released must be a boolean or unknown/null")
    if not isinstance(output["objects"], dict) or not output["objects"]:
        raise ValueError("evaluator object evidence must be a nonempty dictionary")
    for name, item in output["objects"].items():
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            raise ValueError("invalid evaluator object entry")
        if item.get("role") not in {"target", "container", "fixture", "distractor"}:
            raise ValueError("unknown evaluator object role")
        for key in ("in_basket", "released"):
            if key not in item or (item[key] is not None and type(item[key]) is not bool):
                raise ValueError(f"object {key} must be boolean or unknown/null")
        if not isinstance(item.get("release_evidence"), dict):
            raise ValueError("object release requires explicit physical evidence")
    json_bytes(output)
    return output


def _action(value):
    array = np.asarray(value)
    if array.shape != (7,) or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
        raise ValueError("ledger actions must be finite decoded seven-vectors")
    return array.astype(np.float64).tobytes()


def _validate_result(result, episode):
    if result.get("schema_version") != RESULT_SCHEMA or result.get("protocol_version") != PROTOCOL:
        raise ValueError("not a FINISH-v1 episode; legacy scores/STOP records cannot be mixed")
    mode, status = result["mode"], result["status"]
    if mode not in {"active", "shadow"} or status not in {"completed", "runtime_error"}:
        raise ValueError("invalid FINISH mode/status")
    config = result["configuration"]
    horizon = integer(config["horizon"], "horizon")
    retention = integer(config["retention_steps"], "retention_steps")
    chunk = integer(config["max_chunk_steps"], "max_chunk_steps", 1, 8)
    n_steps = integer(result["n_steps"], "n_steps")
    integer(result["policy_queries"], "policy_queries")
    for key in ("finish_step", "timeout_step"):
        if result.get(key) is not None:
            integer(result[key], key, 0, horizon)
    trace, queries, actions = result["trace"], result["queries"], result["executed_actions"]
    if not all(isinstance(table, list) for table in (trace, queries, actions)):
        raise ValueError("FINISH trace/query/action ledgers must be lists")
    if len(actions) != n_steps or len(queries) != result["policy_queries"] or len(trace) > n_steps + 1:
        raise ValueError("FINISH ledger counts disagree with execution")
    source = episode if episode is not None else result
    initial = source["initial_mask"]
    if not isinstance(initial, list) or not initial or any(type(item) is not bool for item in initial):
        raise ValueError("invalid source mask")
    if episode is not None:
        for key in ("episode_id", "instruction", "initial_mask"):
            if result.get(key) != episode[key]:
                raise ValueError("FINISH result belongs to a different source episode/instruction")
    for step, row in enumerate(trace):
        if type(row.get("step")) is not int or row["step"] != step:
            raise ValueError("FINISH trace must be a continuous prefix starting at zero")
        validate_evaluator_state({key: row[key] for key in ("goals", "released", "objects")}, len(initial))
        if step == 0:
            if row.get("action") is not None or row.get("action_kind") != "initial":
                raise ValueError("step zero is the pre-action state")
            if status == "completed" and row["goals"] != initial:
                raise ValueError("completed FINISH episode has the wrong initial goal mask")
        else:
            event = actions[step - 1]
            for key in ("action_kind", "hold_cause", "query_sequence", "chunk_index"):
                if row.get(key) != event.get(key):
                    raise ValueError("trace and physical action ledger differ")
            if _action(row["action"]) != _action(event["action"]):
                raise ValueError("trace action differs from the executed action")
    next_step, exit_reason, exit_step = 1, None, None
    head, threshold = None, None
    for sequence, row in enumerate(queries, 1):
        if (type(row.get("sequence")) is not int or row["sequence"] != sequence
                or type(row.get("observation_step")) is not int or row["observation_step"] != next_step - 1
                or row["observation_step"] > horizon or exit_reason is not None):
            raise ValueError("query is not at an exhausted queue/deadline boundary")
        if not isinstance(row.get("observation_sha256"), str) or not HASH.fullmatch(row["observation_sha256"]):
            raise ValueError("missing actual decision observation hash")
        if row.get("status") == "error":
            if status == "completed" or sequence != len(queries) or row.get("executed_steps"):
                raise ValueError("failed query cannot complete or execute a candidate")
            continue
        if row.get("status") != "valid":
            raise ValueError("unfinished query cannot be a finalized result")
        decision = validate_decision(row)
        if head is None:
            head, threshold = decision["head_identity"], decision["threshold"]
        if head != decision["head_identity"] or threshold != decision["threshold"]:
            raise ValueError("head identity or threshold changed during the episode")
        candidate = np.asarray(row["candidate_actions"])
        if candidate.shape != (8, 7) or candidate.dtype.kind not in "fiu" or not np.isfinite(candidate).all():
            raise ValueError("invalid candidate action evidence")
        applied = ("finish" if mode == "active" and decision["head_decision"] == "finish" else
                   "timeout" if row["observation_step"] == horizon else "continue")
        if row["applied_decision"] != applied:
            raise ValueError("applied decision violates active/shadow/deadline semantics")
        expected = min(chunk, horizon - row["observation_step"]) if applied == "continue" else 0
        accepted = integer(row["accepted_chunk_length"], "accepted_chunk_length")
        if accepted != expected and not (accepted == 0 and status == "runtime_error" and sequence == len(queries)):
            raise ValueError("accepted chunk does not respect the remaining decision budget")
        if len(row["accepted_actions"]) != accepted:
            raise ValueError("accepted action length differs")
        for i, action in enumerate(row["accepted_actions"]):
            if _action(action) != _action(candidate[i]):
                raise ValueError("accepted actions are not the unmodified candidate prefix")
        executed = row["executed_steps"]
        if (not isinstance(executed, list) or any(type(step) is not int for step in executed)
                or executed != list(range(next_step, next_step + len(executed))) or len(executed) > accepted):
            raise ValueError("invalid policy execution interval")
        if sequence < len(queries) and len(executed) != accepted:
            raise ValueError("query inserted before exhausting the preceding chunk")
        for index, step in enumerate(executed):
            event = actions[step - 1]
            if (event.get("action_kind") != "policy" or event.get("hold_cause") is not None
                    or event.get("query_sequence") != sequence or event.get("chunk_index") != index
                    or _action(event["action"]) != _action(candidate[index])):
                raise ValueError("candidate and actual policy execution mapping disagree")
        interval = [executed[0], executed[-1]] if executed else None
        if row["execution_interval"] != interval or row["executed_chunk_length"] != len(executed):
            raise ValueError("query execution summary differs")
        if row["unexecuted_accepted_actions"] != accepted - len(executed):
            raise ValueError("query truncation summary differs")
        if not isinstance(row.get("input_sha256"), str) or not HASH.fullmatch(row["input_sha256"]):
            raise ValueError("missing actual processed-input digest")
        next_step += len(executed)
        if applied != "continue":
            exit_reason, exit_step = applied, row["observation_step"]
    if result.get("exit_reason") != exit_reason:
        raise ValueError("reported exit reason differs from actual query decisions")
    if result.get("finish_step") != (exit_step if exit_reason == "finish" else None):
        raise ValueError("FINISH boundary differs from the pre-action decision state")
    if result.get("timeout_step") != (horizon if exit_reason == "timeout" else None):
        raise ValueError("budget timeout cannot be relabeled as FINISH")
    holds = actions[next_step - 1:]
    if holds and (exit_reason is None or not isinstance(result.get("hold_contract"), dict) or not result["hold_contract"]):
        raise ValueError("physical hold requires an explicit exit and controller contract")
    if len(holds) > retention:
        raise ValueError("hold exceeds the retention budget")
    for event in holds:
        if (event.get("action_kind") != "hold" or event.get("hold_cause") != exit_reason
                or event.get("query_sequence") is not None or event.get("chunk_index") is not None):
            raise ValueError("hold cause/ownership differs; timeout is not a policy STOP query")
    for step, event in enumerate(actions, 1):
        if type(event.get("step")) is not int or event["step"] != step:
            raise ValueError("physical action steps must be contiguous")
        _action(event["action"])
    if status == "completed" and (exit_reason is None or len(holds) != retention or len(trace) != n_steps + 1):
        raise ValueError("completed FINISH episode lacks its complete physical hold/trace")
    return {"protocol_version": PROTOCOL, "verified": True, "mode": mode, "policy_queries": len(queries), "n_steps": n_steps}


def validate_finish_result(result, episode=None):
    """Recompute deadline/queue/physical-ledger consistency, never task success."""
    try:
        return _validate_result(result, episode)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(f"malformed FINISH result: {error}") from error
