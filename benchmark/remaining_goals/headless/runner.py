"""Original-policy rollout; goal confirmation is an evaluator-side endpoint."""
from copy import deepcopy
import math

from ..runner import _observation, _actions
from ..pilot_evidence import observation_sha256
from .schema import (PROTOCOL, RESULT_SCHEMA, EVENTS, canonical_hash, integer,
                     validate_evaluator_state, analyze_trace)


def run_episode(env, policy, episode, *, horizon=520, confirmation_steps=4,
                max_chunk_steps=8, recorder=None, evidence=None, identity=None):
    integer(horizon, "horizon", 1)
    integer(max_chunk_steps, "max_chunk_steps", 1)
    if horizon > 520 or confirmation_steps != 4 or type(confirmation_steps) is not int or max_chunk_steps > 8:
        raise ValueError("task011 fixes H<=520/K4/chunk<=8; smaller H is CPU-fixture only")
    if episode.get("initial_mask") != [True, False] or any(type(x) is not bool for x in episode["initial_mask"]):
        raise ValueError("headless task011 requires source mask10")
    if identity is None and evidence is not None:
        identity = evidence.identity
    if evidence is not None and identity != evidence.identity:
        raise ValueError("runner/evidence identities differ")
    result = {key: deepcopy(episode.get(key)) for key in ("episode_id", "task_id", "suite", "instruction", "seed",
        "initial_state_index", "initial_mask", "state_sha256", "model_xml_sha256", "bddl_sha256")}
    if "task_name" in episode:
        result["task_name"] = deepcopy(episode["task_name"])
    result.update(schema_version=RESULT_SCHEMA, protocol_version=PROTOCOL,
        configuration={"horizon": horizon, "confirmation_steps": 4, "max_chunk_steps": max_chunk_steps},
        identity_sha256=canonical_hash(identity) if identity is not None else None,
        status="runtime_error", exit_reason="technical_error", n_steps=0, policy_queries=0,
        queries=[], executed_actions=[], trace=[], error=None, error_phase=None, interrupted=False,
        measurement_static=None, initial_observation_sha256=None)
    if identity is not None and "model_identity" in identity:
        result["model_identity"] = deepcopy(identity["model_identity"])
    if identity is not None and "source_acceptance" in identity:
        result["source_acceptance"] = deepcopy(identity["source_acceptance"])
    phase = "evidence_begin"
    event_counts, events, streak = {}, [], 0
    regression, length, previous, inventory = False, 0., None, None

    def record(step, raw, event=None):
        nonlocal streak, regression, length, previous, inventory
        # Obtain only the existing returned observation. No render/update/step.
        observation = _observation(raw)
        if recorder is not None:
            recorder.capture(observation, step=step)
        facts = validate_evaluator_state(env.evaluator_state())
        from .environment import validate_evaluator_evidence
        validate_evaluator_evidence(facts, result["measurement_static"])
        current_inventory = {"tcp": {key: facts["tcp"][key] for key in ("site_id", "site_name", "frame")},
            "roles": {name: obj["role"] for name, obj in facts["objects"].items()},
            "candidates": {key: sorted(facts["event_candidates"][key]) for key in EVENTS}}
        if inventory is not None and inventory != current_inventory:
            raise ValueError("TCP site or event object inventory changed")
        inventory = current_inventory
        position = facts["tcp"]["position"]
        increment = 0. if previous is None else math.dist(position, previous)
        length += increment
        previous = position
        regression = regression or not facts["goals"][0]
        streak = streak + 1 if all(facts["goals"]) and facts["released"] is True else 0
        for kind in EVENTS:
            for name, candidate in facts["event_candidates"][kind].items():
                key = (kind, name)
                event_counts[key] = event_counts.get(key, 0) + 1 if candidate is True else 0
                if event_counts[key] == 5 and not any(x["event"] == kind and x["object"] == name for x in events):
                    events.append({"event": kind, "object": name, "start_step": step - 4, "confirmation_step": step})
        provenance = {"action": None, "query_sequence": None, "chunk_index": None} if event is None else {
            key: deepcopy(event[key]) for key in ("action", "query_sequence", "chunk_index")}
        result["trace"].append({"step": step, **facts, **provenance, "path_increment_m": increment,
            "path_length_m": length, "completion_streak": streak, "goal_regression": regression,
            "confirmed_events": deepcopy(events)})
        return observation

    try:
        if evidence is not None:
            evidence.begin_episode(episode)
        phase = "policy_reset"
        policy.reset()
        phase = "environment_reset"
        raw = env.reset(deepcopy(episode))
        observation = _observation(raw)
        result["initial_observation_sha256"] = observation_sha256(observation)
        phase = "evidence_initial"
        if evidence is not None:
            evidence.capture_initial(observation)
        phase = "measurement_static"
        result["measurement_static"] = deepcopy(env.measurement_static())
        canonical_hash(result["measurement_static"])
        from .environment import validate_measurement_static
        validate_measurement_static(result["measurement_static"], episode=episode)
        phase = "evaluator_state"
        observation = record(0, observation)
        if result["trace"][0]["goals"] != [True, False]:
            result.update(status="invalid_initial_state", exit_reason="invalid_initial_state", error="actual initial goals differ from mask10", error_phase="initial_mask")
        else:
            while result["n_steps"] < horizon:
                sequence = len(result["queries"]) + 1
                phase = "evidence_query"
                if evidence is not None:
                    evidence.capture_query_input(observation, sequence=sequence, step=result["n_steps"])
                query = {"sequence": sequence, "observation_step": result["n_steps"],
                    "observation_sha256": observation_sha256(observation), "status": "error",
                    "returned_chunk_length": None, "accepted_chunk_length": 0,
                    "accepted_actions": [], "executed_steps": []}
                result["queries"].append(query)
                result["policy_queries"] += 1
                phase = "policy_predict"
                prediction = policy.predict(deepcopy(observation), episode["instruction"])
                phase = "policy_action_validation"
                if prediction is None:
                    query["status"] = "stop"
                    raise ValueError("unexpected model STOP is a technical error, never goal confirmation")
                query["status"] = "invalid"
                actions = _actions(prediction)
                accepted = actions[:max_chunk_steps]
                query.update(status="actions", returned_chunk_length=len(actions), accepted_chunk_length=len(accepted),
                             accepted_actions=accepted.tolist())
                for offset, candidate in enumerate(accepted):
                    phase = "policy_step"
                    action = candidate.copy()
                    raw = env.step(action)
                    step = result["n_steps"] + 1
                    result["n_steps"] = step
                    event = {"step": step, "query_sequence": sequence, "chunk_index": offset, "action": candidate.tolist()}
                    result["executed_actions"].append(event)
                    query["executed_steps"].append(step)
                    if action.dtype != candidate.dtype or action.tobytes() != candidate.tobytes():
                        raise ValueError("environment mutated the original policy action")
                    phase = "evaluator_state"
                    observation = record(step, raw, event)
                    if streak >= 5 or step == horizon:
                        break
                if streak >= 5:
                    result.update(status="completed", exit_reason="goal_confirmed")
                    break
                if result["n_steps"] == horizon:
                    result.update(status="completed", exit_reason="horizon")
                    break
    except BaseException as error:
        result.update(status="runtime_error", exit_reason="technical_error", error=f"{type(error).__name__}: {error}",
                      error_phase=phase, interrupted=isinstance(error, (KeyboardInterrupt, SystemExit)))
    finally:
        result.update({key: value for key, value in analyze_trace(result["trace"]).items() if key != "frames"})
        if recorder is not None:
            try:
                video = recorder.close()
                if not isinstance(video, dict):
                    raise ValueError("video close report must be an object")
                canonical_hash(video)
                result["video"] = video
                if video.get("status") != "saved":
                    raise ValueError("required headless video was not saved")
            except BaseException as error:
                result["video"] = {"status": "video_error", "error": f"{type(error).__name__}: {error}"}
                if result["status"] != "runtime_error":
                    result.update(status="runtime_error", exit_reason="technical_error", error=result["video"]["error"], error_phase="video_close")
                result["interrupted"] |= isinstance(error, (KeyboardInterrupt, SystemExit))
        if evidence is not None:
            try:
                if str(result.get("error_phase", "")).startswith("evidence"):
                    result["execution_evidence"] = evidence.failure_reference(RuntimeError(result["error"]))
                else:
                    result["execution_evidence"] = evidence.finish(result)
            except BaseException as error:
                result.update(status="runtime_error", exit_reason="technical_error", error=f"{type(error).__name__}: {error}", error_phase="evidence_finish")
                result["interrupted"] |= isinstance(error, (KeyboardInterrupt, SystemExit))
                result["execution_evidence"] = evidence.failure_reference(error)
    return result
