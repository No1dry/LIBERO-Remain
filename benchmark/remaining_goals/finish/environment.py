"""Basket-only FINISH evaluator and latched Panda OSC hold.

Nothing here imports or starts LIBERO at module import. Real construction,
restoration and hold validation are user-run operations, never CPU-test setup.
The release test is deliberately conservative: absence of a dual-pad grasp
alone is insufficient proof that an object has been released.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from ..libero_env import (LiberoGoalEnv, create_scene, environment_identity, fresh_observation,
                         model_xml_hash, restore_raw_state, _task_environment, _predicate,
                         _restore_quaternion_roundoff, _require_exact_state)
from ..libero_compat import reset_scene
from ..task_catalog import TASKS

HOLD_VERSION = "panda-fixed-osc-latched-pose-gripper-zero-v1"
RELEASE_VERSION = "panda-dualpad-contact-and-conservative-pinch-clearance-v1"
TARGETS = ("alphabet_soup_1", "tomato_sauce_1")
REGION = "basket_1_contain_region"
CONTAINER = "basket_1"
CLEARANCE = 0.002  # engineering geometry margin, not a learned/test-tuned threshold


def _state(env):
    return np.asarray(env.sim.get_state().flatten(), dtype=np.float64).copy()


def _finite(value, shape, name):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"invalid {name}")
    return array.copy()


def _rotation(value):
    matrix = _finite(value, (3, 3), "end-effector rotation")
    if not np.allclose(matrix.T @ matrix, np.eye(3), rtol=0, atol=1e-7) or abs(np.linalg.det(matrix) - 1) > 1e-7:
        raise ValueError("end-effector orientation is not a proper rotation")
    return matrix


def _axis_angle(matrix):
    matrix = _rotation(matrix)
    angle = math.acos(float(np.clip((np.trace(matrix) - 1) / 2, -1, 1)))
    skew = np.array([matrix[2, 1] - matrix[1, 2], matrix[0, 2] - matrix[2, 0], matrix[1, 0] - matrix[0, 1]])
    if angle < 1e-8:
        return skew / 2
    if math.pi - angle < 1e-6:
        # The symmetric rotation has eigenvalue +1 along its rotation axis.
        values, vectors = np.linalg.eigh((matrix + matrix.T) / 2)
        axis = vectors[:, int(np.argmax(values))]
        if np.linalg.norm(skew) > 1e-12:
            axis *= 1 if np.dot(axis, skew) >= 0 else -1
        elif axis[int(np.argmax(np.abs(axis)))] < 0:
            axis *= -1
        return axis * angle
    return skew * (angle / (2 * math.sin(angle)))


def _robot_contract(env):
    robots = getattr(env, "robots", None)
    if not isinstance(robots, (list, tuple)) or len(robots) != 1:
        raise RuntimeError("FINISH hold supports exactly one Panda robot")
    robot = robots[0]
    gripper, controller = getattr(robot, "gripper", None), getattr(robot, "controller", None)
    if (getattr(getattr(robot, "robot_model", None), "__class__", type(None)).__name__ != "Panda"
            or type(gripper).__name__ != "PandaGripper" or getattr(gripper, "dof", None) != 1
            or getattr(gripper, "speed", None) != .01):
        raise RuntimeError("unsupported Panda/gripper incremental-action contract")
    current = _finite(gripper.current_action, (2,), "Panda current_action")
    if np.any(np.abs(current) > 1):
        raise RuntimeError("Panda current_action is outside its contract")
    if (getattr(controller, "name", None) != "OSC_POSE" or getattr(controller, "impedance_mode", None) != "fixed"
            or getattr(controller, "control_dim", None) != 6 or getattr(controller, "use_delta", None) is not True
            or getattr(controller, "use_ori", None) is not True):
        raise RuntimeError("FINISH hold requires fixed-impedance 6D delta OSC_POSE")
    for field in ("position_limits", "orientation_limits", "interpolator_pos", "interpolator_ori"):
        if getattr(controller, field, None) is not None:
            raise RuntimeError(f"FINISH hold does not claim support for {field}")
    if not callable(getattr(controller, "update", None)) or not callable(getattr(controller, "set_goal", None)):
        raise RuntimeError("OSC hold requires update and explicit pose-goal control")
    limits = {name: _finite(getattr(controller, name), (6,), name)
              for name in ("input_min", "input_max", "output_min", "output_max")}
    if np.any(limits["input_max"] <= limits["input_min"]) or np.any(limits["output_max"] <= limits["output_min"]):
        raise RuntimeError("OSC action scaling ranges must be nondegenerate and ordered")
    return controller, gripper, limits


class PandaPoseHold:
    """Latch exit pose once; correct pose drift without changing gripper target.

    Upstream OSC maps deltaR @ currentR to its orientation goal. Inverting the
    documented affine scale_action therefore uses axisangle(refR @ currentR.T).
    Panda's incremental gripper uses sign(action): zero preserves current_action.
    This contract is not an empirical stability guarantee.
    """
    def __init__(self, env):
        self.env = env
        self.controller, self.gripper, self.limits = _robot_contract(env)
        self.reference_pos = self.reference_ori = self.gripper_target = None

    def _update(self):
        before = _state(self.env)
        self.controller.update(force=True)
        _restore_quaternion_roundoff(self.env, before, phase="FINISH hold controller refresh")
        _require_exact_state(before, _state(self.env), "FINISH hold controller refresh")

    def begin(self):
        if self.reference_pos is not None:
            raise RuntimeError("physical exit hold may be latched only once")
        self._update()
        self.reference_pos = _finite(self.controller.ee_pos, (3,), "exit end-effector position")
        self.reference_ori = _rotation(self.controller.ee_ori_mat)
        self.gripper_target = _finite(self.gripper.current_action, (2,), "exit gripper target")
        before = _state(self.env)
        # A zero rotation alone would leave the previous OSC orientation goal.
        self.controller.set_goal(np.zeros(6), set_pos=self.reference_pos.copy(), set_ori=self.reference_ori.copy())
        _restore_quaternion_roundoff(self.env, before, phase="FINISH hold goal latch")
        _require_exact_state(before, _state(self.env), "FINISH hold goal latch")
        return {"version": HOLD_VERSION, "controller": "OSC_POSE", "impedance": "fixed", "frame": "world",
                "reference_position": self.reference_pos.tolist(), "reference_orientation": self.reference_ori.tolist(),
                "gripper_command": 0.0, "gripper_current_action": self.gripper_target.tolist(),
                "input_min": self.limits["input_min"].tolist(), "input_max": self.limits["input_max"].tolist(),
                "output_min": self.limits["output_min"].tolist(), "output_max": self.limits["output_max"].tolist(),
                "clipping": "controller input bounds; no goal truth is read", "empirical_stability_validated": False}

    def action(self):
        if self.reference_pos is None:
            raise RuntimeError("begin_hold must precede hold actions")
        self._update()
        if not np.array_equal(self.gripper.current_action, self.gripper_target):
            raise RuntimeError("Panda gripper command state changed during physical hold")
        position = _finite(self.controller.ee_pos, (3,), "current end-effector position")
        orientation = _rotation(self.controller.ee_ori_mat)
        delta = np.concatenate([self.reference_pos - position, _axis_angle(self.reference_ori @ orientation.T)])
        low, high = self.limits["input_min"], self.limits["input_max"]
        output_low, output_high = self.limits["output_min"], self.limits["output_max"]
        scale = (output_high - output_low) / (high - low)
        command = (delta - (output_high + output_low) / 2) / scale + (high + low) / 2
        return np.concatenate([np.clip(command, low, high), [0.]])


def _geom_spheres(env, names):
    if not isinstance(names, (list, tuple)) or not names:
        raise ValueError("collision geometry names are missing")
    points, radii = [], []
    for name in names:
        if not isinstance(name, str) or not name:
            raise ValueError("invalid collision geometry name")
        index = int(env.sim.model.geom_name2id(name))
        if index < 0:
            raise ValueError("collision geometry name is absent from compiled model")
        points.append(_finite(env.sim.data.geom_xpos[index], (3,), "collision geometry position"))
        radius = float(env.sim.model.geom_rbound[index])
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("collision geometry bounding radius is unavailable")
        radii.append(radius)
    return np.array(points), np.array(radii)


def _release(env, inner, gripper, obj):
    evidence = {"method": RELEASE_VERSION, "clearance_margin_m": CLEARANCE,
                "dual_pad_grasp": None, "any_gripper_contact": None,
                "hand_sphere_clearance_m": None, "pinch_capsule_clearance_m": None}
    try:
        geoms = list(obj.contact_geoms)
        hand_geoms = list(gripper.contact_geoms)
        grasp = inner._check_grasp(gripper, geoms)
        contact = inner.check_contact(hand_geoms, geoms)
        if not isinstance(grasp, (bool, np.bool_)) or not isinstance(contact, (bool, np.bool_)):
            raise ValueError("grasp/contact detector did not return booleans")
        evidence.update(dual_pad_grasp=bool(grasp), any_gripper_contact=bool(contact))
        if grasp:
            evidence["reason"] = "both_fingerpads_contact_object"
            return False, evidence
        if contact:
            evidence["reason"] = "gripper_contact_without_proven_dualpad_grasp"
            return None, evidence
        points, radii = _geom_spheres(env, geoms)
        hand, hand_radii = _geom_spheres(env, hand_geoms)
        separation = np.linalg.norm(points[:, None] - hand[None, :], axis=2) - radii[:, None] - hand_radii[None, :]
        clearance = float(np.min(separation))
        pads = gripper.important_geoms
        left, lr = _geom_spheres(env, pads["left_fingerpad"])
        right, rr = _geom_spheres(env, pads["right_fingerpad"])
        a, b = left.mean(axis=0), right.mean(axis=0)
        axis = b - a
        length2 = float(axis @ axis)
        if length2 <= 1e-12:
            raise ValueError("fingerpad segment is degenerate")
        pad_radius = max(float(np.max(np.linalg.norm(left - a, axis=1) + lr)),
                         float(np.max(np.linalg.norm(right - b, axis=1) + rr)))
        fraction = np.clip((points - a) @ axis / length2, 0, 1)
        closest = a + fraction[:, None] * axis
        pinch_clearance = float(np.min(np.linalg.norm(points - closest, axis=1) - radii - pad_radius))
        evidence.update(hand_sphere_clearance_m=clearance, pinch_capsule_clearance_m=pinch_clearance)
        released = clearance > CLEARANCE and pinch_clearance > CLEARANCE
        evidence["reason"] = "no_contact_and_clear_of_hand_and_pinch_envelope" if released else "near_hand_or_inside_pinch_envelope"
        return (True if released else None), evidence
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, RuntimeError) as error:
        evidence.update(reason="release_evidence_unavailable", error=f"{type(error).__name__}: {error}")
        return None, evidence


class BasketContract:
    """Evaluator-only physical facts for the fixed two-object basket task."""
    def __init__(self, env):
        self.env, self.inner = env, _task_environment(env)
        official = sorted(_predicate(p) for p in self.inner.parsed_problem["goal_state"])
        expected = sorted(("in", name, REGION) for name in TARGETS)
        if official != expected:
            raise ValueError("FINISH-v1 environment supports only the fixed soup/sauce basket task")
        objects = getattr(self.inner, "objects_dict", None)
        fixtures = getattr(self.inner, "fixtures_dict", None)
        if not isinstance(objects, dict) or not set((*TARGETS, CONTAINER)).issubset(objects) or not isinstance(fixtures, dict):
            raise ValueError("basket scene object/fixture inventory is incomplete")
        if not all(getattr(objects[name], "joints", None) for name in TARGETS):
            raise ValueError("target objects must be movable physical objects")
        if set(objects).intersection(fixtures):
            raise ValueError("ambiguous scene object roles")
        self.objects, self.fixtures = objects, fixtures
        self.hold = PandaPoseHold(env)
        self.gripper = self.hold.gripper

    def evaluator_state(self):
        facts = {}
        for name, obj in {**self.objects, **self.fixtures}.items():
            role = ("target" if name in TARGETS else "container" if name == CONTAINER else
                    "fixture" if name in self.fixtures or not getattr(obj, "joints", None) else "distractor")
            if role in {"target", "distractor"}:
                in_basket = self.inner._eval_predicate(["in", name, REGION])
                if not isinstance(in_basket, (bool, np.bool_)):
                    raise RuntimeError("basket membership predicate returned no physical truth")
                released, release = _release(self.env, self.inner, self.gripper, obj)
                facts[name] = {"role": role, "in_basket": bool(in_basket), "released": released, "release_evidence": release}
            else:
                facts[name] = {"role": role, "in_basket": None, "released": None,
                               "release_evidence": {"method": RELEASE_VERSION, "reason": "excluded_container_or_fixture_role"}}
        states = [facts[name]["released"] for name in TARGETS]
        released = False if any(value is False for value in states) else True if all(value is True for value in states) else None
        return {"goals": [facts[name]["in_basket"] for name in TARGETS], "released": released, "objects": facts,
                "release_evidence": {"method": RELEASE_VERSION, "targets": {name: facts[name]["release_evidence"] for name in TARGETS}}}


class FinishLiberoEnv(LiberoGoalEnv):
    def __init__(self, config):
        if "hold_action" in config or "hold_contract" in config:
            raise ValueError("FINISH requires its versioned physical hold, not a constant-action override")
        super().__init__(config)
        self.finish_contract = None

    def reset(self, episode):
        self.finish_contract = None
        profile = TASKS["basket"]
        if episode.get("suite") != profile["suite"] or episode.get("task_name") != profile["name"]:
            raise ValueError("FINISH-v1 only supports the fixed LIBERO-10 basket task")
        observation = super().reset(episode)
        self.finish_contract = BasketContract(self.env)
        return observation

    def evaluator_state(self):
        if not self._ready or self.finish_contract is None:
            raise RuntimeError("successful FINISH reset is required")
        truth = self.finish_contract.evaluator_state()
        # Preserve source group order; the contract's target identities are fixed.
        truth["goals"] = self.goal_values()
        return truth

    def begin_hold(self):
        if not self._ready or self.finish_contract is None:
            raise RuntimeError("successful FINISH reset is required")
        return self.finish_contract.hold.begin()

    def hold_action(self):
        if not self._ready or self.finish_contract is None:
            raise RuntimeError("successful FINISH reset is required")
        return self.finish_contract.hold.action()

    def close(self):
        self.finish_contract = None
        super().close()


def make_env(config):
    return FinishLiberoEnv(config)


def _layout(model):
    result = {key: int(getattr(model, key)) for key in ("nq", "nv", "nu", "nbody", "ngeom", "nsite", "njnt")}
    for kind, count in (("joint", "njnt"), ("body", "nbody"), ("geom", "ngeom"), ("site", "nsite"), ("actuator", "nu")):
        convert = getattr(model, kind + "_id2name")
        result[kind + "_names"] = [convert(index) for index in range(result[count])]
    for key in ("jnt_type", "jnt_qposadr", "jnt_dofadr", "body_parentid", "geom_bodyid", "site_bodyid",
                "actuator_trnid", "actuator_trntype"):
        result[key] = np.asarray(getattr(model, key)).tolist()
    return result


def _processed_demo_xml(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("demonstration model_xml must contain actual XML text")
    from libero.libero.envs.utils import postprocess_model_xml
    import libero.libero as package
    previous = Path.cwd()
    try:
        # Official helper builds its LIBERO asset root from cwd + '/libero'.
        os.chdir(Path(package.__file__).resolve().parent.parent)
        processed = postprocess_model_xml(text, demo_generation=True)
    finally:
        os.chdir(previous)
    tree = ET.fromstring(processed)
    for element in tree.findall("./asset/*"):
        path = element.get("file")
        if path is not None and not Path(path).is_file():
            raise ValueError(f"demonstration XML references an unavailable asset: {path}")
    return processed


class DemonstrationAuditProvider:
    """User-run native restoration and isolated passive-label confirmation.

    Uses the demonstration's actual XML when supplied. A changed scene/layout
    fails explicitly; it is never silently replayed against the default model.
    """
    def __init__(self, config):
        if not isinstance(config, dict):
            raise ValueError("data provider requires a configuration dictionary")
        profile = TASKS["basket"]
        if config.get("task_key", "basket") != "basket":
            raise ValueError("FINISH data audit supports only basket")
        for name, fixed in (("image_size", 256), ("control_freq", 20)):
            if type(config.get(name, fixed)) is not int or config.get(name, fixed) != fixed:
                raise ValueError(f"FINISH data audit requires {name}={fixed}")
        self.env = None
        self.contract = None
        self._active_source_xml = None
        self._model_valid = False
        try:
            self.env, task, bddl = create_scene(profile["suite"], profile["name"], image_size=256, control_freq=20)
            source_bddl = Path(config["bddl_path"])
            if not source_bddl.is_file() or source_bddl.read_bytes() != bddl.read_bytes():
                raise ValueError("data BDDL differs from the fixed official basket task")
            if config.get("original_instruction") != task.language or task.name != profile["name"]:
                raise ValueError("data instruction differs from the actual official BDDL language")
            seed = config.get("env_seed", 0)
            if type(seed) is not int or seed < 0:
                raise ValueError("data audit environment seed must be nonnegative")
            self.env.seed(seed)
            reset_scene(self.env)
            self.contract = BasketContract(self.env)
            self._base_layout = _layout(self.env.sim.model)
            self._base_xml = self.env.sim.model.get_xml()
            if isinstance(self._base_xml, bytes):
                self._base_xml = self._base_xml.decode("utf-8")
            self._model_valid = True
            self.metadata = {"provider_version": "basket-native-passive-label-provider-v1", "task_name": task.name,
                             "instruction": task.language, "bddl_sha256": hashlib.sha256(bddl.read_bytes()).hexdigest(),
                             "environment": environment_identity(20), "hold_version": HOLD_VERSION,
                             "release_version": RELEASE_VERSION, "environment_seed": seed,
                             "backend": "LIBERO/robosuite", "scope": "user-invoked data audit, not model evaluation",
                             "real_correctness_certified": False}
        except BaseException:
            self.close()
            raise

    def _model(self, source_xml):
        if source_xml is not None and (not isinstance(source_xml, str) or not source_xml.strip()):
            raise ValueError("invalid demonstration XML")
        if source_xml == self._active_source_xml and self._model_valid:
            return
        text = self._base_xml if source_xml is None else _processed_demo_xml(source_xml)
        self._model_valid = False
        self.env.reset_from_xml_string(text)
        if _layout(self.env.sim.model) != self._base_layout:
            raise ValueError("demonstration XML changed basket scene inventory or saved-state joint/layout identity")
        self.contract = BasketContract(self.env)
        self._active_source_xml = source_xml
        self._model_valid = True

    def _truth(self):
        truth = self.contract.evaluator_state()
        truth["release_evidence"].update(current_model_xml_sha256=model_xml_hash(self.env),
            source_xml_sha256=(hashlib.sha256(self._active_source_xml.encode()).hexdigest() if self._active_source_xml else None))
        return truth

    def restore_demonstration(self, state, model_xml=None):
        if self.env is None:
            raise RuntimeError("data provider is closed")
        if not isinstance(model_xml, str) or not model_xml.strip():
            raise ValueError("insufficient demonstration identity: actual trajectory model_xml is required")
        self._model(model_xml)
        observation = restore_raw_state(self.env, state)
        # Every independent restored state needs a fresh pose-hold latch.
        self.contract = BasketContract(self.env)
        truth = self._truth()
        return {"observation": observation, "goals": truth["goals"], "released": truth["released"],
                "release_evidence": truth["release_evidence"]}

    def capture_hold_label(self, state, steps, model_xml=None):
        from .data import state_sha256
        if type(steps) is not int or steps < 1:
            raise ValueError("passive label confirmation needs a positive step count")
        if self.env is None:
            raise RuntimeError("data provider is closed")
        if not isinstance(model_xml, str) or not model_xml.strip():
            raise ValueError("insufficient demonstration identity: actual trajectory model_xml is required")
        previous_state, previous_xml = _state(self.env), self._active_source_xml
        try:
            initial = self.restore_demonstration(state, model_xml=model_xml)
            trace = [{"step": 0, **{key: deepcopy(initial[key]) for key in ("goals", "released", "release_evidence")}}]
            contract = self.contract.hold.begin()
            for step in range(1, steps + 1):
                action = self.contract.hold.action()
                # Native done guards do not stop physical label confirmation.
                for holder in (self.env, self.contract.inner):
                    if "done" in vars(holder):
                        holder.done = False
                self.env.step(action.tolist())
                fresh_observation(self.env)
                truth = self._truth()
                trace.append({"step": step, **{key: deepcopy(truth[key]) for key in ("goals", "released", "release_evidence")}})
            return {"source_state_sha256": state_sha256(state), "hold_contract": contract, "trace": trace}
        finally:
            self._model(previous_xml)
            restore_raw_state(self.env, previous_state)
            self.contract = BasketContract(self.env)
            _require_exact_state(previous_state, _state(self.env), "passive label branch restoration")

    def close(self):
        env, self.env = self.env, None
        self.contract = None
        if env is not None:
            env.close()


def make_audit_provider(config):
    return DemonstrationAuditProvider(config)
