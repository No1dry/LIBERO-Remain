"""Roll out a remaining-goals episode without privileged policy inputs.

The environment owns state restoration, decoded action application, and a
validated hold controller. The policy receives only camera/proprioceptive
observations and the original instruction. Goal truth is evaluator-only.
``completed`` means that the scheduled rollout finished, not task success;
metrics must separately check the horizon and retention window.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
import json
from numbers import Integral
from time import perf_counter
from typing import Any

import numpy as np


_IMAGE_KEYS = {"image", "wrist_image", "agentview_image", "robot0_eye_in_hand_image"}
_PROPRIO_KEYS = {
    "proprio", "state", "robot0_eef_pos", "robot0_eef_quat",
    "robot0_gripper_qpos", "robot0_joint_pos", "robot0_joint_vel",
}


def _real_array(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype.kind not in "iuf" or not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite real numbers")
    return array


def _observation(value: Any) -> dict[str, Any]:
    """Reject unexpected/privileged fields instead of silently forwarding them.

    ``state`` is a compatibility name for a one-dimensional proprioception
    vector, never a simulator state or a dictionary. Environment adapters are
    responsible for the physical meaning of numeric vectors and camera pixels.
    Copies prevent policy preprocessing from mutating environment buffers.
    """
    if not isinstance(value, dict) or not value:
        raise ValueError("observation must be a nonempty dictionary")
    output: dict[str, Any] = {}
    for key, item in value.items():
        if key == "images":
            if not isinstance(item, dict) or not item:
                raise ValueError("observation.images must be a nonempty camera dictionary")
            images = {}
            for camera, pixels in item.items():
                if not isinstance(camera, str) or not isinstance(pixels, np.ndarray):
                    raise ValueError("observation.images requires string names and image arrays")
                image = _real_array(pixels, f"image {camera}")
                if image.ndim not in (2, 3) or not image.size:
                    raise ValueError(f"image {camera} must be a nonempty 2D or 3D array")
                images[camera] = image.copy()
            output[key] = images
        elif key in _IMAGE_KEYS:
            if not isinstance(item, np.ndarray):
                raise ValueError(f"{key} must be an image array")
            image = _real_array(item, key)
            if image.ndim not in (2, 3) or not image.size:
                raise ValueError(f"{key} must be a nonempty 2D or 3D array")
            output[key] = image.copy()
        elif key in _PROPRIO_KEYS:
            proprio = _real_array(item, key)
            if proprio.ndim != 1 or not proprio.size:
                raise ValueError(f"{key} must be a nonempty 1D proprioception vector")
            output[key] = proprio.copy()
        else:
            raise ValueError(f"observation field is not permitted: {key!r}")
    return output


def _goal_values(value: Any, count: int, name: str) -> list[bool]:
    if not isinstance(value, (list, tuple, np.ndarray)):
        raise ValueError(f"{name} must be a boolean sequence")
    array = np.asarray(value)
    if array.ndim != 1 or len(array) != count or array.dtype.kind != "b":
        raise ValueError(f"{name} must contain exactly {count} booleans")
    return [bool(item) for item in array]


def _step_count(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    if value < (1 if positive else 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return int(value)


def _actions(value: Any, *, hold: bool = False) -> np.ndarray:
    array = _real_array(value, "hold action" if hold else "policy action")
    if hold:
        if array.shape != (7,):
            raise ValueError(f"hold_action must return shape (7,), got {array.shape}")
        return array.astype(np.float64, copy=True)
    if array.shape == (7,):
        array = array[None, :]
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != 7:
        raise ValueError(f"policy action must have shape (7,) or (T, 7), got {array.shape}")
    return array.astype(np.float64, copy=True)


def run_episode(env: Any, policy: Any, episode: dict[str, Any], *,
                max_chunk_steps: int = 8, recorder: Any = None, evidence: Any = None) -> dict[str, Any]:
    """Run H+W steps, or W for an initially fully satisfied episode.

    ``env.reset(episode)`` and ``env.step(action)`` return observation dicts;
    ``env.goal_values()`` returns goal truth. ``policy.reset()`` clears its own
    state and ``policy.predict(obs, instruction)`` returns decoded 7D actions,
    action chunks, or ``None`` for explicit STOP. After STOP the runner calls
    ``env.hold_action()`` afresh for every remaining step. No zero-action hold
    is guessed, and success/done never causes an automatic stop.

    Each trace row describes the state after ``step`` physical actions. Its
    action is the action just applied; ``stopped`` says that this action was
    applied after STOP. ``stop_step`` records the decision boundary itself:
    use that row's goals to score premature stopping, not the first hold row.
    Exceptions are returned as ``runtime_error`` with the partial trace.
    Initial predicate mismatch is ``invalid_initial_state``. Neither status
    may be counted as success. The runner does not close env or policy.
    Optional recording receives copies of existing observations and never
    controls execution. Recording errors are reported separately in ``video``.
    Optional execution evidence records the actual whitelisted reset and query
    inputs without additional environment/policy calls. Evidence failures are
    technical runtime errors; omitting evidence preserves the legacy schema.
    """
    started = perf_counter()
    result = {
        key: deepcopy(episode.get(key)) for key in (
            "episode_id", "task_id", "suite", "task_name", "instruction",
            "seed", "initial_mask", "horizon", "retention_steps",
        )
    }
    result.update(status="runtime_error", trace=[], n_steps=0,
                  policy_queries=0, stop_step=None, error=None)
    video_errors = []

    def capture(observation, step):
        if recorder is not None and not video_errors:
            try:
                recorder.capture(deepcopy(observation), step=step)
            except Exception as exc:
                video_errors.append(f"capture: {type(exc).__name__}: {exc}")

    phase = "validate_episode"
    try:
        chunk_limit = _step_count(max_chunk_steps, "max_chunk_steps", positive=True)
        horizon = _step_count(episode["horizon"], "horizon")
        retention = _step_count(episode["retention_steps"], "retention_steps")
        specs = episode["goal_specs"]
        if not isinstance(specs, list) or not specs:
            raise ValueError("goal_specs must be a nonempty list")
        initial = _goal_values(episode["initial_mask"], len(specs), "initial_mask")
        instruction = episode["instruction"]
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("instruction must be a nonempty string")
        result.update(initial_mask=initial, horizon=horizon, retention_steps=retention)
        total = retention if all(initial) else horizon + retention
        result["scheduled_steps"] = total
        action_queue: deque[np.ndarray] = deque()
        if evidence is not None:
            phase = "evidence_begin"
            evidence.begin_episode(deepcopy(episode), max_chunk_steps=chunk_limit, scheduled_steps=total)

        phase = "env_reset"
        raw_obs = env.reset(deepcopy(episode))
        capture(raw_obs, 0)
        obs = _observation(raw_obs)
        if evidence is not None:
            phase = "evidence_initial_observation"
            evidence.capture_initial(deepcopy(obs))
        phase = "initial_goals"
        goals = _goal_values(env.goal_values(), len(initial), "goal_values")
        result["trace"].append({"step": 0, "goals": goals,
                                "action": None, "stopped": False})
        if goals != initial:
            result.update(status="invalid_initial_state",
                          error=f"initial mask mismatch: expected {initial}, observed {goals}")
            return result

        phase = "policy_reset"
        policy.reset()
        stopped = False
        for step in range(1, total + 1):
            if not stopped and not action_queue:
                if evidence is not None:
                    phase = "evidence_query_input"
                    evidence.prepare_query(deepcopy(obs), obs_step=result["n_steps"],
                                           sequence=result["policy_queries"] + 1)
                phase = "policy_predict"
                result["policy_queries"] += 1
                prediction = policy.predict(obs, instruction)
                if prediction is None:
                    stopped = True
                    result["stop_step"] = result["n_steps"]
                if evidence is not None:
                    phase = "evidence_query_return"
                    evidence.query_returned(deepcopy(prediction))
                if prediction is not None:
                    phase = "validate_action"
                    actions = _actions(prediction)
                    action_queue.extend(actions[:chunk_limit])
                    if evidence is not None:
                        phase = "evidence_accepted_chunk"
                        evidence.accept_actions(actions.copy(), chunk_limit=chunk_limit)
            if stopped:
                phase = "hold_action"
                hold = getattr(env, "hold_action", None)
                if not callable(hold):
                    raise ValueError("explicit STOP requires env.hold_action()")
                action = _actions(hold(), hold=True)
            else:
                action = action_queue.popleft()
            action_record = action.tolist()
            phase = "env_step"
            raw_obs = env.step(action.copy())
            result["n_steps"] = step
            capture(raw_obs, step)
            if evidence is not None:
                phase = "evidence_executed_action"
                evidence.action_executed(step, action.copy(), stopped=stopped)
            phase = "goal_values"
            goals = _goal_values(env.goal_values(), len(initial), "goal_values")
            result["trace"].append({"step": step, "goals": goals,
                                    "action": action_record, "stopped": stopped})
            phase = "observation"
            obs = _observation(raw_obs)
        result["status"] = "completed"
    except Exception as exc:
        result.update(status="runtime_error", error=f"{type(exc).__name__}: {exc}",
                      error_phase=phase)
    finally:
        if recorder is not None:
            video = {}
            try:
                video = recorder.close()
                if not isinstance(video, dict):
                    raise TypeError("video recorder close() must return a dictionary")
                json.dumps(video, allow_nan=False)
            except Exception as exc:
                video = {}
                video_errors.append(f"close: {type(exc).__name__}: {exc}")
            if video_errors:
                prior_error = video.get("error")
                video.update(status="video_error", error="; ".join(
                    ([prior_error] if isinstance(prior_error, str) and prior_error else []) + video_errors))
            result["video"] = video
        if evidence is not None:
            try:
                result["execution_evidence"] = evidence.finish(deepcopy(result))
            except Exception as exc:
                previous = {key: result.get(key) for key in ("status", "error", "error_phase")}
                result.update(status="runtime_error", error=f"{type(exc).__name__}: {exc}",
                              error_phase="evidence_finalize", prior_execution_status=previous)
                try:
                    result["execution_evidence"] = evidence.failure_reference(exc)
                except Exception:
                    result["execution_evidence"] = {"status": "evidence_error", "error": str(exc)}
        result["elapsed_seconds"] = perf_counter() - started
    return result
