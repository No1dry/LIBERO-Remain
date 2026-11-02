"""R5: finite upright mug poses over the microwave's actual collision floor.

This is a seed geometry hypothesis, not evidence of stable contact. No simulator
is imported, created, restored, forwarded or stepped. Every candidate still
requires the unchanged HOLD, full-state physics, official predicate and v6
audits. Existing R2 construction is deliberately untouched.
"""
from __future__ import annotations

from itertools import product

import numpy as np

from benchmark.remaining_goals.construction import (
    REGION_TILT_LIMIT_RAD, _array, _base, _candidate, _collision_geoms,
    _descendants, _field, _geom_bounds, _joint_id, _limit, _rotation,
    region_geometry,
)
from benchmark.states import mujoco_state as ms


METHOD = "microwave_gravity_support_pose_transplant_v3"
OBJECT = "white_yellow_mug_1"
REGION = "microwave_1_heating_region"
HORIZONTAL_MARGIN = .001
SEED_CLEARANCE = .002
_SIGNS = np.asarray(list(product((-1., 1.), repeat=3)))


def _quat_rotation(value):
    q = _array(value, (4,), "free-joint quaternion")
    norm = float(np.linalg.norm(q))
    if not np.isclose(norm, 1., atol=1e-5, rtol=0):
        raise ValueError("free-joint quaternion is not unit length")
    w, x, y, z = q / norm
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _margin(model, geom):
    value = float(_field(model, "geom_margin", geom, "geom", "margin"))
    if not np.isfinite(value) or value < 0:
        raise ValueError("collision margin must be known, finite and nonnegative")
    return value


def _mug_geometry(base, model, data, layout):
    entry = ms.resolve_free_joint(model, OBJECT)
    body = int(_field(model, "jnt_bodyid", _joint_id(model, entry), "joint", "bodyid"))
    owned = _descendants(model, body)
    for joint in range(int(model.njnt)):
        if (int(_field(model, "jnt_bodyid", joint, "joint", "bodyid")) in owned
                and ms.joint_name(model, joint) != entry.name):
            raise ValueError("mug must be a single rigid free-joint component")
    start = layout.qpos_slice.start + entry.qpos_adr
    origin, rotation = base[start:start+3], _quat_rotation(base[start+3:start+7])
    if (not np.allclose(data.body_xpos[body], origin, atol=1e-8, rtol=0)
            or not np.allclose(_rotation(data.body_xmat[body], "mug body_xmat"),
                               rotation, atol=1e-8, rtol=0)):
        raise ValueError("mug body pose differs from base free-joint pose")
    boxes = []
    for geom in _collision_geoms(model, body):
        if ms.geom_type(model, geom) != 6:
            raise ValueError("R5 requires known mug collision box geometry")
        half = _array(_field(model, "geom_size", geom, "geom", "size"), (3,), "box half-size")
        if np.any(half <= 0):
            raise ValueError("mug collision box has nonpositive half-size")
        center = rotation.T @ (_array(data.geom_xpos[geom], (3,)) - origin)
        axes = rotation.T @ _rotation(data.geom_xmat[geom], "mug geom_xmat")
        boxes.append({"geom": geom, "corners": (_SIGNS * half) @ axes.T + center,
                      "center": center, "axes": axes, "half_size": half,
                      "margin": _margin(model, geom)})
    all_corners = np.concatenate([b["corners"] for b in boxes])
    bottom = float(all_corners[:, 2].min())
    # Pinned mug's local +z is upright; confirm a real thin, flat bottom box
    # near its lowest collision face instead of inferring a cylinder/mesh base.
    bottom_boxes = []
    for box in boxes:
        thin = int(np.argmin(box["half_size"]))
        aligned = abs(float(box["axes"][2, thin])) >= np.cos(REGION_TILT_LIMIT_RAD)
        if aligned and abs(float(box["corners"][:, 2].min()) - bottom) <= .001:
            bottom_boxes.append(box["geom"])
    if not bottom_boxes:
        raise ValueError("mug has no known local-z aligned collision bottom box")
    return entry, start, rotation, boxes, bottom_boxes


