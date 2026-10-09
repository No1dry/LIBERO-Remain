"""Prepare one official-source 00 for a capability regression, never a paired pack.

This reuses the existing base preparation, audit and restoration implementation.
It performs no completed-goal placement search, policy inference or GPU work.
The saved start precedes the dynamic audit: callers must restore it through
LiberoGoalEnv before executing the unchanged H=520/W=150 rollout.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmark.states import mujoco_state as ms
from . import build as builder
from .libero_env import create_scene, environment_identity, model_xml_hash, reset_scene, restore_raw_state
from .observation_artifact import load_observation_artifact
from .task_catalog import TASKS, select_tasks


SCHEMA_VERSION = "remaining-goals-capability-statebank-v1"
PURPOSE = "normal00-capability-regression"
SETTLE_STEPS = 80
AUDIT_STEPS = 150
HORIZON = 520
RETENTION_STEPS = 150


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _array_identity(value):
    value = np.ascontiguousarray(value)
    return {"dtype": value.dtype.str, "shape": list(value.shape),
            "sha256": hashlib.sha256(value.tobytes()).hexdigest()}


def _official_source(profile):
    from libero.libero import benchmark, get_libero_path

    suite = benchmark.get_benchmark_dict()[profile["suite"]]()
    matches = [index for index in range(suite.n_tasks) if suite.get_task(index).name == profile["name"]]
    if len(matches) != 1:
        raise ValueError("catalog task name must resolve to exactly one official task index")
    task_index = matches[0]
    task = suite.get_task(task_index)
    root = Path(get_libero_path("init_states")).resolve()
    path = (root / task.problem_folder / task.init_states_file).resolve()
    if not path.is_relative_to(root) or path == root or not path.is_file():
        raise ValueError("official initial-state source must be a file inside its package init_states root")
    source_hash = _sha(path)
    states = builder._official_initial_states(suite, task_index)
    if _sha(path) != source_hash:
        raise ValueError("official initial-state file changed while it was being loaded")
    return task_index, task, states, {"path": str(path), "package_relative_path": path.relative_to(root).as_posix(),
                                     "sha256": source_hash, "count": len(states)}


def prepare_normal00(task_key, initial_state_index, output: Path, *, environment_config=None) -> dict:
    """Prepare exactly one requested index in a new directory, with no fallback.

    Invalid arguments or an existing output raise before execution. Preparation
    failures return status=preparation_error, episode=None and a phase-specific
    error, while preserving the attempted index and all available artifacts.
    The returned environment_config is for a fresh LiberoGoalEnv, not a policy.
    Optional environment_config accepts only image_size=256, control_freq=20,
    and an expected environment identity whose fingerprint must match exactly.
    """
    if not isinstance(task_key, str) or select_tasks([task_key]) != [task_key]:
        raise ValueError("task_key must name exactly one supported task catalog entry")
    if type(initial_state_index) is not int or initial_state_index < 0:
        raise ValueError("initial_state_index must be a nonnegative integer, not a boolean")
    if environment_config is None:
        environment_config = {}
    if not isinstance(environment_config, dict):
        raise ValueError("environment_config must be an object")
    unknown = set(environment_config) - {"image_size", "control_freq", "environment"}
    if unknown:
        raise ValueError(f"unsupported preparation environment options: {sorted(unknown)}")
    for field, fixed in (("image_size", 256), ("control_freq", 20)):
        value = environment_config.get(field, fixed)
        if type(value) is not int or value != fixed:
            raise ValueError(f"capability 00 preparation requires {field}={fixed}")
    expected_identity = environment_config.get("environment")
    if expected_identity is not None and (not isinstance(expected_identity, dict)
                                         or expected_identity.get("name") != "libero"
                                         or not isinstance(expected_identity.get("fingerprint"), str)):
        raise ValueError("expected environment must identify a LIBERO fingerprint")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    profile = deepcopy(TASKS[task_key])
    report = {
        "schema_version": SCHEMA_VERSION, "purpose": PURPOSE, "complete_paired_benchmark": False,
        "status": "preparing", "episode": None, "environment_config": None, "error": None,
        "release_authorized": False,
        "provenance": {"task_key": task_key, "suite": profile["suite"], "task_name": profile["name"],
                       "initial_state_index": initial_state_index, "environment_seed": initial_state_index,
                       "source": "fresh preparation from the exact official initial-state index; no existing state bank reused"},
        "preparation": {"attempted": 1, "requested_index": initial_state_index, "replacement_indices": [],
                        "settle_steps_requested": SETTLE_STEPS, "settle_steps_completed": 0,
                        "audit_steps_requested": AUDIT_STEPS, "audit_steps_completed": 0,
                        "policy_steps": 0, "hold_action": builder.HOLD.tolist(),
                        "hold_scope": "unattended initial-state settling and stability audit only; not a policy STOP guarantee",
                        "horizon": HORIZON, "retention_steps": RETENTION_STEPS,
                        "notice": "Single 00 capability-regression preparation; no paired masks or legal/reachability approval"},
    }
    env = None
    phase = "environment_identity"
    try:
        identity = environment_identity(20)
        if identity.get("name") != "libero":
            raise ValueError("normal00 capability preparation requires a real LIBERO identity")
        if expected_identity is not None and identity.get("fingerprint") != expected_identity["fingerprint"]:
            raise ValueError("runtime LIBERO fingerprint differs from expected preparation environment")
        report["provenance"]["environment"] = deepcopy(identity)
        report["provenance"]["preparer_source_sha256"] = _sha(__file__)
        report["provenance"]["frozen_source_sha256"] = {
            name: _sha(Path(__file__).with_name(name)) for name in (
                "build.py", "construction.py", "validation.py", "task_catalog.py",
                "observation_artifact.py", "libero_env.py", "libero_compat.py")}
        phase = "official_initial_state"
        task_index, source_task, states, source = _official_source(profile)
        report["provenance"].update(official_task_index=task_index, official_initial_state_file=source)
        if initial_state_index >= len(states):
            raise ValueError(f"requested initial-state index {initial_state_index} is outside {len(states)} official states")
        selected = np.asarray(states[initial_state_index])
        if selected.ndim != 1 or not selected.size or selected.dtype.kind not in "fiu" or not np.isfinite(selected).all():
            raise ValueError("selected official state must be a finite one-dimensional real numeric vector")
        report["provenance"]["selected_official_state"] = _array_identity(selected)
        raw_state = selected.astype(np.float64, copy=True)
        report["provenance"]["restored_official_state"] = _array_identity(raw_state)
        phase = "create_scene"
        env, task, bddl = create_scene(profile["suite"], profile["name"], image_size=256, control_freq=20)
        if task.name != source_task.name or task.language != source_task.language:
            raise ValueError("created scene differs from the resolved official task/instruction")
        official = [list(predicate) for predicate in env.env.parsed_problem["goal_state"]]
        grouped = [predicate for goal in profile["goals"] for predicate in goal["predicates"]]
        if sorted(official) != sorted(grouped) or len({tuple(predicate) for predicate in grouped}) != len(grouped):
            raise ValueError("catalog goal groups do not partition the official final predicates")
        phase = "reset_and_restore"
        env.seed(initial_state_index)
        reset_scene(env)
        reset_xml_hash = model_xml_hash(env)
        bddl_hash = _sha(bddl)
        report["provenance"].update(model_xml_sha256=reset_xml_hash, bddl_sha256=bddl_hash,
                                     official_instruction=task.language)
        restore_raw_state(env, raw_state)
        phase = "settle"
        for step in range(SETTLE_STEPS):
            builder._step(env, builder.HOLD.copy())
            report["preparation"]["settle_steps_completed"] = step + 1
        base = builder._state(env).copy()
        zeros = [False] * len(profile["goals"])
        phase = "initial_goal_check"
        actual_goals = builder._goals(env, profile["goals"])
        report["preparation"]["settled_goal_values"] = actual_goals
        if actual_goals != zeros:
            raise ValueError("requested official state is not all-false after the fixed 80-step settle")
        reference = ms.get_robot_qpos(base, ms.StateLayout.from_model(env.sim.model), n=9)
        identifier = f"{task_key}_s{initial_state_index:03d}_{'0' * len(zeros)}"
        relative = Path("validation") / identifier / "base"
        episode = {
            "episode_id": identifier, "task_id": task_key, "suite": profile["suite"],
            "libero_task_id": task_index, "task_name": task.name, "instruction": task.language,
            "goal_specs": deepcopy(profile["goals"]), "initial_mask": zeros,
            "state_path": f"states/{identifier}.npy", "source_id": f"{task_key}_official_{initial_state_index}",
            "split": "val", "initial_state_index": initial_state_index, "seed": initial_state_index,
            "pose_id": "official_settled_base_capability_regression", "horizon": HORIZON,
            "retention_steps": RETENTION_STEPS, "bddl_sha256": bddl_hash,
            "model_xml_sha256": reset_xml_hash, "reference_robot_qpos": reference.tolist(),
            "purpose": PURPOSE,
            "construction": {"method": "official_initial_state_fixed_80_step_settle_00_only",
                             "legal": False, "reviewed_by": "pending_semantic_and_execution_review",
                             "technical_audit": (relative / "audit.json").as_posix()},
        }
        report["provenance"]["settled_base_state"] = _array_identity(base)
        phase = "technical_audit"
        acceptance = builder._audit_state(env, base.copy(), episode, output, relative, validation_steps=AUDIT_STEPS,
                                          velocity_tolerance=0.01, robot_tolerance=0.002)
        report["preparation"]["audit"] = deepcopy(acceptance)
        audit_path = output / relative / "audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        report["preparation"]["audit_steps_completed"] = audit.get("completed_steps", 0)
        report["provenance"]["technical_audit_sha256"] = _sha(audit_path)
        if (acceptance.get("technical_acceptance") is not True or audit.get("technical_acceptance") is not True
                or audit.get("requested_steps") != AUDIT_STEPS or audit.get("completed_steps") != AUDIT_STEPS
                or audit.get("error") is not None or len(audit.get("trace", [])) != AUDIT_STEPS + 1):
            raise ValueError("the requested 00 failed the unchanged static/dynamic technical audit")
        phase = "audit_initial_state_binding"
        first = audit["trace"][0]
        audited_state = np.asarray(first.get("state"), dtype=np.float64)
        if (audited_state.shape != base.shape or not np.array_equal(audited_state.view(np.uint64), base.view(np.uint64))
                or first.get("step") != 0 or first.get("goals") != zeros):
            raise ValueError("passing audit step zero differs from the saved settled base")
        load_observation_artifact(output, episode.get("initial_observation"),
                                  expected_digest=first.get("observation_check", {}).get("returned_sha256"))
        phase = "save_state"
        state_path = output / episode["state_path"]
        state_path.parent.mkdir()
        with state_path.open("xb") as stream:
            np.save(stream, base, allow_pickle=False)
        episode["state_sha256"] = _sha(state_path)
        report["provenance"]["saved_state_sha256"] = episode["state_sha256"]
        report.update(status="prepared", episode=episode,
                      environment_config={"manifest_dir": str(output), "environment": identity,
                                          "control_freq": 20, "image_size": 256})
    except Exception as error:
        report.update(status="preparation_error", episode=None, environment_config=None,
                      error={"phase": phase, "type": type(error).__name__, "message": str(error)})
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as error:
                cleanup = {"phase": "close_environment", "type": type(error).__name__, "message": str(error)}
                report["preparation"]["cleanup_error"] = cleanup
                report.update(status="preparation_error", episode=None, environment_config=None)
                if report["error"] is None:
                    report["error"] = cleanup
        report["preparation"]["elapsed_seconds"] = perf_counter() - started
        builder._write(output / "preparation.json", report)
    return report
