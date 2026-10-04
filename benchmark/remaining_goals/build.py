"""Build real LIBERO precompletion candidates with per-step physics audits.

This command never substitutes toy states and never certifies execution
feasibility from predicate satisfaction. Its output is a technical candidate
pack pending semantic/feasibility review, not an automatically released dataset.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np

from benchmark.states import mujoco_state as ms
from .construction import placement_candidates, joint_candidates, drawer_candidates, combine_goal_candidates, state_diff_whitelist
from .libero_env import create_scene, restore_raw_state, fresh_observation, model_xml_hash, environment_identity, reset_scene
from .validation import validate_candidate, RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_LIMITATION, RGB_QUANTIZATION_RULE
from .schema import manifest_hash
from .observation_artifact import save_observation_artifact
from .task_catalog import TASKS, mask_order, select_tasks

HOLD = np.array([0, 0, 0, 0, 0, 0, -1.0])


def _serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serial(item) for item in value]
    return value


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_serial(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _state(env):
    return np.asarray(env.sim.get_state().flatten(), dtype=np.float64).copy()


def _clear_done(env):
    for holder in (env, env.env):
        if "done" in vars(holder):
            holder.done = False


def _step(env, action):
    _clear_done(env)
    env.step(np.asarray(action).tolist())
    # Native sensor caches can lag the final physics substep. All benchmark
    # policies and construction audits use the same synchronized observation.
    return fresh_observation(env)


def _goals(env, goal_specs):
    return [all(bool(env.env._eval_predicate(list(p))) for p in goal["predicates"]) for goal in goal_specs]


def _image(path: Path, observation):
    from PIL import Image
    image = np.asarray(observation["agentview_image"])[::-1, ::-1]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.astype(np.uint8)).save(path)


class CandidateAuditEnv:
    """Adapter exposing privileged data exclusively to the technical auditor."""
    def __init__(self, env, state, goals, *, frames_dir: Path | None = None):
        self.env, self.candidate, self.goals = env, state, goals
        self.layout = ms.StateLayout.from_model(env.sim.model)
        self.frames_dir = frames_dir
        self.steps = 0
        self.initial_observation = None
        self.objects = [name for names in env.env.parsed_problem["objects"].values() for name in names]
        self.articulation_sites = []
        targets = sorted({predicate[1] for goal in goals for predicate in goal["predicates"]
                          if predicate[0].lower() in ("open", "close")})
        for name in targets:
            try:
                site = int(env.sim.model.site_name2id(name))
            except AttributeError:
                site = int(env.sim.model.site(name).id)
            if site < 0 or site >= int(env.sim.model.nsite):
                raise ValueError(f"required articulated goal region site is missing: {name}")
            self.articulation_sites.append((name, site))

    def restore_candidate(self, episode):
        self.steps = 0
        _clear_done(self.env)
        observation = restore_raw_state(self.env, self.candidate)
        # Capture the actual returned step-zero arrays, never a later rerender.
        self.initial_observation = deepcopy(observation)
        if self.frames_dir:
            _image(self.frames_dir / "start.png", observation)
        return observation

    def step(self, action):
        observation = _step(self.env, action)
        self.steps += 1
        if self.frames_dir and self.steps % 50 == 0:
            _image(self.frames_dir / f"step_{self.steps:04d}.png", observation)
        return observation

    def validation_snapshot(self):
        before = _state(self.env)
        observation = fresh_observation(self.env)
        state = _state(self.env)
        positions = {name: ms.get_object_pos(state, self.env.sim.model, name).tolist() for name in self.objects}
        # Predicates alone would miss motion within their truth intervals. A
        # drawer is not a free object, so explicitly audit its moving goal site
        # with the same per-step position-drift limit as all other objects.
        for name, site in self.articulation_sites:
            position = np.asarray(self.env.sim.data.site_xpos[site])
            if position.shape != (3,) or not np.isfinite(position).all():
                raise ValueError(f"invalid articulated goal region position: {name}")
            positions[f"site:{name}"] = position.tolist()
        contacts = []
        model, data = self.env.sim.model, self.env.sim.data
        for i in range(int(data.ncon)):
            contact = data.contact[i]
            contacts.append({
                "geom1": model.geom_id2name(int(contact.geom1)) or f"geom_{contact.geom1}",
                "geom2": model.geom_id2name(int(contact.geom2)) or f"geom_{contact.geom2}",
                "depth": max(0.0, -float(contact.dist)),
            })
        return {"state": state, "state_before_refresh": before,
                "qvel": state[self.layout.qvel_slice],
                "robot_qpos": ms.get_robot_qpos(state, self.layout, n=9),
                "object_positions": positions, "penetrations": contacts,
                "goals": _goals(self.env, self.goals), "fresh_observation": observation}


def _official_initial_states(suite, task_index):
    """Read only the pinned upstream package's trusted .pruned_init assets."""
    import torch
    from libero.libero import get_libero_path
    task = suite.get_task(task_index)
    root = Path(get_libero_path("init_states")).resolve()
    path = (root / task.problem_folder / task.init_states_file).resolve()
    if root not in path.parents:
        raise ValueError("official initial-state path escaped its package root")
    # PyTorch >=2.6 defaults to weights_only, which cannot read legacy NumPy
    # init-state files. These files are trusted, pinned upstream assets.
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(path, map_location="cpu")


