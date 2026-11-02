"""Explicit R7 active-object pose evidence; pure arrays, never native stepping.

The raw flattened state convention is [time, qpos, qvel, act]. The complete
compiled joint partition and XML digest are retained, so a velocity exemption
cannot be assigned to arbitrary coordinates by an unchecked index list.
"""
from copy import deepcopy
import re

import numpy as np

PROFILE = "active-free-object-pose-stability-v7"
AUDIT_SCHEMA = "remaining-goals-validation-v2-active-pose"
OBJECT = "white_yellow_mug_1"
BINDING_SCHEMA = "remaining-active-free-joint-binding-v1"
POSITION_LIMIT = .005
ORIENTATION_LIMIT_DEG = 1.
VELOCITY_LIMIT = .01


def _integer(value, name, minimum=0):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _vector(value, size, name):
    array = np.asarray(value)
    if array.shape != (size,) or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a finite real vector of size {size}")
    return array.astype(np.float64, copy=True)


def validate_binding(binding, model_xml_sha256=None):
    """Validate the complete joint partition and selected free joint, file-only."""
    if not isinstance(binding, dict) or set(binding) != {
            "schema_version", "model_xml_sha256", "object_name", "state_layout", "joint_layout", "active_joint"}:
        raise ValueError("complete explicit stability binding required")
    digest = binding["model_xml_sha256"]
    if (binding["schema_version"] != BINDING_SCHEMA or binding["object_name"] != OBJECT
            or not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None
            or model_xml_sha256 is not None and digest != model_xml_sha256):
        raise ValueError("stability binding identity/XML digest mismatch")
    layout = binding["state_layout"]
    if not isinstance(layout, dict) or set(layout) != {"nq", "nv", "na", "qpos_start", "qvel_start", "state_size"}:
        raise ValueError("complete flattened state layout required")
    for name, value in layout.items():
        _integer(value, name, 1 if name in ("nq", "nv", "qpos_start", "qvel_start", "state_size") else 0)
    nq, nv, na = (layout[k] for k in ("nq", "nv", "na"))
    if (layout["qpos_start"], layout["qvel_start"], layout["state_size"]) != (1, 1+nq, 1+nq+nv+na):
        raise ValueError("flattened state layout is inconsistent")
    joints = binding["joint_layout"]
    if not isinstance(joints, list) or not joints:
        raise ValueError("complete compiled joint mapping required")
    qnext = vnext = 0
    names, active = set(), []
    for index, joint in enumerate(joints):
        if not isinstance(joint, dict) or set(joint) != {"id", "name", "type", "qpos_adr", "qpos_dim", "dof_adr", "dof_dim"}:
            raise ValueError("invalid compiled joint mapping")
        for name in ("id", "type", "qpos_adr", "qpos_dim", "dof_adr", "dof_dim"):
            _integer(joint[name], name)
        name, kind = joint["name"], joint["type"]
        if not isinstance(name, str) or not name or name in names or kind not in (0, 1, 2, 3):
            raise ValueError("joint name/type must be explicit, unique and supported")
        names.add(name)
        dims = {0: (7, 6), 1: (4, 3), 2: (1, 1), 3: (1, 1)}[kind]
        if (joint["id"] != index or (joint["qpos_dim"], joint["dof_dim"]) != dims
                or (joint["qpos_adr"], joint["dof_adr"]) != (qnext, vnext)):
            raise ValueError("compiled joints must partition the full qpos/qvel layout without gaps or overlap")
        qnext += dims[0]; vnext += dims[1]
        if name == OBJECT or name.startswith(OBJECT + "_"):
            active.append(joint)
    declared_active = binding["active_joint"]
    if not isinstance(declared_active, dict):
        raise ValueError("explicit target joint mapping required")
    for name in ("id", "type", "qpos_adr", "qpos_dim", "dof_adr", "dof_dim"):
        _integer(declared_active.get(name), name)
    if (qnext, vnext) != (nq, nv) or len(active) != 1 or active[0]["type"] != 0 or declared_active != active[0]:
        raise ValueError("mapping must bind exactly the target free joint and all state coordinates")
    return deepcopy(binding)


def binding_from_model(model, model_xml_sha256):
    """Read actual compiled arrays and names; no simulated state is changed."""
    from benchmark.states import mujoco_state as ms
    nq, nv, na, njnt = (_integer(getattr(model, k), k) for k in ("nq", "nv", "na", "njnt"))
    arrays = [np.asarray(getattr(model, k)) for k in ("jnt_type", "jnt_qposadr", "jnt_dofadr")]
    if any(a.shape != (njnt,) or a.dtype.kind not in "iu" for a in arrays):
        raise ValueError("compiled joint arrays must have exact integer njnt layout")
    joints = []
    for i in range(njnt):
        kind = int(arrays[0][i])
        if kind not in (0, 1, 2, 3):
            raise ValueError("unsupported compiled joint type")
        qdim, vdim = {0: (7, 6), 1: (4, 3), 2: (1, 1), 3: (1, 1)}[kind]
        joints.append({"id": i, "name": ms.joint_name(model, i), "type": kind,
                       "qpos_adr": int(arrays[1][i]), "qpos_dim": qdim,
                       "dof_adr": int(arrays[2][i]), "dof_dim": vdim})
    active = [j for j in joints if j["name"] == OBJECT or j["name"].startswith(OBJECT + "_")]
    return validate_binding({"schema_version": BINDING_SCHEMA, "model_xml_sha256": model_xml_sha256,
        "object_name": OBJECT, "state_layout": {"nq": nq, "nv": nv, "na": na,
        "qpos_start": 1, "qvel_start": 1+nq, "state_size": 1+nq+nv+na},
        "joint_layout": joints, "active_joint": active[0] if len(active) == 1 else None})


