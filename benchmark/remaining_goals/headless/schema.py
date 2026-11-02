"""Strict, offline-recomputable task011 endpoint and event records."""
from copy import deepcopy
import hashlib
import json
import math
import re

from .protocols import (get_protocol, protocol_for_result, LEGACY_PROTOCOL, NORMAL00_PROTOCOL,
                        NORMAL00_VERSION, NORMAL00_RESULT_SCHEMA)

PROTOCOL = "remaining-headless-goal-endpoint-v1"
RESULT_SCHEMA = "remaining-headless-episode-v1"
EVENTS = ("wrong_grasp", "wrong_placement", "table_drop")
ROLES = {"target", "support", "container", "fixture", "distractor"}
HASH = re.compile(r"[0-9a-f]{64}\Z")
FACT_FIELDS = ("goals", "released", "tcp", "objects", "event_candidates", "event_evidence")
NINE_FACT_FIELDS = ("invariant_values", "official_goal_values", "official_success", "required_open_values")


def trace_facts(row, descriptor):
    fields = FACT_FIELDS + (NINE_FACT_FIELDS if descriptor.nine_semantics else ())
    return {key: row[key] for key in fields}


def initial_matches(facts, descriptor):
    valid = tuple(facts["goals"]) == descriptor.initial_mask
    if descriptor.nine_semantics:
        from ..nine_catalog import initial_constraints_match
        valid = valid and initial_constraints_match(facts)
    return valid


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def vector(value, name, size=3):
    if (not isinstance(value, list) or len(value) != size or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError(f"{name} requires {size} finite coordinates")
    return [float(x) for x in value]


def _boolean(value, name):
    if value is not None and type(value) is not bool:
        raise ValueError(f"{name} must be boolean or null")
    return value


def validate_evaluator_state(value):
    required = set(FACT_FIELDS)
    if not isinstance(value, dict) or set(value) not in (required, required | set(NINE_FACT_FIELDS)):
        raise ValueError("headless evaluator requires explicit legacy or nine-task fact fields")
    if "official_success" in value:
        if type(value["official_success"]) is not bool:
            raise ValueError("official success must be boolean")
        for key in ("invariant_values", "official_goal_values", "required_open_values"):
            if not isinstance(value[key], list) or any(type(x) is not bool for x in value[key]):
                raise ValueError("nine-task predicate facts must be boolean lists")
    canonical_hash(value)
    if not isinstance(value["goals"], list) or len(value["goals"]) != 2 or any(type(x) is not bool for x in value["goals"]):
        raise ValueError("exactly two official boolean goals are required")
    _boolean(value["released"], "released")
    tcp = value["tcp"]
    if (not isinstance(tcp, dict) or set(tcp) != {"site_id", "site_name", "frame", "position"}
            or tcp["frame"] != "world" or not isinstance(tcp["site_name"], str) or not tcp["site_name"]):
        raise ValueError("TCP requires the actual named world-coordinate site")
    integer(tcp["site_id"], "TCP site ID")
    vector(tcp["position"], "TCP position")
    objects = value["objects"]
    if not isinstance(objects, dict):
        raise ValueError("object inventory must be explicit")
    for name, obj in objects.items():
        if (not isinstance(name, str) or not name or not isinstance(obj, dict) or
                not {"role", "position", "released", "release_evidence"}.issubset(obj) or obj["role"] not in ROLES
                or not isinstance(obj["release_evidence"], dict)):
            raise ValueError("invalid named physical object/role evidence")
        if obj["position"] is not None:
            vector(obj["position"], "object position")
        _boolean(obj["released"], "object release")
    if any(not isinstance(value[k], dict) or set(value[k]) != set(EVENTS) for k in ("event_candidates", "event_evidence")):
        raise ValueError("all three event channels must be explicit")
    for kind in EVENTS:
        candidates, evidence = value["event_candidates"][kind], value["event_evidence"][kind]
        if not isinstance(candidates, dict) or not isinstance(evidence, dict) or set(candidates) != set(evidence):
            raise ValueError("event candidates and object evidence differ")
        for name, candidate in candidates.items():
            allowed = {"distractor", "support", "container"} if kind == "table_drop" else {"distractor"}
            if name not in objects or objects[name]["role"] not in allowed:
                raise ValueError("event uses an unsupported object role")
            _boolean(candidate, "event candidate")
            if not isinstance(evidence[name], dict) or not evidence[name]:
                raise ValueError("every event candidate requires physical evidence, including unknown")
    return deepcopy(value)


def analyze_trace(trace, *, confirmation_steps=4, protocol=LEGACY_PROTOCOL, task_semantics=None):
    """Recompute facts, sticky events and TCP path; unknown never means false."""
    integer(confirmation_steps, "confirmation_steps", 1)
    descriptor = get_protocol(protocol)
    if descriptor.nine_semantics:
        from ..nine_catalog import validate_task_semantics, validate_goal_facts
        validate_task_semantics(task_semantics)
    preservation = bool(descriptor.preserved_goal_indices)
    streak = 0
    confirmed = begin = None
    counters, events, unknown = {}, [], []
    regression, length, previous, inventory = False if preservation else None, 0., None, None
    derived = []
    invariant_regression = False if preservation and descriptor.nine_semantics else None
    for step, row in enumerate(trace):
        if row.get("step") != step or type(row.get("step")) is not int:
            raise ValueError("physical trace must be contiguous from step zero")
        facts = validate_evaluator_state(trace_facts(row, descriptor))
        if descriptor.nine_semantics:
            validate_goal_facts(facts, task_semantics)
        identity = {"tcp": {k: facts["tcp"][k] for k in ("site_id", "site_name", "frame")},
                    "roles": {name: obj["role"] for name, obj in facts["objects"].items()},
                    "candidates": {key: sorted(facts["event_candidates"][key]) for key in EVENTS}}
        if inventory is None:
            inventory = identity
        elif inventory != identity:
            raise ValueError("TCP site or object/event inventory changed during the episode")
        position = vector(facts["tcp"]["position"], "TCP position")
        increment = 0. if previous is None else math.dist(position, previous)
        length += increment
        previous = position
        if preservation:
            regression = regression or any(not facts["goals"][index] for index in descriptor.preserved_goal_indices)
            if descriptor.nine_semantics:
                invariant_regression = invariant_regression or not all(facts["invariant_values"])
                regression = regression or invariant_regression
        official = facts["official_success"] if descriptor.nine_semantics else all(facts["goals"])
        complete = official and (descriptor.official_endpoint or facts["released"] is True)
        streak = streak + 1 if complete else 0
        if confirmed is None and streak >= (1 if descriptor.official_endpoint else confirmation_steps + 1):
            confirmed, begin = step, step if descriptor.official_endpoint else step - confirmation_steps
        for kind in EVENTS:
            for name, candidate in facts["event_candidates"][kind].items():
                key = (kind, name)
                counters[key] = counters.get(key, 0) + 1 if candidate is True else 0
                if candidate is None:
                    unknown.append({"step": step, "event": kind, "object": name})
                if counters[key] == confirmation_steps + 1:
                    if not any(e["event"] == kind and e["object"] == name for e in events):
                        events.append({"event": kind, "object": name, "start_step": step - confirmation_steps,
                                       "confirmation_step": step})
        derived.append({"path_increment_m": increment, "path_length_m": length,
                        "completion_streak": streak, "goal_regression": regression,
                        "confirmed_events": deepcopy(events)})
        if not preservation:
            derived[-1]["preservation_applicable"] = False
        if descriptor.nine_semantics:
            derived[-1]["invariant_regression"] = invariant_regression
    result = {"frames": derived, "path_length_m": length, "goal_completion_step": begin,
            "goal_confirmed_step": confirmed, "goal_regression": regression,
            "confirmed_events": events, "event_unknown": unknown,
            "release_unknown_steps": [row["step"] for row in trace if row["released"] is None],
            "official_goals_achieved": any(row["official_success"] if descriptor.nine_semantics else all(row["goals"]) for row in trace)}
    if descriptor.nine_semantics:
        result["invariant_regression"] = invariant_regression
    if not preservation:
        result["preservation_applicable"] = False
    return result


def _same(left, right):
    return canonical_hash(left) == canonical_hash(right)


def _validate_result(result, episode=None, identity=None, *, protocol=LEGACY_PROTOCOL):
    descriptor = get_protocol(protocol)
    if result.get("schema_version") != descriptor.result_schema or result.get("protocol_version") != descriptor.protocol_version:
        raise ValueError("not a headless task011 result; old protocols cannot be reinterpreted")
    canonical_hash(result)
    descriptor.validate_mask(result.get("initial_mask"))
    descriptor.validate_identity(result)
    descriptor.validate_identity(identity)
    if descriptor.nine_semantics:
        from ..nine_catalog import validate_task_semantics, validate_episode_semantics
        validate_task_semantics(result.get("task_semantics"), key=result["task_id"])
        if episode is not None:
            validate_episode_semantics(episode)
            if result["task_semantics"] != episode["task_semantics"]:
                raise ValueError("result task semantics differ from source")
        wanted_endpoint = "official_success_or_horizon" if descriptor.official_endpoint else "all_goals_release_five_observations_or_horizon"
        if result.get("endpoint_rule") != wanted_endpoint:
            raise ValueError("nine-task endpoint rule differs")
    for key in ("episode_id", "task_id", "suite", "instruction"):
        if not isinstance(result.get(key), str) or not result[key]:
            raise ValueError("missing source episode identity")
    for key in ("state_sha256", "model_xml_sha256", "bddl_sha256"):
        if not isinstance(result.get(key), str) or not HASH.fullmatch(result[key]):
            raise ValueError("missing physical source identity")
    if integer(result.get("initial_state_index"), "initial_state_index") > 9:
        raise ValueError("task011 sources are official indices zero through nine")
    integer(result.get("seed"), "source environment seed")
    if episode is not None:
        for key in ("episode_id", "task_id", "suite", "instruction", "initial_mask", "initial_state_index",
                    "state_sha256", "model_xml_sha256", "bddl_sha256", "seed"):
            if key not in episode or not _same(result.get(key), episode[key]):
                raise ValueError(f"result differs from source {key}")
        if "task_name" in episode and not _same(result.get("task_name"), episode["task_name"]):
            raise ValueError("result differs from source task_name")
    if identity is not None and result.get("identity_sha256") != canonical_hash(identity):
        raise ValueError("result belongs to a different run/model/track identity")
    if identity is not None and "model_identity" in identity and result.get("model_identity") != identity["model_identity"]:
        raise ValueError("result model/checkpoint/normalization identity differs")
    if identity is not None:
        for key in ("source_acceptance", "source_origin"):
            if key in identity and not _same(result.get(key), identity[key]):
                raise ValueError(f"result {key} differs from frozen identity")
    if result.get("measurement_static") is not None:
        from .environment import validate_measurement_static, validate_evaluator_evidence
        static_options = {} if protocol == LEGACY_PROTOCOL else {"protocol": protocol}
        validate_measurement_static(result["measurement_static"], episode=episode if episode is not None else result, **static_options)
        for row in result["trace"]:
            validate_evaluator_evidence(trace_facts(row, descriptor), result["measurement_static"])
    elif result["trace"] or result["status"] == "completed":
        raise ValueError("recorded headless facts require the frozen measurement source")
    configuration = result["configuration"]
    horizon = integer(configuration["horizon"], "horizon", 1)
    k = integer(configuration["confirmation_steps"], "confirmation_steps", 1)
    chunk = integer(configuration["max_chunk_steps"], "max_chunk_steps", 1)
    if horizon > 520 or k != 4 or chunk > 8:
        raise ValueError("headless H/K/chunk exceeds the fixed task011 contract")
    steps = integer(result["n_steps"], "n_steps")
    queries, actions, trace = result["queries"], result["executed_actions"], result["trace"]
    if not all(isinstance(x, list) for x in (queries, actions, trace)) or len(actions) != steps or steps > horizon:
        raise ValueError("action ledger count/budget differs")
    if integer(result["policy_queries"], "policy_queries") != len(queries) or len(trace) not in (steps, steps + 1):
        raise ValueError("query or observation count differs")
    if result["status"] not in {"completed", "runtime_error", "invalid_initial_state"}:
        raise ValueError("unsupported headless execution status")
    cursor = 1
    for seq, query in enumerate(queries, 1):
        if (query.get("sequence") != seq or type(query.get("sequence")) is not int or
                query.get("observation_step") != cursor - 1 or type(query.get("observation_step")) is not int or
                not HASH.fullmatch(query.get("observation_sha256", ""))):
            raise ValueError("query order or raw observation hash differs")
        executed = query["executed_steps"]
        if executed != list(range(cursor, cursor + len(executed))) or any(type(s) is not int for s in executed):
            raise ValueError("query execution is not a contiguous physical prefix")
        if query["status"] == "actions":
            returned = integer(query["returned_chunk_length"], "returned chunk", 1)
            if query["accepted_chunk_length"] != min(returned, chunk) or len(query["accepted_actions"]) != min(returned, chunk):
                raise ValueError("accepted action prefix differs from chunk limit")
            for action in query["accepted_actions"]:
                vector(action, "candidate action", 7)
            if len(executed) > min(returned, chunk) or seq < len(queries) and len(executed) != min(returned, chunk):
                raise ValueError("query occurred before exhausting its predecessor")
        elif query["status"] in {"stop", "error", "invalid"}:
            if executed or query["accepted_actions"] or query["accepted_chunk_length"] != 0 or seq != len(queries) or result["status"] == "completed":
                raise ValueError("STOP/error cannot execute or complete an episode")
        else:
            raise ValueError("unsupported query status")
        for offset, step in enumerate(executed):
            event = actions[step - 1]
            if event.get("step") != step or event.get("query_sequence") != seq or event.get("chunk_index") != offset:
                raise ValueError("action query/chunk association differs")
            vector(event["action"], "executed action", 7)
            if not _same(event["action"], query["accepted_actions"][offset]):
                raise ValueError("executed action differs from original accepted float64 values")
        cursor += len(executed)
    if cursor != steps + 1:
        raise ValueError("actions lack query provenance")
    for step, row in enumerate(trace):
        expected = {"action": None, "query_sequence": None, "chunk_index": None} if step == 0 else {
            key: actions[step - 1][key] for key in ("action", "query_sequence", "chunk_index")}
        if any(not _same(row.get(key), value) for key, value in expected.items()):
            raise ValueError("frame does not match its physical action")
    analysis = analyze_trace(trace, confirmation_steps=k, protocol=protocol, task_semantics=result.get("task_semantics"))
    if not descriptor.preserved_goal_indices and ("goal_regression" not in result or
            any("goal_regression" not in row for row in trace)):
        raise ValueError("normal00 preservation requires explicit null goal_regression")
    for row, derived in zip(trace, analysis["frames"]):
        if any(not _same(row.get(key), value) for key, value in derived.items()):
            raise ValueError("stored TCP path or sticky event summary does not recompute")
    for key in ("path_length_m", "goal_completion_step", "goal_confirmed_step", "goal_regression", "confirmed_events", "event_unknown", "release_unknown_steps", "official_goals_achieved"):
        if not _same(result.get(key), analysis[key]):
            raise ValueError(f"headless result {key} does not recompute")
    if descriptor.nine_semantics and not _same(result.get("invariant_regression"), analysis["invariant_regression"]):
        raise ValueError("invariant regression does not recompute")
    if not descriptor.preserved_goal_indices and result.get("preservation_applicable") is not False:
        raise ValueError("normal00 preservation must be explicitly inapplicable")
    if analysis["goal_confirmed_step"] is not None and analysis["goal_confirmed_step"] != steps:
        raise ValueError("actions continued after the first confirmed goal endpoint")
    if result["status"] == "completed":
        if len(trace) != steps + 1 or not trace or not initial_matches(trace[0], descriptor):
            raise ValueError("completed result lacks valid t0 or per-step observations")
        reason = ("official_success" if descriptor.official_endpoint else "goal_confirmed") if analysis["goal_confirmed_step"] is not None else "horizon"
        if result.get("exit_reason") != reason or reason == "horizon" and steps != horizon:
            raise ValueError("completion endpoint differs from H/K4 observations")
        if result.get("error") is not None:
            raise ValueError("completed result carries a technical error")
    elif result["status"] == "invalid_initial_state":
        if steps or queries or not trace or initial_matches(trace[0], descriptor) or result.get("exit_reason") != "invalid_initial_state":
            raise ValueError("invalid-initial report does not describe actual t0 mismatch")
    elif result.get("exit_reason") != "technical_error" or not result.get("error"):
        raise ValueError("runtime failure needs its actual error and technical endpoint")
    return {"verified": True, "protocol_version": descriptor.protocol_version, "path_observations": len(trace), "n_steps": steps,
            "path_complete": len(trace) == steps + 1, "path_length_m": analysis["path_length_m"]}


def validate_result(result, episode=None, identity=None):
    try:
        return _validate_result(result, episode, identity)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(f"malformed headless result: {error}") from error


def validate_normal00_result(result, episode=None, identity=None):
    return validate_protocol_result(result, episode, identity, protocol=NORMAL00_PROTOCOL)


def validate_protocol_result(result, episode=None, identity=None, *, protocol=None):
    try:
        descriptor = protocol_for_result(result) if protocol is None else get_protocol(protocol)
        return _validate_result(result, episode, identity, protocol=descriptor.key)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(f"malformed headless result: {error}") from error