def _per_goal(env, base, profile, max_candidates):
    model = env.sim.model
    data = env.sim.data
    result = []
    for goal in profile["goals"]:
        restore_raw_state(env, base)
        predicate = goal["predicates"][0]
        if predicate[0] in ("in", "on"):
            reserved = [g["predicates"][0][1] for g in profile["goals"]
                        if len(g["predicates"][0]) == 3 and g["predicates"][0][2] == predicate[2]]
            candidates = placement_candidates(base, model, data, predicate[1], predicate[2],
                                              relation=predicate[0], reservation_objects=reserved,
                                              target_kind="object" if predicate[2] in profile.get("object_supports", []) else "region",
                                              max_candidates=max_candidates)
        elif predicate[0] == "turnon":
            candidates = []
            for joint in ms.iter_joints(model):
                if joint.name.startswith(predicate[1]) and not joint.is_free:
                    for candidate in joint_candidates(base, model, joint.name):
                        restore_raw_state(env, candidate["state"])
                        if bool(env.env._eval_predicate(predicate)):
                            candidates.append(candidate)
            candidates = candidates[:max_candidates]
        elif predicate[0] in ("open", "close"):
            contract = profile.get("joint_contracts", {}).get(predicate[1])
            if not contract:
                raise ValueError("drawer predicate needs an explicit exact joint contract")
            site = env.env.object_sites_dict[predicate[1]]
            if list(site.joints or []) != [contract["joint"]] or site.parent_name != contract["fixture"]:
                raise ValueError("official drawer site-to-joint mapping differs from the pinned contract")
            key = f"default_{predicate[0]}_ranges"
            ranges = env.env.get_object(site.parent_name).object_properties["articulation"][key]
            if not np.array_equal(ranges, contract["predicate_ranges"][predicate[0]]):
                raise ValueError("official drawer predicate range differs from the pinned contract")
            candidates = []
            for candidate in drawer_candidates(base, model, predicate[1], contract,
                                                predicate_range=ranges,
                                                predicate_range_source=f"{site.parent_name}.object_properties.articulation.{key}"):
                restore_raw_state(env, candidate["state"])
                if bool(env.env._eval_predicate(predicate)):
                    candidates.append(candidate)
            candidates = candidates[:max_candidates]
        else:
            raise ValueError(f"unsupported independent construction predicate: {predicate[0]}")
        result.append(candidates)
    restore_raw_state(env, base)
    return result