def _support(model, data, region):
    body = region["body_id"]
    origin = _array(data.body_xpos[body], (3,), "microwave body origin")
    body_rotation = _rotation(data.body_xmat[body], "microwave body_xmat")
    owned = _collision_geoms(model, body)
    matches = []
    for geom in owned:
        if ms.geom_bodyid(model, geom) != body or ms.geom_type(model, geom) != 6:
            continue
        half = _array(_field(model, "geom_size", geom, "geom", "size"), (3,))
        position = _array(data.geom_xpos[geom], (3,))
        rotation = _rotation(data.geom_xmat[geom], "floor geom_xmat")
        local = body_rotation.T @ (position-origin)
        # Explicit pinned bottom box. Vertical wall caps, the roof, visual
        # meshes and a movable door can never substitute for this support.
        if (np.allclose(local, [-.04, -.004, .012], atol=1e-6, rtol=0)
                and np.allclose(half, [.1035, .084, .012], atol=1e-6, rtol=0)
                and np.allclose(body_rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0)):
            normal = rotation[:, 2]
            tilt = float(np.arctan2(np.linalg.norm(normal[:2]), normal[2]))
            if tilt <= REGION_TILT_LIMIT_RAD:
                matches.append({"geom": geom, "half_size": half, "rotation": rotation,
                                "face": position + normal*half[2], "normal": normal,
                                "tilt": tilt, "margin": _margin(model, geom)})
    if len(matches) != 1:
        raise ValueError("R5 requires exactly one known microwave collision floor")
    support = matches[0]
    obstacles = []
    for geom in owned:
        if geom == support["geom"]:
            continue
        lo, hi = _geom_bounds(model, data, geom, np.zeros(3), np.eye(3))
        obstacles.append((geom, lo, hi, _margin(model, geom)))
    return support, obstacles


def _clip(polygon, direction, bound):
    """Clip a convex root-position polygon by direction @ xy <= bound."""
    if not len(polygon):
        return polygon
    result = []
    previous = polygon[-1]
    prev_distance = float(direction @ previous-bound)
    for current in polygon:
        distance = float(direction @ current-bound)
        if (distance <= 0) != (prev_distance <= 0):
            fraction = prev_distance / (prev_distance-distance)
            result.append(previous + fraction*(current-previous))
        if distance <= 0:
            result.append(current)
        previous, prev_distance = current, distance
    return np.asarray(result)


def _pose_positions(vertices, support, region):
    """Intersect actual full-footprint support and original In-volume bounds."""
    axes = support["rotation"][:, :2]
    normal = support["normal"]
    rise = (SEED_CLEARANCE - float((vertices @ normal).min())) / normal[2]
    origin = support["face"] + [0., 0., rise]
    footprint = (vertices + [0., 0., rise]) @ axes
    low = -support["half_size"][:2] + HORIZONTAL_MARGIN - footprint.min(axis=0)
    high = support["half_size"][:2] - HORIZONTAL_MARGIN - footprint.max(axis=0)
    if np.any(low >= high):
        return []
    polygon = np.array([[low[0], low[1]], [high[0], low[1]],
                        [high[0], high[1]], [low[0], high[1]]])
    local = (vertices + origin - region["center"]) @ region["rotation"]
    coefficients = region["rotation"].T @ axes
    for axis in range(3):
        for sign in (1., -1.):
            limit = region["half_size"][axis] - HORIZONTAL_MARGIN - (sign*local[:, axis]).max()
            polygon = _clip(polygon, sign*coefficients[axis], limit)
            if len(polygon) < 3:
                return []
    center = polygon.mean(axis=0)
    offsets = [center]
    offsets.extend(center + .5*(point-center) for point in polygon)
    offsets.extend(center + .25*(a+b-2*center)
                   for a, b in zip(polygon, np.roll(polygon, -1, axis=0)))
    return [origin + axes @ xy for xy in offsets]