def validate_scope(episode):
    """Only the approved named task/goal/protocol/index can use R7."""
    from .nine_catalog import validate_episode_semantics
    if (not isinstance(episode, dict) or episode.get("stability_profile") != PROFILE
            or episode.get("observation_profile") != "named-uint8-rgb-one-level-v6"
            or episode.get("task_id") != "mug_microwave_close"
            or not isinstance(episode.get("model_xml_sha256"), str)
            or re.fullmatch("[0-9a-f]{64}", episode["model_xml_sha256"]) is None
            or not isinstance(episode.get("construction"), dict)
            or episode["construction"].get("protocol") != "nine-mask10"
            or type(episode.get("initial_state_index")) is not int
            or episode["initial_state_index"] not in range(10)
            or episode.get("initial_mask") != [True, False]
            or any(type(x) is not bool for x in episode["initial_mask"])):
        raise ValueError("R7 requires explicit nine-mask10/mug_microwave_close index 0..9 scope")
    validate_episode_semantics(episode)
    reference = np.asarray(episode.get("reference_robot_qpos"))
    _vector(reference, 9, "reference_robot_qpos")
    return validate_binding(episode.get("stability_binding"), episode.get("model_xml_sha256"))


def sample(state, qvel, binding):
    """Bind raw state/qvel to A's unmodified pose and velocity diagnostics."""
    binding = validate_binding(binding)
    layout, joint = binding["state_layout"], binding["active_joint"]
    state = _vector(state, layout["state_size"], "state")
    qvel = _vector(qvel, layout["nv"], "qvel")
    raw_velocity = state[layout["qvel_start"]:layout["qvel_start"]+layout["nv"]]
    if not np.array_equal(raw_velocity.view(np.uint64), qvel.view(np.uint64)):
        raise ValueError("qvel differs from the bound raw state velocity slice")
    start = layout["qpos_start"] + joint["qpos_adr"]
    pose = state[start:start+7]
    if not np.linalg.norm(pose[3:]) > 0:
        raise ValueError("active quaternion must have nonzero norm")
    vstart = joint["dof_adr"]
    selected = qvel[vstart:vstart+6]
    other = np.concatenate((qvel[:vstart], qvel[vstart+6:]))
    return {"state": state.tolist(), "qvel": qvel.tolist(), "active_pose_wxyz": pose.tolist(),
            "max_abs_active_velocity": float(np.max(np.abs(selected))),
            "max_abs_non_active_velocity": float(np.max(np.abs(other))) if other.size else 0.}


def pose_window(samples):
    """Conservative bbox translation and maximum pairwise shortest rotation.

    This helper supports the 20-observation preparation window as well as the
    formal 151 observations. The caller must enforce the required point count.
    All A velocity components stay in raw evidence; only diagnostics use them.
    """
    if not isinstance(samples, (list, tuple)) or not samples:
        raise ValueError("pose window requires observed samples")
    poses = np.array([_vector(s.get("active_pose_wxyz"), 7, "active pose") for s in samples])
    norms = np.linalg.norm(poses[:, 3:], axis=1)
    if np.any(norms == 0) or not np.isfinite(norms).all():
        raise ValueError("invalid active quaternion norm")
    quat = poses[:, 3:] / norms[:, None]
    # Force the self-pair dot to one; avoid roundoff giving identical poses a
    # spurious nonzero span. q and -q use the same shortest rotation.
    dots = np.clip(np.abs(quat @ quat.T), 0., 1.)
    np.fill_diagonal(dots, 1.)
    angle = float(np.rad2deg(2 * np.arccos(np.min(dots))))
    span = float(np.linalg.norm(np.ptp(poses[:, :3], axis=0)))
    active, other = [], []
    for item in samples:
        for name, output in (("max_abs_active_velocity", active), ("max_abs_non_active_velocity", other)):
            value = item.get(name)
            if type(value) not in (float, int) or not np.isfinite(value) or value < 0:
                raise ValueError("invalid velocity diagnostics")
            output.append(value)
    return {"observations": len(samples), "position_span_m": span, "orientation_span_deg": angle,
            "active_velocity_exceedance_fraction": sum(x > VELOCITY_LIMIT for x in active) / len(active),
            "peak_abs_active_velocity": max(active), "non_active_velocity_peak": max(other),
            "stable": bool(span <= POSITION_LIMIT and angle <= ORIENTATION_LIMIT_DEG)}
