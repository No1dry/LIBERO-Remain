"""Versioned single-source selected10 / normal00 producers for task031.

Selected10 constructs only goal A and transplants only its exact whitelist.
Normal00 saves the official fixed-index settled base with an initial-only audit.
Neither path calls a model or changes the original complete-mask builder.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np

from .schema import manifest_hash
from .task_catalog import TASKS
from .nine_catalog import (NEW_TASKS, NINE_PROTOCOLS, get_task, episode_fields,
                           read_goal_facts, initial_constraints_match)

SELECTED_TASKS = ("frypan_stove9", "cabinet_close_top_bowl")
METHOD = "selected_A_only_settle_component_transplant_v1"
METHOD_R2 = "selected_A_only_bounded_settle_component_transplant_v2"
NORMAL_METHOD = "official_fixed_init_settle_initial_only_v1"
BOUNDED_SETTLE = {"schema_version": "remaining-selected-component-settle-v2", "min_steps": 80,
                  "max_steps": 400, "required_stable_observations": 20,
                  "velocity_limit": .01, "position_span_limit": .005}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _array_sha(state):
    return _sha(np.asarray(state).astype("<f8").tobytes())


def _backend():
    from . import build
    return build


def _suite(profile):
    from libero.libero import benchmark
    return benchmark.get_benchmark_dict()[profile["suite"]]()


def _official_asset(suite, task_index):
    from libero.libero import get_libero_path
    task = suite.get_task(task_index)
    root = Path(get_libero_path("init_states")).resolve()
    path = (root / task.problem_folder / task.init_states_file).resolve()
    if not path.is_relative_to(root):
        raise ValueError("official init asset escaped package root")
    return {"asset": path.relative_to(root).as_posix(), "sha256": _sha(path.read_bytes())}


def _settle_component(b, env, profile, semantics, whitelist, evidence):
    """Observe bounded real HOLD convergence; never edit a measured velocity."""
    layout = b.ms.StateLayout.from_model(env.sim.model)
    entry = b.ms.resolve_free_joint(env.sim.model, profile["goals"][0]["predicates"][0][1])
    position_indices = list(range(1 + entry.qpos_adr, 1 + entry.qpos_adr + 3))
    qpos_indices = [i for i in whitelist if layout.qpos_slice.start <= i < layout.qpos_slice.stop]
    qvel_indices = [i for i in whitelist if layout.qvel_slice.start <= i < layout.qvel_slice.stop]
    if not set(position_indices).issubset(whitelist) or not qvel_indices:
        raise ValueError("bounded settling requires the selected object's actual position and velocity whitelist")
    evidence.update(deepcopy(BOUNDED_SETTLE), mode="bounded_convergence", attempted_steps=0,
        completed_steps=0, exception_calls=0, converged=False, stop_reason="running", samples=[],
        count_scope="candidate HOLD only; excludes base80 and construction audit150")
    positions = []
    for step in range(1, evidence["max_steps"] + 1):
        evidence["attempted_steps"] += 1
        try:
            b._step(env, b.HOLD)
        except BaseException:
            evidence["exception_calls"] += 1
            evidence["stop_reason"] = "step_exception"
            raise
        evidence["completed_steps"] += 1
        state = b._state(env)
        if not np.isfinite(state).all():
            evidence["stop_reason"] = "nonfinite_state"
            raise ValueError("bounded settle produced a nonfinite physical state")
        facts = read_goal_facts(env.env._eval_predicate, env.check_success(), semantics)
        max_velocity = float(np.max(np.abs(state[layout.qvel_slice])))
        eligible = max_velocity <= evidence["velocity_limit"] and facts["goals"] == [True, False] and initial_constraints_match(facts)
        positions = (positions + [state[position_indices].copy()])[-evidence["required_stable_observations"]:] if eligible else []
        span = float(np.linalg.norm(np.ptp(np.asarray(positions), axis=0))) if positions else None
        evidence["samples"].append({"step": step, "max_abs_qvel": max_velocity,
            "selected_qpos": state[qpos_indices].tolist(), "selected_qvel": state[qvel_indices].tolist(),
            "goal_facts": facts, "eligible": bool(eligible), "stable_observations": len(positions),
            "position_span_m": span})
        if (step >= evidence["min_steps"] and len(positions) == evidence["required_stable_observations"]
                and span <= evidence["position_span_limit"]):
            evidence.update(converged=True, stop_reason="bounded_settle_converged", state_array_sha256=_array_sha(state))
            return state
    evidence["stop_reason"] = "bounded_settle_not_converged"
    return None


def build(output, *, task, index, protocol="selected-mask10", max_candidates=24, construction_method=None,
          observation_profile=None):
    """Produce one fixed official source, always in a fresh directory.

    Default v1 keeps settle80. Explicit R2 microwave convergence is bounded at
    400 HOLD steps; base80 and selected150 audit remain unchanged. Failed
    candidates stay in the new output and never replace old files.
    """
    nine = protocol in NINE_PROTOCOLS
    from .validation import observation_profile_config, V6_PROFILE
    observation_config = observation_profile_config(observation_profile)
    if observation_profile == V6_PROFILE and not nine:
        raise ValueError("v6 source construction is limited to the nine-task protocols")
    if (task not in (NEW_TASKS if nine else SELECTED_TASKS) or type(index) is not int or index not in range(10)
            or protocol not in ("selected-mask10", "normal00-control", *NINE_PROTOCOLS)
            or type(max_candidates) is not int or not 1 <= max_candidates <= 24):
        raise ValueError("selected builder requires one fixed task/index and at most 24 A candidates")
    r2 = construction_method == METHOD_R2
    if construction_method not in (None, METHOD, METHOD_R2) or r2 and (protocol != "nine-mask10" or task not in NEW_TASKS):
        raise ValueError("R2 construction is explicit and limited to new-three nine-mask10 sources")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    b = _backend()
    profile = get_task(task) if nine else TASKS[task]
    normal = protocol in ("normal00-control", "nine-normal00")
    method = NORMAL_METHOD if normal else METHOD_R2 if r2 else METHOD
    identity = b.environment_identity(20)
    manifest = {"schema_version": "remaining-goals-v0.1", "environment": identity, "episodes": []}
    group = {"task_id": task, "suite": profile["suite"], "task_name": profile["name"],
             "initial_state_index": index, "seed": index, "complete": False, "attempts": []}
    report = {"kind": "normal00_initialization_v1" if normal else "selected_mask10_candidate_construction_v2" if r2 else "selected_mask10_candidate_construction_v1",
              "protocol": protocol, "method": method,
              "environment": identity, "hold_action": b.HOLD.tolist(), "settle_steps": 80,
              "validation_steps": 0 if normal else 150, "initialization_kind": "settled_base",
              "construction_scope": "initial_only_00" if normal else "selected_A_only_actual10",
              "dynamic_stability": None if normal else "see_selected_audit",
              "policy_called": False, "release_authorized": False, "complete": False,
              "builder_sources_sha256": {name: _sha((Path(__file__).parent / name).read_bytes())
                                         for name in ("selected_build.py", "build.py", "construction.py", "validation.py", "task_catalog.py")
                                         + (("nine_catalog.py", "libero_env.py") if nine else ())},
              "groups": [group]}
    if observation_profile is not None:
        manifest["observation_profile"] = report["observation_profile"] = observation_profile
        report.update(observation_audit_limits=observation_config["limits"],
                      observation_audit_rule=observation_config["rule"],
                      observation_audit_limitation=observation_config["limitation"])
    if r2:
        report["candidate_settle_contract"] = deepcopy(BOUNDED_SETTLE) if task == "mug_microwave_close" else {"mode": "fixed80", "steps": 80}
        report["seed_velocity_policy"] = "preserve_entire_real_settled_base_qvel_before_native_restore"
    env = None
    try:
        suite = _suite(profile)
        task_index = next(i for i in range(suite.n_tasks) if suite.get_task(i).name == profile["name"])
        if nine and task_index != profile["official_task_id"]:
            raise ValueError("nine-task official index/name mapping differs")
        initial_states = b._official_initial_states(suite, task_index)
        if index >= len(initial_states):
            raise ValueError("fixed official source index is absent; no replacement is allowed")
        official_state = np.asarray(initial_states[index], dtype=np.float64)
        if official_state.ndim != 1 or not np.isfinite(official_state).all():
            raise ValueError("official initial state is not a finite vector")
        group["official_initial_asset"] = _official_asset(suite, task_index)
        group["official_task_index"] = task_index
        group["raw_official_state_array_sha256"] = _array_sha(official_state)
        env, official_task, bddl = b.create_scene(profile["suite"], profile["name"], image_size=256, control_freq=20)
        official_goals = [list(p) for p in env.env.parsed_problem["goal_state"]]
        fields = episode_fields(task, official_goals) if nine else {"goal_specs": deepcopy(profile["goals"])}
        if not nine and sorted(official_goals) != sorted(p for g in profile["goals"] for p in g["predicates"]):
            raise ValueError("task profile differs from official goals")
        env.seed(index)
        b.reset_scene(env)
        reset_xml_hash = b.model_xml_hash(env)
        group["reset_model_xml_sha256"] = reset_xml_hash
        b.restore_raw_state(env, official_state)
        for _ in range(80):
            b._step(env, b.HOLD)
        base = b._state(env)
        if not np.isfinite(base).all() or b._goals(env, profile["goals"]) != [False, False]:
            raise ValueError("official settled base is not finite actual00")
        if nine and not initial_constraints_match(read_goal_facts(env.env._eval_predicate, env.check_success(), fields["task_semantics"])):
            raise ValueError("official settled base violates invariant or required Open predicate")
        group["base_state_array_sha256"] = _array_sha(base)
        base_q = b.ms.get_robot_qpos(base, b.ms.StateLayout.from_model(env.sim.model), n=9)

        def episode_for(number):
            bits = "00" if normal else "10"
            episode_id = f"{task}_s{index:03d}_{bits}"
            relative = Path("validation") / episode_id / f"attempt_{number:03d}"
            return {"episode_id": episode_id, "task_id": task, "suite": profile["suite"],
                    "libero_task_id": task_index, "task_name": official_task.name, "instruction": official_task.language,
                    **deepcopy(fields), "initial_mask": [False, False] if normal else [True, False],
                    "source_id": f"{task}_official_{index}", "initial_state_index": index, "seed": index,
                    "split": "test", "pose_id": "official_settled_initial_only_v1" if normal else "selected_A_settled_transplant_v2" if r2 else "selected_A_settled_transplant_v1",
                    "horizon": 520, "retention_steps": 150,
                    "state_path": f"states/{episode_id}.npy", "bddl_sha256": _sha(bddl.read_bytes()),
                    "model_xml_sha256": reset_xml_hash, "reference_robot_qpos": base_q.tolist(),
                    "construction": {"method": method, "legal": False,
                                     "reviewed_by": "pending_semantic_and_execution_review",
                                     "technical_audit": (relative / "audit.json").as_posix(),
                                     "protocol": protocol}}, relative

        def audit_and_export(state, number, provenance):
            episode, relative = episode_for(number)
            episode["construction"].update(provenance)
            options = {}
            if observation_profile is not None:
                episode["observation_profile"] = observation_profile
                options["observation_profile"] = observation_profile
            acceptance = b._audit_state(env, state, episode, output, relative,
                                        validation_steps=0 if normal else 150,
                                        velocity_tolerance=.01, robot_tolerance=.002, **options)
            group["attempts"].append({"candidate": number, **acceptance, **provenance})
            if not acceptance["technical_acceptance"]:
                return False
            state_path = output / episode["state_path"]
            state_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(state_path, state)
            episode["state_sha256"] = _sha(state_path.read_bytes())
            manifest["episodes"].append(episode)
            group.update(complete=True, episode_id=episode["episode_id"], state_path=episode["state_path"],
                         state_sha256=episode["state_sha256"],
                         initial_observation_sha256=episode["initial_observation"]["sha256"],
                         initial_observation_digest=episode["initial_observation"]["observation_sha256"],
                         audit_path=episode["construction"]["technical_audit"])
            return True

        if normal:
            audit_and_export(base, 0, {"acceptance_scope": "initial_only", "dynamic_stability": None})
        else:
            # Only A is enumerated. B has no candidate generation, settling,
            # partner audit or eligibility role in this new construction method.
            active_profile = deepcopy(profile)
            active_profile["goals"] = [deepcopy(profile["goals"][0])]
            if r2 and task == "bowl_drawer_close":
                active_profile["in_volume_regions"] = ["white_cabinet_1_bottom_region"]
            per_goal = b._per_goal(env, base, active_profile, max_candidates)
            active_candidates = per_goal[0]
            if not active_candidates:
                raise ValueError("no active-A construction candidates")
            whitelist = list(active_candidates[0]["allowed_indices"])
            if not whitelist or any(list(item["allowed_indices"]) != whitelist for item in active_candidates):
                raise ValueError("active A candidate whitelist is empty or changes")
            candidates = b.combine_goal_candidates(base, env.sim.model, per_goal, [True], max_candidates=max_candidates)
            for number, candidate in enumerate(candidates):
                if set(candidate["allowed_indices"]) != set(whitelist):
                    raise ValueError("composed A whitelist differs from generated candidates")
                seed = candidate["state"].copy()
                settling = None
                seed_provenance = {}
                if r2:
                    layout = b.ms.StateLayout.from_model(env.sim.model)
                    # Existing seed generators may zero a free object's velocity.
                    # R2 retains the *measured* base qvel before any native restore;
                    # neither final convergence nor audit is obtained by clearing it.
                    seed[layout.qvel_slice] = base[layout.qvel_slice]
                    seed_provenance = {"seed_velocity_policy": report["seed_velocity_policy"],
                        "seed_qvel": seed[layout.qvel_slice].tolist(),
                        "seed_qvel_array_sha256": _array_sha(seed[layout.qvel_slice])}
                b.restore_raw_state(env, seed)
                if r2 and task == "mug_microwave_close":
                    settling = {}
                    try:
                        settled = _settle_component(b, env, profile, fields["task_semantics"], whitelist, settling)
                    except BaseException:
                        group["attempts"].append({"candidate": number, "technical_acceptance": False,
                            "candidate_settle": settling, "candidate_diagnostics": candidate["diagnostics"], **seed_provenance})
                        raise
                    if settled is None:
                        group["attempts"].append({"candidate": number, "technical_acceptance": False,
                            "candidate_settle": settling, "candidate_diagnostics": candidate["diagnostics"], **seed_provenance})
                        continue
                else:
                    for _ in range(80):
                        b._step(env, b.HOLD)
                    settled = b._state(env)
                frozen = base.copy()
                frozen[whitelist] = settled[whitelist]
                whitelist_audit = b.state_diff_whitelist(base, frozen, env.sim.model, whitelist)
                if not whitelist_audit["valid"]:
                    raise ValueError("selected transplant changed a non-whitelisted state coordinate")
                values = frozen[whitelist]
                provenance = {"candidate_number": number, "base_state_array_sha256": _array_sha(base),
                              "selected_component": {"goal_index": 0, "indices": whitelist,
                                                     "values": values.tolist(), "values_sha256": _array_sha(values)},
                              "whitelist": whitelist_audit, "candidate_diagnostics": candidate["diagnostics"]}
                if r2:
                    provenance.update(seed_provenance)
                    if settling is not None:
                        provenance["candidate_settle"] = settling
                if audit_and_export(frozen, number, provenance):
                    break
            if not group["complete"]:
                group["error"] = "all bounded selected-A candidates failed actual10 construction audit"
    except Exception as error:
        group["error"] = f"{type(error).__name__}: {error}"
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as error:
                group["close_error"] = f"{type(error).__name__}: {error}"
        report["complete"] = group["complete"]
        manifest["content_hash"] = manifest_hash(manifest)
        b._write(output / "construction_report.json", report)
        b._write(output / "manifest.candidates.json", manifest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--task", required=True, choices=(*SELECTED_TASKS, *NEW_TASKS))
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--protocol", choices=("selected-mask10", "normal00-control", *NINE_PROTOCOLS), default="selected-mask10")
    parser.add_argument("--construction-method", choices=(METHOD, METHOD_R2))
    from .validation import V6_PROFILE, RGB_QUANTIZATION_RULE
    parser.add_argument("--observation-profile", choices=(RGB_QUANTIZATION_RULE["rule_id"], V6_PROFILE))
    args = parser.parse_args(argv)
    if not build(args.out, task=args.task, index=args.index, protocol=args.protocol,
                 construction_method=args.construction_method, observation_profile=args.observation_profile)["complete"]:
        raise SystemExit("source construction failed; inspect construction_report.json")


if __name__ == "__main__":
    main()