def _matched_states(base, settled, model, per_goal, candidate):
    """Transplant one settled all-goal candidate into all 2**K matched starts."""
    masks = mask_order(len(per_goal))
    if any(not candidates for candidates in per_goal):
        raise ValueError("a matched group requires nonempty goal candidate lists")
    components, occupied = [], set()
    for goal_index, candidates in enumerate(per_goal):
        indices = list(candidates[0]["allowed_indices"])
        # Supported profiles edit one fixed object/joint per goal. Do
        # not silently choose a different articulation's whitelist later.
        if any(list(item["allowed_indices"]) != indices for item in candidates):
            raise ValueError("all candidates for a goal must use the same exact whitelist")
        if occupied.intersection(indices):
            raise ValueError("goal component whitelists overlap")
        occupied.update(indices)
        values = np.asarray(settled)[indices].copy()
        components.append({"goal_index": goal_index, "indices": indices,
                           "values": values.tolist(),
                           "values_sha256": hashlib.sha256(values.astype("<f8").tobytes()).hexdigest()})
    if occupied != set(candidate["allowed_indices"]):
        raise ValueError("joint candidate whitelist differs from the per-goal components")
    states = {}
    for bits in masks:
        frozen = base.copy()
        allowed = []
        for bit, component in zip(bits, components):
            if bit == "1":
                frozen[component["indices"]] = component["values"]
                allowed.extend(component["indices"])
        audit = state_diff_whitelist(base, frozen, model, allowed)
        if not audit["valid"]:
            raise ValueError("matched construction modified a non-whitelisted coordinate")
        states[bits] = {"state": frozen, "whitelist": audit}
    # Check actual arrays, including velocities, rather than trusting metadata.
    for goal_index, component in enumerate(components):
        indices = component["indices"]
        for bits, item in states.items():
            expected = settled[indices] if bits[goal_index] == "1" else base[indices]
            if not np.array_equal(item["state"][indices], expected):
                raise ValueError("all-mask component matching failed")
    return states, components


def _audit_state(env, state, episode, output, relative, *, validation_steps,
                 velocity_tolerance, robot_tolerance):
    """Reject static failures before paying for a full dynamic audit."""
    directory = output / relative
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = CandidateAuditEnv(env, state, episode["goal_specs"], frames_dir=directory)
    kwargs = {"hold_action": HOLD, "velocity_tolerance": velocity_tolerance,
              "robot_position_tolerance": robot_tolerance, **RGB_QUANTIZATION_AUDIT}
    static = validate_candidate(wrapper, episode, steps=0, **kwargs)
    _write(directory / "static_audit.json", static)
    if not static["technical_acceptance"]:
        audit = dict(static, stage="static_rejection", requested_dynamic_steps=validation_steps)
    else:
        audit = validate_candidate(wrapper, episode, steps=validation_steps, **kwargs)
        audit["stage"] = "dynamic_validation"
    if audit["technical_acceptance"]:
        reference = save_observation_artifact(output, (relative / "initial_observation.npz").as_posix(),
                                              wrapper.initial_observation)
        if reference["observation_sha256"] != audit["trace"][0]["observation_check"]["returned_sha256"]:
            raise RuntimeError("captured initial observation differs from the selected construction audit")
        episode["initial_observation"] = reference
        audit["initial_observation"] = reference
    _write(directory / "audit.json", audit)
    return {"technical_acceptance": bool(audit["technical_acceptance"]),
            "static_acceptance": bool(static["technical_acceptance"]),
            "checks": audit["checks"], "error": audit.get("error"),
            "audit_path": (relative / "audit.json").as_posix(),
            "static_audit_path": (relative / "static_audit.json").as_posix()}