def microwave_candidates(base, model, data, *, max_candidates=24):
    """Return at most 24 deterministic candidates, interleaving four yaw poses.

    Only A's seven qpos coordinates change. The whitelist also names A's six
    qvel coordinates for the later measured-state transplant; seed velocities
    and all B/robot/other coordinates are copied bit for bit from the base.
    ``data`` must already correspond to that base; this function never updates it.
    """
    base, layout = _base(base, model)
    limit = min(24, _limit(max_candidates, "max_candidates"))
    if not np.array_equal(_array(data.qpos, (layout.nq,), "data.qpos"), base[layout.qpos_slice]):
        raise ValueError("data.qpos differs from base_state")
    region = region_geometry(model, data, REGION, in_volume=True)
    entry, start, original_rotation, boxes, bottom_boxes = _mug_geometry(base, model, data, layout)
    support, obstacles = _support(model, data, region)
    yaw = float(np.arctan2(original_rotation[1, 0], original_rotation[0, 0]))
    allowed = list(range(start, start+7)) + list(range(
        layout.qvel_slice.start+entry.dof_adr, layout.qvel_slice.start+entry.dof_adr+6))
    per_pose = []
    for pose_index, yaw_offset in enumerate((0., np.pi/2, -np.pi/2, np.pi)):
        angle = yaw + yaw_offset
        quaternion = np.array([np.cos(angle/2), 0., 0., np.sin(angle/2)])
        rotation = _quat_rotation(quaternion)
        rotated = [box["corners"] @ rotation.T for box in boxes]
        vertices = np.concatenate(rotated)
        seeds = []
        for position in _pose_positions(vertices, support, region):
            obstacle_gaps = []
            for other, lo, hi, other_margin in obstacles:
                # Per-box AABBs include the real margins conservatively. An
                # overlap is rejected even if exact oriented shapes might fit;
                # this cannot certify contact-free physics or relax any audit.
                gaps = [float(np.max(np.maximum(lo-(v+position).max(axis=0),
                                                 (v+position).min(axis=0)-hi)))
                        - other_margin - box["margin"] for v, box in zip(rotated, boxes)]
                obstacle_gaps.append((other, min(gaps)))
            if any(gap < HORIZONTAL_MARGIN for _, gap in obstacle_gaps):
                continue
            world = vertices + position
            local = (world-region["center"]) @ region["rotation"]
            floor_local = (world-support["face"]) @ support["rotation"]
            region_clearance = region["half_size"]-np.abs(local).max(axis=0)
            floor_clearance = support["half_size"][:2]-np.abs(floor_local[:, :2]).max(axis=0)
            if np.any(region_clearance < HORIZONTAL_MARGIN-1e-12) or np.any(floor_clearance < HORIZONTAL_MARGIN-1e-12):
                continue
            state = base.copy()
            state[start:start+7] = np.r_[position, quaternion]
            placement = {"object": OBJECT, "joint": entry.name, "region": REGION,
                "target_kind": "region", "relation": "in", "position": position.tolist(),
                "quaternion_wxyz": quaternion.tolist(), "aabb_min": world.min(axis=0).tolist(),
                "aabb_max": world.max(axis=0).tolist(), "reservation_objects": [OBJECT],
                "reservation_plan": {"method": METHOD, "objects": [OBJECT]},
                "slot_index": 0, "clearance": SEED_CLEARANCE}
            diagnostics = {"method": METHOD, "pose_index": pose_index,
                "base_yaw_rad": yaw, "yaw_offset_rad": yaw_offset,
                "candidate_quaternion_wxyz": quaternion.tolist(), "gravity_aligned_local_axis": "+z",
                "collision_geom_ids": [b["geom"] for b in boxes], "bottom_geom_ids": bottom_boxes,
                "collision_world_extent": np.ptp(vertices, axis=0).tolist(),
                "object_bottom_offset": float(vertices[:, 2].min()),
                "support_geom_id": support["geom"], "support_body_id": region["body_id"],
                "support_half_size": support["half_size"].tolist(), "support_margin": support["margin"],
                "support_face_world": support["face"].tolist(), "support_normal": support["normal"].tolist(),
                "support_tilt_rad": support["tilt"], "support_tilt_limit_rad": REGION_TILT_LIMIT_RAD,
                "support_world_z": float(support["face"][2]),
                "support_clearance": float(((world-support["face"]) @ support["normal"]).min()),
                "support_footprint_clearance": floor_clearance.tolist(),
                "region_clearance": region_clearance.tolist(), "region_rotation": region["rotation"].tolist(),
                "obstacle_aabb_clearances": [{"geom": g, "clearance_after_margins": gap} for g, gap in obstacle_gaps],
                "minimum_obstacle_aabb_clearance": min((gap for _, gap in obstacle_gaps), default=None),
                "site_axes_are_support_axes": False, "full_collision_volume_contained": True,
                "geometry_recomputed_for_pose": True, "gravity_settle_required": True,
                "seed_orientation_preserved": bool(np.array_equal(
                    quaternion, base[start+3:start+7])), "seed_velocity_preserved": True,
                "settled_component_includes_orientation": True,
                "contact_parameters_changed": False, "physical_solution_proven": False}
            seeds.append(_candidate(base, state, model, allowed, [entry.name], [placement], diagnostics))
        per_pose.append(seeds)
    output = []
    # Round-robin eligible poses; a large first-pose spatial search must not
    # consume the whole 24-candidate physics budget before other yaws are tried.
    for rank in range(max(map(len, per_pose), default=0)):
        for seeds in per_pose:
            if rank < len(seeds):
                output.append(seeds[rank])
                if len(output) == limit:
                    return output
    return output
