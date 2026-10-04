"""LIBERO bridge with evaluator-only predicates and explicit state restoration.

LIBERO is imported lazily. This bridge needs acceptance checks in the actual
Linux simulation environment before producing research results.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
from pathlib import Path

import numpy as np

from .schema import verify_state_file
from .libero_compat import apply_libero_compat, compatibility_identity, reset_scene

OBSERVATION_KEYS = (
    "agentview_image", "robot0_eye_in_hand_image", "robot0_eef_pos",
    "robot0_eef_quat", "robot0_gripper_qpos", "robot0_joint_pos", "robot0_joint_vel",
)


def environment_identity(control_freq: int = 20) -> dict:
    """Lock simulator versions, LIBERO sources and actual asset file contents.

    Asset paths and bytes are hashed from this installation, independently of
    an installer profile. Python bytecode/cache artifacts are excluded. Task
    XML hashes separately lock the generated scene and its model topology.
    """
    import libero.libero as libero_package

    root = Path(libero_package.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.suffix in (".py", ".bddl")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    assets_root = root / "assets"
    assets_digest = hashlib.sha256()
    assets = [path for path in assets_root.rglob("*") if path.is_file()
              and "__pycache__" not in path.relative_to(assets_root).parts
              and path.suffix.lower() not in (".pyc", ".pyo")]
    for path in sorted(assets, key=lambda item: item.relative_to(assets_root).as_posix()):
        file_digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                file_digest.update(block)
        assets_digest.update(path.relative_to(assets_root).as_posix().encode("utf-8") + b"\0")
        assets_digest.update(file_digest.digest())
    versions = {}
    for package in ("robosuite", "mujoco-py", "mujoco"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    lock = {"source_sha256": digest.hexdigest(), "assets_sha256": assets_digest.hexdigest(), "versions": versions,
            "control_freq": control_freq, "compatibility": compatibility_identity()}
    fingerprint = hashlib.sha256(json.dumps(lock, sort_keys=True).encode()).hexdigest()
    return {"name": "libero", "fingerprint": fingerprint, "lock": lock}


def _chain(env):
    seen = set()
    while env is not None and id(env) not in seen:
        seen.add(id(env))
        yield env
        env = getattr(env, "env", None)


def _observation(raw: dict) -> dict:
    # Do not expose object-state arrays, reward, predicates or environment info.
    # Preserve raw LIBERO camera orientation and colors; model adapters own any
    # image flipping, resizing, cropping, and normalization.
    result = {key: np.array(raw[key], copy=True) for key in OBSERVATION_KEYS if key in raw}
    required = {"agentview_image", "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"}
    if not required.issubset(result):
        raise RuntimeError(f"missing policy observation keys: {sorted(required - result.keys())}")
    return result


def _predicate(predicate) -> tuple[str, ...]:
    if (not isinstance(predicate, (list, tuple)) or len(predicate) not in (2, 3)
            or any(not isinstance(token, str) or not token for token in predicate)):
        raise ValueError("official LIBERO predicates must be flat unary/binary string lists")
    return (predicate[0].lower(), *predicate[1:])


def _new_scene(bddl_path: Path, *, image_size: int, control_freq: int):
    for name, value in (("image_size", image_size), ("control_freq", control_freq)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    from libero.libero.envs import OffScreenRenderEnv

    apply_libero_compat()
    return OffScreenRenderEnv(
        bddl_file_name=str(bddl_path), camera_heights=image_size,
        camera_widths=image_size, control_freq=control_freq,
    )


def create_scene(suite: str, task_name: str, *, image_size: int = 256,
                 control_freq: int = 20) -> tuple:
    """Create an official scene by suite/name, without a frozen manifest.

    Returns ``(native_env, official_task, bddl_path)``. The caller owns close,
    seed/reset, official initial-state selection, and physical legality review.
    This uses the default official suite ordering; callers recording numeric
    task IDs must resolve the name in that same ordering.
    """
    if not isinstance(suite, str) or not suite.strip():
        raise ValueError("suite must be a nonempty string")
    if not isinstance(task_name, str) or not task_name.strip():
        raise ValueError("task_name must be a nonempty string")
    from libero.libero import benchmark, get_libero_path

    suites = benchmark.get_benchmark_dict()
    if suite not in suites:
        raise ValueError(f"unknown LIBERO suite {suite!r}")
    task_suite = suites[suite]()
    names = task_suite.get_task_names()
    matching = [index for index, name in enumerate(names) if name == task_name]
    if len(matching) != 1:
        raise ValueError(f"task name {task_name!r} must occur exactly once in suite {suite!r}")
    task = task_suite.get_task(matching[0])
    if task.name != task_name:
        raise ValueError("official task name/index mapping is inconsistent")
    bddl_path = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    if not bddl_path.is_file():
        raise ValueError(f"official task BDDL file is missing: {bddl_path}")
    env = _new_scene(bddl_path, image_size=image_size, control_freq=control_freq)
    return env, task, bddl_path


def model_xml_hash(env) -> str:
    """Hash exact current ``sim.model.get_xml()`` bytes (UTF-8 for strings).

    This deliberately retains absolute asset paths and all formatting for
    compatibility with existing state packages. Build and evaluate in the same
    frozen runtime/install location; a moved installation must be revalidated,
    not silently accepted by stripping paths. XML hashes identify model text,
    not the contents of separately referenced mesh or texture files.
    """
    xml = env.sim.model.get_xml()
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    if not isinstance(xml, bytes):
        raise ValueError("model.get_xml() must return text or bytes")
    return hashlib.sha256(xml).hexdigest()


def _task_environment(env):
    inner = next((holder for holder in _chain(env)
                  if hasattr(holder, "parsed_problem")
                  and callable(getattr(holder, "_eval_predicate", None))), None)
    if inner is None:
        raise RuntimeError("cannot locate official LIBERO goal_state / predicate evaluator")
    return inner


def _state_bits(state):
    # MuJoCo's flattened physical state is float64. Compare its representation,
    # including signed zero, rather than using a whole-state tolerance.
    return np.ascontiguousarray(state, dtype=np.float64).view(np.uint64)


def _require_exact_state(reference, current, phase):
    if reference.shape != current.shape:
        raise RuntimeError(f"{phase} changed simulator state: shape differs")
    changed = np.flatnonzero(_state_bits(reference) != _state_bits(current))
    if changed.size:
        delta = np.max(np.abs(reference - current))
        raise RuntimeError(f"{phase} changed simulator state: indices={changed.tolist()}, max_abs_delta={delta}")


def _restore_quaternion_roundoff(env, reference, *, phase):
    """Undo only float64 unit-quaternion normalization roundoff from forward.

    robosuite 1.4's state layout is [time, qpos, qvel], with na == 0.
    MuJoCo can normalize free/ball joint quaternions in place during forward,
    including controller.update(force=True). Identify those slots from model
    topology; all other state bits must match exactly. Validate every affected
    quaternion before writing any original qpos bits back. This does not accept
    materially nonunit quaternions or normalize a saved state on the caller's
    behalf. Derived physics remains the result of the completed forward call.
    """
    current = np.asarray(env.sim.get_state().flatten(), dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if current.shape != reference.shape:
        _require_exact_state(reference, current, phase)
    changed = np.flatnonzero(_state_bits(reference) != _state_bits(current))
    if not changed.size:
        return

    # On any unsupported layout or inadmissible change, retain the original
    # exact-state error with changed indices, rather than silently tolerating it.
    def reject():
        _require_exact_state(reference, current, phase)

    model = env.sim.model
    try:
        nq, nv, na, njnt = (int(getattr(model, key)) for key in ("nq", "nv", "na", "njnt"))
        types = np.asarray(model.jnt_type)
        addresses = np.asarray(model.jnt_qposadr)
        qpos = env.sim.data.qpos
    except (AttributeError, TypeError, ValueError):
        reject()
        return
    if (na != 0 or reference.shape != (1 + nq + nv,)
            or types.shape != (njnt,) or addresses.shape != (njnt,)
            or np.asarray(qpos).shape != (nq,)):
        reject()
    groups = []
    for kind, address in zip(types, addresses):
        # MuJoCo mjJNT_FREE == 0; mjJNT_BALL == 1.
        if kind not in (0, 1):
            continue
        start = int(address) + (3 if kind == 0 else 0)
        if start < 0 or start + 4 > nq:
            reject()
        groups.append(np.arange(1 + start, 1 + start + 4))
    allowed = np.concatenate(groups) if groups else np.array([], dtype=int)
    if not np.isin(changed, allowed).all():
        reject()

    affected = [slots for slots in groups if np.isin(changed, slots).any()]
    tolerance = 16 * np.finfo(np.float64).eps
    for slots in affected:
        before_q, after_q = reference[slots], current[slots]
        before_norm, after_norm = np.linalg.norm(before_q), np.linalg.norm(after_q)
        if (not np.isfinite(before_q).all() or not np.isfinite(after_q).all()
                or abs(before_norm - 1) > tolerance or abs(after_norm - 1) > tolerance
                or np.max(np.abs(before_q - after_q)) > tolerance
                or np.linalg.norm(before_q / before_norm - after_q / after_norm) > tolerance):
            reject()
    for slots in affected:
        qpos[slots - 1] = reference[slots]
    _require_exact_state(reference, np.asarray(env.sim.get_state().flatten()), phase)


def fresh_observation(env) -> dict:
    """Synchronize derived physics, visuals and observations without stepping.

    Forward first, then follow ControlEnv.regenerate_obs_from_state's hooks.
    Native step observations can be cached from an earlier internal timestep;
    this explicit protocol always samples the current completed physical step.
    Returns copied policy-only observations, in raw LIBERO image orientation.
    Only unit-quaternion roundoff caused by forward is restored to its original
    bits; no flattened physics state may remain changed, including time. Call this
    after a real step to audit its current state, without restoring an earlier
    state or resetting its controller. Like other native simulator operations,
    this helper must not run concurrently with stepping the same environment.
    """
    inner = _task_environment(env)
    hooks = ("_post_process", "_update_observables", "_get_observations")
    if any(not callable(getattr(inner, hook, None)) for hook in hooks):
        raise RuntimeError("official LIBERO non-stepping observation refresh hooks are missing")
    check_success = getattr(env, "check_success", None)
    if not callable(check_success):
        check_success = getattr(inner, "_check_success", None)
    if not callable(check_success):
        raise RuntimeError("official LIBERO success refresh hook is missing")
    if not callable(getattr(env.sim, "forward", None)):
        raise RuntimeError("official LIBERO non-stepping forward hook is missing")
    before = np.asarray(env.sim.get_state().flatten()).copy()
    env.sim.forward()
    phase = "non-stepping observation refresh"
    _restore_quaternion_roundoff(env, before, phase=phase)
    check_success()
    inner._post_process()
    inner._update_observables(force=True)
    raw = inner._get_observations()
    after = np.asarray(env.sim.get_state().flatten())
    _require_exact_state(before, after, phase)
    return _observation(raw)


def _synchronize_grippers(env, robots):
    """Reanchor Panda's incremental command to its restored finger positions.

    PandaGripper.current_action is Python state, absent from MjSimState. A new
    gripper starts at zero even when restored qpos is open; its first action
    would otherwise command a half-closed target. Invert Manipulator.grip_action
    using the compiled position actuator ranges. Only the verified Panda/unit
    joint transmission/position-servo contract is supported. Saturate command
    targets to their control limits without altering physical qpos, since
    MuJoCo soft joint limits can permit positions outside those limits.
    Neither format_action nor simulation stepping belongs in restoration.
    """
    prepared = []
    for robot in robots:
        gripper = getattr(robot, "gripper", None)
        if gripper is None:
            if getattr(robot, "has_gripper", False):
                raise RuntimeError("unsupported restored gripper contract: missing gripper")
            continue  # Explicitly gripper-free robots and controller-only fakes.
        if getattr(robot, "has_gripper", True) is False:
            continue
        from robosuite.models.grippers.panda_gripper import PandaGripper

        if type(gripper) is not PandaGripper or gripper.dof != 1 or gripper.speed != .01:
            raise RuntimeError("unsupported restored gripper contract: expected official PandaGripper")
        model, data = env.sim.model, env.sim.data
        try:
            joints, actuators = list(gripper.joints), list(gripper.actuators)
            if len(joints) != 2 or len(actuators) != 2 or len(set(joints)) != 2 or len(set(actuators)) != 2:
                raise ValueError("expected two distinct finger joints and actuators")
            joint_ids = np.array([model.joint_name2id(name) for name in joints], dtype=int)
            actuator_ids = np.array([model.actuator_name2id(name) for name in actuators], dtype=int)
            if min(joint_ids) < 0 or min(actuator_ids) < 0 or len(set(joint_ids)) != 2 or len(set(actuator_ids)) != 2:
                raise ValueError("finger names did not resolve to distinct model elements")
            addresses = np.asarray(model.jnt_qposadr)[joint_ids]
            control_range = np.asarray(model.actuator_ctrlrange)[actuator_ids]
            gain = np.asarray(model.actuator_gainprm)[actuator_ids]
            bias_parameters = np.asarray(model.actuator_biasprm)[actuator_ids]
            expected_gain = np.zeros_like(gain)
            expected_gain[:, 0] = gain[:, 0]
            expected_bias = np.zeros_like(bias_parameters)
            expected_bias[:, 1] = -gain[:, 0]
            expected_transmission = np.column_stack([joint_ids, [-1, -1]])
            expected_gear = np.zeros((2, 6))
            expected_gear[:, 0] = 1.
            # MuJoCo enums: slide=2, joint transmission=0, dynamics none=0,
            # fixed gain=0, affine bias=1. Position servo: force=kp*(ctrl-qpos).
            if (not np.all(np.asarray(model.jnt_type)[joint_ids] == 2)
                    or not np.all(np.asarray(model.jnt_limited)[joint_ids])
                    or not np.all(np.asarray(model.actuator_trntype)[actuator_ids] == 0)
                    or not np.array_equal(np.asarray(model.actuator_trnid)[actuator_ids], expected_transmission)
                    or not np.array_equal(np.asarray(model.actuator_gear)[actuator_ids], expected_gear)
                    or not np.all(np.asarray(model.actuator_dyntype)[actuator_ids] == 0)
                    or not np.all(np.asarray(model.actuator_gaintype)[actuator_ids] == 0)
                    or not np.all(np.asarray(model.actuator_biastype)[actuator_ids] == 1)
                    or not np.all(np.asarray(model.actuator_ctrllimited)[actuator_ids])
                    or not np.isfinite(gain).all() or not np.all(gain[:, 0] > 0)
                    or not np.array_equal(gain, expected_gain)
                    or not np.array_equal(bias_parameters, expected_bias)
                    or control_range.shape != (2, 2) or not np.isfinite(control_range).all()
                    or not np.all(control_range[:, 1] > control_range[:, 0])
                    or not np.array_equal(control_range, np.asarray(model.jnt_range)[joint_ids])):
                raise ValueError("expected limited slide joints with matching unit-gear position servos")
            positions = np.asarray(data.qpos)[addresses]
            if positions.shape != (2,) or not np.isfinite(positions).all():
                raise ValueError("invalid restored finger positions")
            bias = .5 * (control_range[:, 1] + control_range[:, 0])
            weight = .5 * (control_range[:, 1] - control_range[:, 0])
            action = np.clip((positions - bias) / weight, -1., 1.)
            prepared.append((gripper, actuator_ids, action, bias + weight * action))
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            raise RuntimeError(f"unsupported restored gripper contract: {error}") from error
    # Validate all grippers first, then synchronize only their command state.
    for gripper, actuator_ids, action, targets in prepared:
        gripper.current_action = action.copy()
        env.sim.data.ctrl[actuator_ids] = targets


def restore_raw_state(env, state) -> dict:
    """Restore a raw state and refresh controllers/observations without stepping.

    No manifest, declared mask, or model outcome is required. The caller must
    create/reset the correct scene beforehand and separately check its model
    identity and physical legality. This does not seed/reset the environment,
    alter episode counters/done flags, or settle physics. Warmstart caches are
    cleared; controller goals and Panda's incremental gripper command are
    reanchored to the restored robot pose. Gripper position control targets are
    initialized consistently without advancing its incremental action state.
    """
    state = np.asarray(state)
    if state.ndim != 1 or not state.size or state.dtype.kind not in "fiu" or not np.isfinite(state).all():
        raise ValueError("state must be a nonempty finite one-dimensional real numeric vector")
    state = state.copy()
    if state.shape != np.asarray(env.sim.get_state().flatten()).shape:
        raise ValueError("state vector shape does not match the active simulator")
    controllers = []
    for holder in _chain(env):
        robots = getattr(holder, "robots", None)
        if robots:
            controllers = [getattr(robot, "controller", None) for robot in robots]
            break
    if (not controllers or any(not callable(getattr(controller, hook, None))
                               for controller in controllers for hook in ("update", "reset_goal"))):
        raise RuntimeError("cannot refresh robot controllers after restoring state")
    env.sim.set_state_from_flattened(state.copy())
    env.sim.data.qacc_warmstart[:] = 0
    _synchronize_grippers(env, robots)
    env.sim.forward()
    phase = "state restoration/controller/observation refresh"
    _restore_quaternion_roundoff(env, state, phase=phase)
    for controller in controllers:
        controller.update(force=True)
        controller.reset_goal()
    _restore_quaternion_roundoff(env, state, phase=phase)
    observation = fresh_observation(env)
    _require_exact_state(state, np.asarray(env.sim.get_state().flatten()), phase)
    return observation


class LiberoGoalEnv:
    def __init__(self, config: dict):
        self.base_dir = Path(config["manifest_dir"])
        self.control_freq = int(config.get("control_freq", 20))
        self.image_size = int(config.get("image_size", 256))
        self.identity = environment_identity(self.control_freq)
        expected = config["environment"]
        if expected.get("name") != "libero" or expected.get("fingerprint") != self.identity["fingerprint"]:
            raise ValueError("runtime LIBERO fingerprint differs from the frozen manifest")
        self.env = None
        self.inner = None
        self._ready = False
        self.task_key = None
        self.predicates = []
        self._last_action = None
        self._hold = config.get("hold_action")
        self._hold_contract = config.get("hold_contract")
        if self._hold is not None:
            candidate = np.asarray(self._hold, dtype=float)
            if (candidate.shape != (7,) or not np.isfinite(candidate).all()
                    or not isinstance(self._hold_contract, str) or not self._hold_contract.strip()):
                raise ValueError("explicit hold_action requires a finite 7D action and hold_contract description")
            self._hold = candidate.copy()

    def _prepare_task(self, episode: dict):
        from libero.libero import benchmark, get_libero_path

        key = (episode["suite"], episode["libero_task_id"], episode["task_name"])
        if self.task_key == key:
            if hashlib.sha256(self._task_bddl_path.read_bytes()).hexdigest() != self._task_bddl_sha256:
                raise ValueError("task BDDL content changed after environment creation")
            return
        self.close()
        suite = benchmark.get_benchmark_dict()[episode["suite"]]()
        task = suite.get_task(episode["libero_task_id"])
        if task.name != episode["task_name"] or task.language != episode["instruction"]:
            raise ValueError("task ID/name/instruction mismatch with the installed LIBERO task")
        bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
        expected_hash = episode.get("bddl_sha256")
        if not expected_hash or hashlib.sha256(bddl.read_bytes()).hexdigest() != expected_hash:
            raise ValueError("missing/mismatched bddl_sha256 for real LIBERO state package")
        self.env = _new_scene(bddl, image_size=self.image_size, control_freq=self.control_freq)
        self.task_key = key
        self._task_bddl_sha256 = expected_hash
        self._task_bddl_path = bddl
        self._task_instruction = task.language

    def reset(self, episode: dict) -> dict:
        # A failed reset must not leave the previous episode executable.
        self._ready = False
        self.inner = None
        self.predicates = []
        self._last_action = None
        state_file = verify_state_file(episode, self.base_dir)
        # verify_state_file validates its own bytes. Re-hash the exact bytes we
        # decode too, so a replaced file cannot slip between verification/load.
        state_bytes = state_file.read_bytes()
        if hashlib.sha256(state_bytes).hexdigest() != episode["state_sha256"]:
            raise ValueError("state_sha256 changed between verification and restoration")
        state = np.load(io.BytesIO(state_bytes), allow_pickle=False)
        self._prepare_task(episode)
        if episode.get("bddl_sha256") != self._task_bddl_sha256 or episode["instruction"] != self._task_instruction:
            raise ValueError("inconsistent BDDL/instruction within the task")
        self.env.seed(episode["seed"])
        reset_scene(self.env)
        inner = _task_environment(self.env)
        groups = episode["goal_specs"]
        if not groups or any(not group["predicates"] for group in groups):
            raise ValueError("goal groups must be nonempty conjunctions")
        official = [_predicate(p) for p in inner.parsed_problem["goal_state"]]
        grouped = [_predicate(p) for g in groups for p in g["predicates"]]
        if len(grouped) != len(set(grouped)) or sorted(grouped) != sorted(official):
            raise ValueError("goal groups must partition the official final predicates exactly")
        xml_hash = model_xml_hash(self.env)
        if not episode.get("model_xml_sha256") or episode["model_xml_sha256"] != xml_hash:
            raise ValueError("missing/mismatched model_xml_sha256; state layout/scene may differ")
        observation = restore_raw_state(self.env, state)
        self.inner = inner
        self.predicates = [[list(_predicate(p)) for p in g["predicates"]] for g in groups]
        self._ready = True
        return observation

    def goal_values(self) -> list[bool]:
        if not self._ready:
            raise RuntimeError("a successful reset is required before evaluating goals")
        values = [all(bool(self.inner._eval_predicate(p)) for p in group) for group in self.predicates]
        if all(values) != bool(self.env.check_success()):
            raise RuntimeError("grouped predicates disagree with official task success")
        return values

    def step(self, action) -> dict:
        if not self._ready:
            raise RuntimeError("a successful reset is required before stepping")
        action = np.asarray(action)
        if action.shape != (7,) or action.dtype.kind not in "fiu" or not np.isfinite(action).all():
            raise ValueError("LIBERO requires a finite, decoded 7D environment action")
        # Evaluator success does not stop or freeze the policy. Disable wrapper
        # done guards explicitly, without forwarding done/reward into the policy.
        for holder in _chain(self.env):
            if "done" in vars(holder):
                holder.done = False
        # Native observations are sampled on robosuite's internal observable
        # clocks and may lag the final physics state. Every baseline uses the
        # same explicit synchronization protocol, recorded in the fingerprint.
        self.env.step(action.tolist())
        self._last_action = action.copy()
        return fresh_observation(self.env)

    def hold_action(self):
        # A zero pose delta plus gripper=-1 is NOT a universal safe stop.
        # Methods emitting STOP must declare a task-validated controller.
        if self._hold is None:
            raise RuntimeError("STOP requires an explicit, validated hold_action/hold_contract")
        return np.asarray(self._hold, dtype=float).copy()

    def close(self):
        env = self.env
        self.env = None
        self.task_key = None
        self.inner = None
        self.predicates = []
        self._ready = False
        self._last_action = None
        if env is not None:
            env.close()