def build(output: Path, *, scenes=1, tasks="all", settle_steps=80, validation_steps=150,
          max_candidates=24, velocity_tolerance=0.01, robot_tolerance=0.002,
          split="val", start_index=0):
    from libero.libero import benchmark
    if split not in ("train", "val", "test"):
        raise ValueError("split must be train, val, or test")
    if type(start_index) is not int or start_index < 0:
        raise ValueError("start_index must be a nonnegative integer")
    if type(scenes) is not int or scenes < 1:
        raise ValueError("scenes must be a positive integer")
    selected = select_tasks(tasks)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    suites = {}
    identity = environment_identity(20)
    manifest = {"schema_version": "remaining-goals-v0.1", "environment": identity, "episodes": []}
    report = {"kind": "real_libero_candidate_construction", "toy": False,
              "builder_sources_sha256": {
                  name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                  for name in ("build.py", "construction.py", "validation.py", "task_catalog.py", "observation_artifact.py")},
              "stage": "technical_validation_pending_semantic_and_execution_review",
              "environment": identity, "scenes": scenes, "settle_steps": settle_steps,
              "split": split, "start_index": start_index,
              "split_scope": "source annotation only; cross-task independence or absence of overlap is not established by this builder",
              "validation_steps": validation_steps, "hold_action": HOLD.tolist(),
              "hold_description": "zero OSC pose delta with open gripper, only for unattended static start validation",
              "limits": {"position_tolerance": 0.005, "velocity_tolerance": velocity_tolerance,
                         "robot_position_tolerance": robot_tolerance, "penetration_tolerance": 0.002,
                         **RGB_QUANTIZATION_AUDIT},
              "observation_audit_limitation": RGB_QUANTIZATION_LIMITATION,
              "observation_audit_rule": dict(RGB_QUANTIZATION_RULE),
              "selected_tasks": selected, "task_catalog": {key: TASKS[key] for key in selected},
              "groups": []}
    try:
        for task_id in selected:
            try:
                profile = TASKS[task_id]
                suite_name = profile["suite"]
                if suite_name not in suites:
                    suites[suite_name] = benchmark.get_benchmark_dict()[suite_name]()
                suite = suites[suite_name]
                masks = mask_order(len(profile["goals"]))
                zero_bits, full_bits = masks[0], masks[-1]
                task_index = next(i for i in range(suite.n_tasks) if suite.get_task(i).name == profile["name"])
                states = _official_initial_states(suite, task_index)
                if start_index + scenes > len(states):
                    raise ValueError("requested more scenes than official initial states")
                env, task, bddl = create_scene(suite_name, profile["name"], image_size=256, control_freq=20)
                try:
                    official = [list(p) for p in env.env.parsed_problem["goal_state"]]
                    if sorted(official) != sorted(p for g in profile["goals"] for p in g["predicates"]):
                        raise ValueError("task profile does not match official goals")
                    for scene in range(start_index, start_index + scenes):
                        group = {"task_id": task_id, "suite": suite_name, "task_name": profile["name"],
                                 "goal_count": len(profile["goals"]), "required_masks": list(masks),
                                 "initial_state_index": scene, "masks": {},
                                 "joint_attempts": [], "complete": False}
                        report["groups"].append(group)
                        env.seed(scene)
                        reset_scene(env)
                        # get_xml() serializes mutable model fields, including
                        # fixture visibility. Reset identity must be captured
                        # before any candidate turns the stove on.
                        reset_xml_hash = model_xml_hash(env)
                        group["reset_model_xml_sha256"] = reset_xml_hash
                        restore_raw_state(env, np.asarray(states[scene], dtype=float))
                        for _ in range(settle_steps):
                            _step(env, HOLD)
                        base = _state(env)
                        if _goals(env, profile["goals"]) != [False] * len(profile["goals"]):
                            group["error"] = f"official settled base is not {zero_bits}"
                            continue
                        base_q = ms.get_robot_qpos(base, ms.StateLayout.from_model(env.sim.model), n=9)
                        group["base_state_array_sha256"] = hashlib.sha256(base.astype("<f8").tobytes()).hexdigest()

                        def episode_for(bits, relative):
                            episode_id = f"{task_id}_s{scene:03d}_{bits}"
                            return {
                                "episode_id": episode_id, "task_id": task_id, "suite": suite_name,
                                "libero_task_id": task_index, "task_name": task.name, "instruction": task.language,
                                "goal_specs": profile["goals"], "initial_mask": [b == "1" for b in bits],
                                "state_path": f"states/{episode_id}.npy", "source_id": f"{task_id}_official_{scene}",
                                "split": split, "initial_state_index": scene, "seed": scene,
                                "pose_id": "matched_settled_base", "horizon": 520, "retention_steps": 150,
                                "bddl_sha256": hashlib.sha256(bddl.read_bytes()).hexdigest(),
                                "model_xml_sha256": reset_xml_hash, "reference_robot_qpos": base_q.tolist(),
                                "construction": {"method": "joint_all_goals_settle_matched_component_transplant",
                                                 "legal": False, "reviewed_by": "pending_semantic_and_execution_review",
                                                 "technical_audit": (relative / "audit.json").as_posix()},
                            }

                        # The identical all-false base is audited once per source. A
                        # systematic base failure cannot be repaired by retrying
                        # 24 different completed-goal placements.
                        zero_relative = Path("validation") / f"{task_id}_s{scene:03d}_{zero_bits}" / "base"
                        zero_episode = episode_for(zero_bits, zero_relative)
                        zero_audit = _audit_state(env, base, zero_episode, output, zero_relative,
                                                  validation_steps=validation_steps,
                                                  velocity_tolerance=velocity_tolerance, robot_tolerance=robot_tolerance)
                        group["masks"][zero_bits] = {"attempted": 1, "accepted": zero_audit["technical_acceptance"],
                                                  "attempts": [zero_audit]}
                        if not zero_audit["technical_acceptance"]:
                            group["error"] = f"shared {zero_bits} base failed technical acceptance; group search stopped"
                            _write(output / "construction_report.json", report)
                            continue
                        per_goal = _per_goal(env, base, profile, max_candidates)
                        group["per_goal_candidate_counts"] = [len(x) for x in per_goal]
                        candidates = combine_goal_candidates(base, env.sim.model, per_goal, [True] * len(profile["goals"]),
                                                              max_candidates=max_candidates)
                        for bits in masks[1:]:
                            group["masks"][bits] = {"attempted": 0, "accepted": False, "attempts": []}
                        for number, candidate in enumerate(candidates):
                            # Settle one all-goal candidate. Every mask takes the
                            # same completed-goal components from this exact state.
                            restore_raw_state(env, candidate["state"])
                            for _ in range(settle_steps):
                                _step(env, HOLD)
                            settled = _state(env)
                            matched, components = _matched_states(base, settled, env.sim.model, per_goal, candidate)
                            trial = {"joint_candidate": number, "construction": candidate["diagnostics"],
                                     "selected_components": components, "components_exactly_matched": True,
                                     "masks": {}, "accepted": False}
                            group["joint_attempts"].append(trial)
                            group_episodes = [zero_episode]
                            for bits in masks[1:]:
                                entry = group["masks"][bits]
                                entry["attempted"] += 1
                                episode_id = f"{task_id}_s{scene:03d}_{bits}"
                                relative = Path("validation") / episode_id / f"joint_candidate_{number:03d}"
                                episode = episode_for(bits, relative)
                                frozen = matched[bits]["state"]
                                acceptance = _audit_state(env, frozen, episode, output, relative,
                                                           validation_steps=validation_steps,
                                                           velocity_tolerance=velocity_tolerance,
                                                           robot_tolerance=robot_tolerance)
                                attempt = {"joint_candidate": number, "whitelist": matched[bits]["whitelist"],
                                           **acceptance}
                                entry["attempts"].append(attempt)
                                trial["masks"][bits] = attempt
                                if not acceptance["technical_acceptance"]:
                                    print(f"{episode_id} joint candidate {number}: failed {acceptance['checks']}", flush=True)
                                    break
                                group_episodes.append(episode)
                            if len(group_episodes) == len(masks):
                                # No survivor is exported until all its partners
                                # pass. The saved arrays are the audited starts.
                                for bits, episode in zip(masks, group_episodes):
                                    episode["construction"].update(joint_candidate=number,
                                                                     selected_components=components,
                                                                     components_exactly_matched=True)
                                    state_path = output / episode["state_path"]
                                    state_path.parent.mkdir(exist_ok=True)
                                    np.save(state_path, matched[bits]["state"])
                                    episode["state_sha256"] = hashlib.sha256(state_path.read_bytes()).hexdigest()
                                    group["masks"][bits].update(accepted=True, selected_joint_candidate=number,
                                                                state_path=episode["state_path"],
                                                                audit_path=episode["construction"]["technical_audit"])
                                trial["accepted"] = True
                                group.update(complete=True, selected_joint_candidate=number,
                                             selected_components=components, components_exactly_matched=True)
                                manifest["episodes"].extend(group_episodes)
                                print(f"{task_id}_s{scene:03d}: all {len(masks)} masks passed from joint candidate {number}", flush=True)
                            _write(output / "construction_report.json", report)
                            if group["complete"]:
                                break
                        if not candidates:
                            group["error"] = f"no compatible joint {full_bits} construction candidates"
                finally:
                    env.close()
            except Exception as error:
                reason = f"{type(error).__name__}: {error}"
                report.setdefault("task_errors", []).append({"task_id": task_id, "error": reason})
                existing = {item["initial_state_index"]: item for item in report["groups"]
                            if item["task_id"] == task_id}
                for scene in range(start_index, start_index + scenes):
                    group = existing.get(scene)
                    if group is None:
                        group = {"task_id": task_id, "suite": TASKS[task_id]["suite"],
                                 "initial_state_index": scene, "masks": {},
                                 "joint_attempts": [], "complete": False}
                        report["groups"].append(group)
                    if not group["complete"]:
                        group["error"] = reason
                        group["failure_stage"] = "task_runtime_error"
                _write(output / "construction_report.json", report)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["complete_groups"] = sum(group["complete"] for group in report["groups"])
        report["candidate_episodes"] = len(manifest["episodes"])
        _write(output / "construction_report.json", report)
        manifest["content_hash"] = manifest_hash(manifest)
        _write(output / "manifest.candidates.json", manifest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scenes", default=1, type=int)
    parser.add_argument("--split", choices=("train", "val", "test"), default="val",
                        help="Source annotation; construction development should use val (default)")
    parser.add_argument("--start-index", default=0, type=int, help="First official initial-state index")
    parser.add_argument("--tasks", default="all", help="all/primary for six libero_10 tasks; extension for four libero_90 tasks; or comma-separated keys from one suite: " + ", ".join(TASKS))
    parser.add_argument("--settle-steps", default=80, type=int)
    parser.add_argument("--validation-steps", default=150, type=int)
    parser.add_argument("--max-candidates", default=24, type=int)
    parser.add_argument("--velocity-tolerance", default=0.01, type=float)
    parser.add_argument("--robot-tolerance", default=0.002, type=float)
    args = parser.parse_args(argv)
    if min(args.scenes, args.settle_steps, args.validation_steps, args.max_candidates) < 1:
        parser.error("counts must be positive")
    if args.start_index < 0:
        parser.error("start-index must be nonnegative")
    report = build(args.out, scenes=args.scenes, tasks=args.tasks, settle_steps=args.settle_steps,
                   validation_steps=args.validation_steps, max_candidates=args.max_candidates,
                   velocity_tolerance=args.velocity_tolerance, robot_tolerance=args.robot_tolerance,
                   split=args.split, start_index=args.start_index)
    if report["complete_groups"] != len(report["groups"]):
        raise SystemExit("Some groups failed technical acceptance; inspect construction_report.json")


if __name__ == "__main__":
    main()
