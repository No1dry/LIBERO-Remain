"""FINISH-v1 rollout: decision-budget exit followed by real physical hold."""
from __future__ import annotations

from copy import deepcopy
from time import perf_counter

import numpy as np

from ..pilot_evidence import observation_sha256
from ..runner import _observation, _actions
from .schema import (PROTOCOL, RESULT_SCHEMA, integer, input_sha256, json_bytes,
                     validate_evaluator_state, validate_policy_result)


def run_finish_episode(env, policy, episode, *, mode="active", horizon=520,
                       retention_steps=150, max_chunk_steps=8, recorder=None, evidence=None,
                       evaluation_contract=None, expected_threshold=None):
    """Run all masks under the same H budget; FINISH and timeout both hold W.

    Only raw whitelisted observations and the original instruction reach the
    policy. Evaluator truth is sampled after physical steps, never used to
    permit, suppress or insert FINISH. Caller owns environment/policy lifetime.
    Optional video/evidence failures are technical errors in this new protocol.
    """
    started = perf_counter()
    from .evaluation import optional_contract, RESULT_SCHEMA_V2
    contract = optional_contract(evaluation_contract)
    result = {key: deepcopy(episode.get(key)) for key in (
        "episode_id", "task_id", "suite", "task_name", "instruction", "initial_mask", "seed", "state_sha256")}
    result.update(schema_version=RESULT_SCHEMA, protocol_version=PROTOCOL, mode=mode,
                  configuration={"horizon": horizon, "retention_steps": retention_steps, "max_chunk_steps": max_chunk_steps},
                  status="runtime_error", error=None, error_phase=None, exit_reason=None,
                  finish_step=None, timeout_step=None, n_steps=0, policy_queries=0,
                  hold_contract=None, trace=[], queries=[], executed_actions=[])
    if contract is not None:
        result.update(schema_version=RESULT_SCHEMA_V2, evaluation_contract=contract, measurement_static=None,
                      model_xml_sha256=episode.get("model_xml_sha256"))
    phase, pending = "validate_episode", None

    def checkpoint():
        if evidence is not None:
            evidence.record(deepcopy(result))

    def capture(raw, step):
        if recorder is not None:
            recorder.capture(deepcopy(raw), step=step)

    def snapshot(action, kind, cause=None, sequence=None, index=None):
        truth = validate_evaluator_state(env.evaluator_state(), len(episode["initial_mask"]),
            **({"evaluation_contract": contract, "measurement_static": result["measurement_static"]} if contract is not None else {}))
        # Evaluator extras cannot replace the control ledger's authoritative fields.
        row = {**truth, "step": result["n_steps"], "action": deepcopy(action), "action_kind": kind,
               "hold_cause": cause, "query_sequence": sequence, "chunk_index": index}
        result["trace"].append(row)
        return truth

    def apply(action, kind, *, cause=None, sequence=None, index=None):
        nonlocal phase
        phase = "hold_step" if kind == "hold" else "policy_step"
        raw = env.step(action.copy())
        result["n_steps"] += 1
        result["executed_actions"].append({"step": result["n_steps"], "action": action.tolist(),
            "action_kind": kind, "hold_cause": cause, "query_sequence": sequence, "chunk_index": index})
        if kind == "policy":
            result["queries"][-1]["executed_steps"].append(result["n_steps"])
        # Preserve already executed actions even if video/evaluator/observation fails.
        phase = "video_capture"
        capture(raw, result["n_steps"])
        phase = "evaluator_state"
        snapshot(action.tolist(), kind, cause, sequence, index)
        phase = "observation"
        observation = _observation(raw)
        phase = "evidence_checkpoint"
        checkpoint()
        return observation

    try:
        horizon = integer(horizon, "horizon")
        retention_steps = integer(retention_steps, "retention_steps")
        max_chunk_steps = integer(max_chunk_steps, "max_chunk_steps", 1, 8)
        if mode not in {"active", "shadow"}:
            raise ValueError("FINISH mode must be active or shadow")
        initial = episode["initial_mask"]
        if not isinstance(initial, list) or not initial or any(type(value) is not bool for value in initial):
            raise ValueError("initial_mask must be a nonempty boolean list")
        instruction = episode["instruction"]
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("FINISH requires the unchanged original instruction")
        for name in ("reset", "step", "evaluator_state", "begin_hold", "hold_action"):
            if not callable(getattr(env, name, None)):
                raise ValueError(f"FINISH environment lacks explicit {name} contract")
        if evidence is not None:
            phase = "evidence_begin"
            evidence.begin_episode(deepcopy(episode), mode=mode, configuration=deepcopy(result["configuration"]))
        phase = "env_reset"
        raw = env.reset(deepcopy(episode))
        if contract is not None:
            phase = "measurement_static"
            from .release_geometry import validate_measurement_static
            result["measurement_static"] = deepcopy(env.measurement_static())
            validate_measurement_static(result["measurement_static"])
            if result["measurement_static"]["compiled_model_xml_sha256"] != result["model_xml_sha256"]:
                raise ValueError("measurement static XML differs from the frozen source episode")
            json_bytes(result["measurement_static"])
        phase = "video_capture"
        capture(raw, 0)
        phase = "observation"
        observation = _observation(raw)
        if evidence is not None:
            phase = "evidence_initial"
            evidence.capture_initial(deepcopy(observation))
        phase = "initial_evaluator_state"
        truth = snapshot(None, "initial")
        if truth["goals"] != initial:
            raise ValueError("actual initial goal mask differs from the source episode")
        phase = "policy_reset"
        policy.reset()
        fixed_head, fixed_threshold = None, None
        while True:
            sequence = result["policy_queries"] + 1
            pending = {"sequence": sequence, "observation_step": result["n_steps"],
                       "observation_sha256": observation_sha256(observation), "status": "error",
                       "error": "policy query did not return a validated FINISH envelope", "executed_steps": []}
            # Increment only at the real predict boundary, not for evidence work.
            phase = "policy_predict"
            result["policy_queries"] += 1
            result["queries"].append(pending)
            raw_prediction = policy.predict(observation, instruction)
            phase = "validate_policy_result"
            prediction = validate_policy_result(raw_prediction)
            if expected_threshold is not None and prediction["threshold"] != expected_threshold:
                raise ValueError("policy threshold differs from the frozen evaluation plan")
            if fixed_head is None:
                fixed_head, fixed_threshold = prediction["head_identity"], prediction["threshold"]
            if prediction["head_identity"] != fixed_head or prediction["threshold"] != fixed_threshold:
                raise ValueError("head artifact or threshold changed within an episode")
            at_deadline = result["n_steps"] == horizon
            applied = ("finish" if mode == "active" and prediction["head_decision"] == "finish"
                       else "timeout" if at_deadline else "continue")
            pending.update({key: deepcopy(prediction[key]) for key in
                            ("logit", "p", "threshold", "head_decision", "head_identity")})
            pending.update(status="valid", error=None, applied_decision=applied,
                           candidate_actions=prediction["candidate_actions"].tolist(),
                           accepted_chunk_length=0, accepted_actions=[], input_evidence=None,
                           input_sha256=input_sha256(prediction["input_evidence"]))
            if applied != "continue":
                result["exit_reason"] = applied
                result["finish_step" if applied == "finish" else "timeout_step"] = result["n_steps"]
            if evidence is not None:
                phase = "evidence_query"
                pending["input_evidence"] = evidence.capture_query(sequence, deepcopy(prediction["input_evidence"]),
                                                                    deepcopy(prediction["head_identity"]))
            if applied != "continue":
                phase = "evidence_checkpoint"
                checkpoint()
                break
            count = min(max_chunk_steps, horizon - result["n_steps"])
            actions = prediction["candidate_actions"][:count].copy()
            pending.update(accepted_chunk_length=count, accepted_actions=actions.tolist())
            phase = "evidence_checkpoint"
            checkpoint()
            for index, action in enumerate(actions):
                observation = apply(action, "policy", sequence=sequence, index=index)
            # The next query is allowed only after this accepted prefix is exhausted.
        phase = "begin_hold"
        hold_contract = env.begin_hold()
        if not isinstance(hold_contract, dict) or not hold_contract:
            raise ValueError("begin_hold must declare its explicit controller contract")
        json_bytes(hold_contract)
        result["hold_contract"] = deepcopy(hold_contract)
        for _ in range(retention_steps):
            phase = "hold_action"
            action = _actions(env.hold_action(), hold=True)
            observation = apply(action, "hold", cause=result["exit_reason"])
        result["status"] = "completed"
    except (Exception, KeyboardInterrupt, SystemExit) as error:
        message = f"{type(error).__name__}: {error}"
        result.update(status="runtime_error", error=message, error_phase=phase)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            result["interrupted"] = True
        if pending is not None and pending["status"] == "error":
            pending["error"] = message
    finally:
        for row in result["queries"]:
            steps = row["executed_steps"]
            row["execution_interval"] = [steps[0], steps[-1]] if steps else None
            row["executed_chunk_length"] = len(steps)
            row["unexecuted_accepted_actions"] = row.get("accepted_chunk_length", 0) - len(steps)
        if recorder is not None:
            try:
                video = recorder.close()
                if not isinstance(video, dict):
                    raise TypeError("video close must return a dictionary")
                json_bytes(video)
                result["video"] = video
                if video.get("status") != "saved":
                    raise RuntimeError(f"required FINISH video is not saved: {video.get('status')}")
            except Exception as error:
                if "video" not in result:
                    result["video"] = {"status": "video_error", "path": None, "error": str(error)}
                if result["status"] == "completed":
                    result.update(status="runtime_error", error=f"{type(error).__name__}: {error}", error_phase="video_finalize")
                else:
                    result["video_error"] = f"{type(error).__name__}: {error}"
        if evidence is not None:
            try:
                result["finish_evidence"] = evidence.finish(deepcopy(result))
            except Exception as error:
                result["prior_execution_status"] = {key: result.get(key) for key in ("status", "error", "error_phase")}
                result.update(status="runtime_error", error=f"{type(error).__name__}: {error}", error_phase="evidence_finalize")
                try:
                    result["finish_evidence"] = evidence.failure_reference(error)
                except Exception as reference_error:
                    result["finish_evidence"] = {"schema_version": "remaining-finish-evidence-v1",
                        "status": "evidence_error", "error": f"{type(reference_error).__name__}: {reference_error}"}
        result["elapsed_seconds"] = perf_counter() - started
    return result
