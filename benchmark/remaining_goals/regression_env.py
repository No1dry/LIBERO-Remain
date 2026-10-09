"""Auditable, distinct official and Remain normal-00 execution backends.

The official backend uses OFT's pinned native environment and initial-state
helpers, but owns the loop so errors retain their partial evidence. Policy
workers already return decoded environment actions; no action mapping occurs
here. These single-00 cases are capability regressions, not paired benchmarks.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np

from .isolated_policy import SubprocessPolicy
from .libero_env import LiberoGoalEnv, _observation as native_observation
from .metrics import compute_metrics
from .observation_artifact import save_observation_artifact
from .regression_states import prepare_normal00
from .runner import _actions, _goal_values, _observation, run_episode
from .task_catalog import TASKS, select_tasks
from .video import EpisodeVideoRecorder, normalize_video_config


SCHEMA_VERSION = "remaining-goals-normal00-episode-v1"
PURPOSE = "normal00-capability-regression"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _array_identity(value):
    array = np.ascontiguousarray(value)
    if array.dtype.kind not in "fiu" or not np.isfinite(array).all():
        raise ValueError("state must contain finite real values")
    return {"dtype": array.dtype.str, "shape": list(array.shape),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest()}


def _runtime_info():
    packages = {}
    for name in ("numpy", "libero", "robosuite", "mujoco", "torch", "transformers"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.executable, "python_version": platform.python_version(),
            "platform": platform.platform(), "packages": packages,
            "backend_source_sha256": _sha(__file__)}


def _validate(case, config):
    if not isinstance(case, dict) or not isinstance(config, dict):
        raise ValueError("case and config must be objects")
    key = case.get("task_key")
    if not isinstance(key, str) or select_tasks([key]) != [key] or TASKS[key]["suite"] != "libero_10":
        raise ValueError("normal00 regression requires a supported libero_10 task")
    for field, expected in (("suite", "libero_10"), ("task_name", TASKS[key]["name"])):
        if case.get(field) != expected:
            raise ValueError(f"case {field} differs from catalog")
    if not isinstance(case.get("id"), str) or not case["id"].strip():
        raise ValueError("case id must be nonempty")
    index = case.get("initial_state_index")
    if type(index) is not int or index < 0:
        raise ValueError("initial_state_index must be a nonnegative integer")
    protocol = case.get("protocol")
    if protocol not in {"official", "remain"}:
        raise ValueError("protocol must be official or remain")
    fixed = {"policy_seed": 7, "horizon": 520, "max_chunk_steps": 8,
             "retention_steps": 0 if protocol == "official" else 150,
             "warmup_steps": 10 if protocol == "official" else 0,
             "settle_steps": 0 if protocol == "official" else 80,
             "env_seed": 0 if protocol == "official" else index}
    for field, expected in fixed.items():
        if type(case.get(field)) is not int or case[field] != expected:
            raise ValueError(f"case {field} must equal {expected}")
    if config.get("execution", {}).get("random_seed") != case["policy_seed"]:
        raise ValueError("policy worker seed differs from case policy_seed")


def _official_context(config, case):
    """Load native official helpers without constructing any model weights."""
    # LIBERO's module import otherwise creates this directory and interactively
    # writes config.yaml. A regression must use an existing native installation.
    native_config = Path(os.environ.get("LIBERO_CONFIG_PATH", os.path.expanduser("~/.libero"))) / "config.yaml"
    if not native_config.is_file():
        raise FileNotFoundError(f"existing native LIBERO configuration required before import: {native_config}")
    config_hash = _sha(native_config)
    from .adapters.openvla import _BASE_OPTIONS, _config, _load_upstream
    from .adapters.openvla_oft import UPSTREAM_COMMIT
    # The full adapter _options validates downloaded model resources. That
    # belongs to SubprocessPolicy's model_load phase, not environment preparation.
    options = deepcopy(config.get("adapter_options"))
    if not isinstance(options, dict) or set(options) - _BASE_OPTIONS:
        raise ValueError("official environment requires the unchanged OFT adapter option names")
    for field in ("repo_path", "checkpoint", "suite"):
        if not isinstance(options.get(field), str) or not options[field].strip():
            raise ValueError(f"adapter_options.{field} must be a nonempty string")
    if options["suite"] != case["suite"]:
        raise ValueError("official environment suite differs from case")
    if "seed" in options and options["seed"] != case["policy_seed"]:
        raise ValueError("adapter and case policy seeds differ")
    options["seed"] = case["policy_seed"]
    api, _torch, commit = _load_upstream(options, UPSTREAM_COMMIT)
    if _sha(native_config) != config_hash:
        raise ValueError("native LIBERO configuration changed during upstream import")
    cfg = _config(api, options)
    cfg.initial_states_path = "DEFAULT"
    cfg.env_img_res = 256
    cfg.num_steps_wait = 10
    cfg.num_open_loop_steps = 8
    suite = api.benchmark.get_benchmark_dict()[case["suite"]]()
    matches = [i for i in range(suite.n_tasks) if suite.get_task(i).name == case["task_name"]]
    if len(matches) != 1:
        raise ValueError("task name must resolve to exactly one official task index")
    task_index = matches[0]
    task = suite.get_task(task_index)
    from libero.libero import get_libero_path
    import libero.libero as libero_module
    source_root = Path(get_libero_path("init_states")).resolve()
    source = (source_root / task.problem_folder / task.init_states_file).resolve()
    if not source.is_relative_to(source_root) or not source.is_file():
        raise ValueError("official initial-state source is outside its package root or missing")
    source_hash = _sha(source)
    states, custom = api.load_initial_states(cfg, suite, task_index)
    if custom is not None or _sha(source) != source_hash:
        raise ValueError("official default initial-state source changed or custom states were returned")
    index = case["initial_state_index"]
    if index >= len(states):
        raise IndexError(f"requested official initial-state index {index} outside {len(states)} states")
    selected = np.asarray(states[index]).copy()
    if selected.ndim != 1:
        raise ValueError("official initial state must be a vector")
    identity = _array_identity(selected)
    env = None
    try:
        env, instruction = api.get_libero_env(task, cfg.model_family, resolution=256)
        if instruction != task.language:
            raise ValueError("official environment instruction differs from selected task")
        goals = deepcopy(TASKS[case["task_key"]]["goals"])
        official = env.env.parsed_problem["goal_state"]
        grouped = [p for goal in goals for p in goal["predicates"]]
        if sorted(map(tuple, official)) != sorted(map(tuple, grouped)) or len(set(map(tuple, grouped))) != len(grouped):
            raise ValueError("catalog goals do not partition official final predicates")
        dummy = _actions(api.get_libero_dummy_action(cfg.model_family), hold=True)
        repo = Path(options["repo_path"])
        provenance = {
            "upstream_repo_commit": commit, "task_index": task_index,
            "official_initial_states": {"path": str(source), "sha256": source_hash,
                                        "package_relative_path": source.relative_to(source_root).as_posix(),
                                        "count": len(states)},
            "selected_official_state": identity,
            "native_libero_config": {"path": str(native_config.absolute()), "sha256": config_hash},
            "libero_module": {"path": str(libero_module.__file__), "sha256": _sha(libero_module.__file__)},
            "official_source_sha256": {name: _sha(repo / "experiments/robot/libero" / name)
                                       for name in ("run_libero_eval.py", "libero_utils.py")},
            "environment_seed": 0, "control_freq": 20, "image_size": 256,
            "restore": "native reset then native set_init_state; no Remain controller/gripper restoration",
        }
        return {"env": env, "initial_state": selected, "instruction": instruction,
                "goals": goals, "dummy_action": dummy, "provenance": provenance}
    except BaseException:
        if env is not None:
            env.close()
        raise


def _native_goals(env, specs):
    goals = [all(bool(env.env._eval_predicate(p)) for p in goal["predicates"]) for goal in specs]
    if all(goals) != bool(env.check_success()):
        raise RuntimeError("grouped goals differ from native official success")
    return goals


class _PreparedEnvironment:
    """Give the unchanged runner one already verified reset observation."""
    def __init__(self, env, episode, observation):
        self.env, self.episode, self.observation = env, deepcopy(episode), deepcopy(observation)
        self.used = False
        self.first_action = None

    def reset(self, episode):
        if self.used or episode != self.episode:
            raise RuntimeError("prepared environment reset is single-use for the exact prepared episode")
        self.used = True
        return deepcopy(self.observation)

    def goal_values(self):
        return self.env.goal_values()

    def step(self, action):
        observation = self.env.step(action)
        if self.first_action is None:
            self.first_action = np.asarray(action).tolist()
        return observation

    def hold_action(self):
        return self.env.hold_action()


def _error(result, phase, exc, status):
    result.update(status=status, common_success=None, native_success=None,
                  termination_reason=status,
                  error={"phase": phase, "type": type(exc).__name__, "message": str(exc)})


def _video_close(recorder, result, failures):
    report = {}
    try:
        report = recorder.close()
        if not isinstance(report, dict):
            raise TypeError("recorder.close() must return an object")
        json.dumps(report, allow_nan=False)
    except Exception as exc:
        report = {}
        failures.append(f"close: {type(exc).__name__}: {exc}")
    if failures:
        report.update(status="video_error", path=None, error="; ".join(failures))
    result["video"] = report


def execute_case(config, case: dict, output: Path, *, video_config: dict) -> dict:
    """Execute one fresh case; never replace a failed source or hide its trace."""
    _validate(case, config)
    video_config = normalize_video_config(video_config)
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    result = deepcopy(case)
    result.update(schema_version=SCHEMA_VERSION, purpose=PURPOSE, complete_paired_benchmark=False,
                  attempted=True, prepared=False, policy_started=False, status="preparation_error",
                  common_success=None, native_success=None, error=None, trace=[], n_steps=0,
                  policy_queries=0, stop_step=None, first_action=None, metrics=None,
                  warmup_trace=[], warmup_steps_completed=0, settle_steps_completed=0,
                  video_config=video_config, runtime=_runtime_info(),
                  seed_scope="worker_and_episode_reset",
                  rng_protocol_note="policy seed is reset for each independent case; upstream evaluation seeds once across episodes",
                  success_definitions={"common": "all grouped official final goals true at any policy step 0..520",
                                       "native": "policy-stage official done" if case["protocol"] == "official"
                                                 else "unchanged Remain metrics.joint_success (H=520/W=150)"})
    env = policy = recorder = None
    video_failures = []
    recorder_closed = False
    phase = "prepare"
    error_status = "preparation_error"
    try:
        if case["protocol"] == "official":
            phase = "official_context"
            context = _official_context(config, case)
            env = context["env"]
            result["environment_provenance"] = context["provenance"]
            specs, instruction = context["goals"], context["instruction"]
            phase = "official_reset"
            env.reset()
            raw_obs = env.set_init_state(context["initial_state"])
            phase = "official_warmup"
            for step in range(1, case["warmup_steps"] + 1):
                raw_obs, _reward, done, _info = env.step(context["dummy_action"].tolist())
                result["warmup_steps_completed"] = step
                result["warmup_trace"].append({"step": step, "action": context["dummy_action"].tolist(),
                                               "native_done": bool(done), "goals": _native_goals(env, specs)})
            obs = _observation(native_observation(raw_obs))
            goals = _native_goals(env, specs)
            result["environment_provenance"]["policy_step0_state"] = _array_identity(env.sim.get_state().flatten())
            episode = {"episode_id": case["id"], "task_id": case["task_key"],
                       "instruction": instruction, "goal_specs": specs,
                       "initial_mask": [False] * len(specs), "horizon": 520, "retention_steps": 0}
        else:
            phase = "remain_preparation"
            preparation = prepare_normal00(case["task_key"], case["initial_state_index"], output / "preparation")
            result["preparation"] = preparation["preparation"]
            result["environment_provenance"] = preparation["provenance"]
            result["settle_steps_completed"] = preparation["preparation"].get("settle_steps_completed", 0)
            if preparation["status"] != "prepared":
                result["error"] = preparation["error"]
                result["termination_reason"] = "preparation_error"
                return result
            episode = deepcopy(preparation["episode"])
            if (episode["horizon"] != 520 or episode["retention_steps"] != 150 or
                    episode["initial_mask"] != [False] * len(episode["goal_specs"])):
                raise ValueError("preparation returned an incompatible normal00 episode")
            result["prepared_episode"] = deepcopy(episode)
            phase = "remain_reset"
            env = LiberoGoalEnv(preparation["environment_config"])
            obs = _observation(env.reset(episode))
            specs, instruction = episode["goal_specs"], episode["instruction"]
            goals = _goal_values(env.goal_values(), len(specs), "goal_values")
        result.update(instruction=instruction, initial_mask=episode["initial_mask"],
                      goal_specs=deepcopy(specs),
                      trace=[{"step": 0, "goals": goals, "action": None, "stopped": False}])
        phase = "initial_goals"
        if goals != episode["initial_mask"]:
            raise ValueError(f"requested source is not normal00 at policy step zero: {goals}")
        phase = "save_initial_observation"
        result["initial_observation"] = save_observation_artifact(output, "initial_observation.npz", obs)
        result["prepared"] = True
        if video_config["enabled"]:
            try:
                recorder = EpisodeVideoRecorder(output / "videos" / "episode.mp4", video_config,
                                                environment_name="libero", episode=episode)
            except Exception as exc:
                result["video"] = {"status": "video_error", "path": None, "error": f"{type(exc).__name__}: {exc}"}
        phase, error_status = "model_load", "model_load_error"
        policy = SubprocessPolicy(config)
        result["policy_provenance"] = deepcopy(policy.provenance)
        result["policy_started"] = True
        phase, error_status = "policy_reset", "runtime_error"
        if case["protocol"] == "remain":
            ready = _PreparedEnvironment(env, episode, obs)
            rollout = run_episode(ready, policy, episode, max_chunk_steps=8, recorder=recorder)
            recorder_closed = recorder is not None
            for key in ("trace", "n_steps", "policy_queries", "stop_step", "video"):
                if key in rollout:
                    result[key] = rollout[key]
            result["first_action"] = ready.first_action
            result["rollout_elapsed_seconds"] = rollout["elapsed_seconds"]
            if rollout["status"] != "completed":
                result.update(status="runtime_error", termination_reason="runtime_error",
                              error={"phase": rollout.get("error_phase", "rollout"),
                                     "type": rollout["status"], "message": rollout.get("error")})
            else:
                result["metrics"] = compute_metrics(episode, rollout["trace"])
                result.update(status="completed", termination_reason="horizon_and_retention_exhausted",
                              common_success=result["metrics"]["task_success_by_horizon"],
                              native_success=result["metrics"]["joint_success"])
        else:
            def capture(value, step):
                if recorder is not None and not video_failures:
                    try:
                        recorder.capture(deepcopy(value), step=step)
                    except Exception as exc:
                        video_failures.append(f"capture: {type(exc).__name__}: {exc}")
            capture(obs, 0)
            policy.reset()
            queue = deque()
            done = False
            for step in range(1, case["horizon"] + 1):
                if not queue:
                    phase = "policy_predict"
                    result["policy_queries"] += 1
                    prediction = policy.predict(_observation(obs), instruction)
                    if prediction is None:
                        raise ValueError("official OFT has no STOP action; a None prediction is invalid")
                    phase = "validate_action"
                    queue.extend(_actions(prediction)[:case["max_chunk_steps"]])
                action = queue.popleft()
                phase = "env_step"
                raw_obs, _reward, done, _info = env.step(action.tolist())
                result["n_steps"] = step
                if result["first_action"] is None:
                    result["first_action"] = action.tolist()
                # Preserve the last available RGB even if evaluator predicates
                # fail afterwards. This is a copy of the native returned frame,
                # never another render or a policy input containing truth.
                capture(raw_obs, step)
                phase = "goal_values"
                goals = _native_goals(env, specs)
                result["trace"].append({"step": step, "goals": goals, "action": action.tolist(),
                                        "stopped": False, "native_done": bool(done)})
                phase = "observation"
                obs = _observation(native_observation(raw_obs))
                if done:
                    break
            result.update(status="completed", termination_reason="evaluator_success" if done else "horizon_exhausted",
                          common_success=any(all(row["goals"]) for row in result["trace"]), native_success=bool(done))
    except Exception as exc:
        _error(result, phase, exc, error_status)
    finally:
        if recorder is not None and not recorder_closed:
            _video_close(recorder, result, video_failures)
        if result.get("video", {}).get("path"):
            result["video"]["path"] = "videos/" + Path(result["video"]["path"]).name
        for resource, name in ((policy, "policy"), (env, "environment")):
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    result.setdefault("cleanup_errors", []).append({"resource": name, "type": type(exc).__name__, "message": str(exc)})
                    if result["status"] == "completed":
                        _error(result, f"close_{name}", exc, "runtime_error")
        result["elapsed_seconds"] = perf_counter() - started
        (output / "episode.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return result
