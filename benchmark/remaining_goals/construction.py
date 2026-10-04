"""Pure, bounded candidate edits for independently satisfiable LIBERO goals.

No simulator reset, forward, step, predicate evaluation, or settling occurs
here. ``data`` must already have been forwarded from the supplied base state.
Every result is a *candidate*, never a declaration of physical legality. The
driver must validate predicates, contacts, settling, visibility and reachability.
The current placement search preserves object orientation and supports box
regions whose local z axis is within five degrees of world up, including yaw
rotation. Small settled tilt is allowed only for conservative candidate search;
gravity settling and full physical validation remain mandatory downstream.
Unknown geometry and larger or inverted support tilts fail explicitly.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import itertools
from numbers import Integral
from typing import Any

import numpy as np

from benchmark.states import mujoco_state as ms


REGION_TILT_LIMIT_RAD = float(np.deg2rad(5.0))
# Pinned LIBERO ObjectState.check_ontop requires body-origin xy distance < .03.
# This only bounds candidate seeds; contact and the actual predicate are audited.
OBJECT_ON_ORIGIN_RADIUS = 0.03


def _array(value, shape=None, name="array"):
    value = np.asarray(value)
    if value.dtype.kind not in "fiu" or not np.isfinite(value).all():
        raise ValueError(f"{name} must contain finite real numbers")
    if shape is not None and value.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {value.shape}")
    return value.astype(np.float64, copy=True)


def _base(base_state, model):
    layout = ms.StateLayout.from_model(model)
    state = _array(base_state, (layout.total_dim,), "base_state")
    return state, layout


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _field(model, field, index, kind, attribute):
    values = getattr(model, field, None)
    if values is not None:
        return values[index]
    return getattr(getattr(model, kind)(index), attribute)


def _joint_id(model, entry):
    return next(i for i in range(int(model.njnt)) if ms.joint_name(model, i) == entry.name)


def _not_robot(entry):
    if entry.name.startswith(("robot", "gripper")):
        raise ValueError("construction cannot edit robot or gripper joints")


def _descendants(model, root):
    result = {int(root)}
    for body in range(int(model.nbody)):
        cursor, seen = body, set()
        while cursor not in seen:
            if cursor == root:
                result.add(body)
                break
            seen.add(cursor)
            parent = int(_field(model, "body_parentid", cursor, "body", "parentid"))
            if parent == cursor:
                break
            cursor = parent
    return result


def _collision_geoms(model, root):
    bodies = _descendants(model, root)
    output = []
    for geom in range(int(model.ngeom)):
        if ms.geom_bodyid(model, geom) not in bodies:
            continue
        contact = int(_field(model, "geom_contype", geom, "geom", "contype"))
        affinity = int(_field(model, "geom_conaffinity", geom, "geom", "conaffinity"))
        if (contact or affinity) and ms.geom_type(model, geom) != 0:
            output.append(geom)
    if not output:
        raise ValueError(f"body {root} has no finite collision geometry")
    return output


def _rotation(value, name):
    matrix = _array(value, name=name).reshape(3, 3)
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6, rtol=0) or not np.isclose(
            np.linalg.det(matrix), 1., atol=1e-6, rtol=0):
        raise ValueError(f"{name} must be an orthonormal rotation")
    return matrix


def _geom_bounds(model, data, geom, origin, frame):
    """Collision bounds in a chosen frame; handles MuJoCo primitive types."""
    center = frame.T @ (_array(data.geom_xpos[geom], (3,), "geom_xpos") - origin)
    rotation = frame.T @ _rotation(data.geom_xmat[geom], "geom_xmat")
    size = _array(_field(model, "geom_size", geom, "geom", "size"), (3,), "geom_size")
    kind = ms.geom_type(model, geom)
    if np.any(size < 0):
        raise ValueError("negative geom size")
    if kind == 2:  # sphere
        extent = np.full(3, size[0])
    elif kind == 3:  # capsule: radius, half-length along local z
        extent = size[0] + np.abs(rotation[:, 2]) * size[1]
    elif kind == 4:  # ellipsoid
        extent = np.sqrt(np.sum((rotation * size) ** 2, axis=1))
    elif kind == 5:  # cylinder
        extent = size[0] * np.sqrt(np.sum(rotation[:, :2] ** 2, axis=1))
        extent += size[1] * np.abs(rotation[:, 2])
    elif kind == 6:  # box
        extent = np.abs(rotation) @ size
    elif kind == 7:  # compiled mesh vertices, already in MuJoCo's mesh frame
        mesh_id = int(_field(model, "geom_dataid", geom, "geom", "dataid"))
        if mesh_id < 0:
            raise ValueError("collision mesh has no mesh data")
        start, count = int(model.mesh_vertadr[mesh_id]), int(model.mesh_vertnum[mesh_id])
        vertices = _array(model.mesh_vert[start:start + count], name="mesh vertices")
        if vertices.shape != (count, 3) or not count:
            raise ValueError("collision mesh vertices unavailable")
        points = vertices @ rotation.T + center
        return points.min(axis=0), points.max(axis=0)
    else:
        raise ValueError(f"unsupported collision geom type {kind}")
    return center - extent, center + extent


def region_geometry(model, data, site_name: str) -> dict:
    """Read a named near-horizontal box site's full world pose, without leveling it.

    Accepting a small tilt does not establish a stable support surface. Candidate
    positions retain the measured rotation and still require gravity settling.
    """
    try:
        site = int(model.site_name2id(site_name))
    except AttributeError:
        site = int(model.site(site_name).id)
    if site < 0 or site >= int(model.nsite):
        raise ValueError(f"unknown region site {site_name!r}")
    if int(_field(model, "site_type", site, "site", "type")) != 6:
        raise ValueError("placement currently requires an explicit box region site")
    size = _array(_field(model, "site_size", site, "site", "size"), (3,), "site_size")
    if np.any(size[:2] <= 0) or size[2] < 0:
        raise ValueError("region must have positive horizontal dimensions")
    rotation = _rotation(data.site_xmat[site], "site_xmat")
    normal = rotation[:, 2]
    tilt = float(np.arctan2(np.linalg.norm(normal[:2]), normal[2]))
    # One floating-point step allows the inclusive five-degree boundary without
    # introducing a physical tolerance above the stated construction limit.
    if tilt > np.nextafter(REGION_TILT_LIMIT_RAD, np.inf):
        raise ValueError("tilted/inverted support regions exceed the candidate construction limit: "
                         f"region_tilt_rad={tilt:.12g}, "
                         f"region_tilt_limit_rad={REGION_TILT_LIMIT_RAD:.12g}")
    return {"name": site_name, "id": site,
            "center": _array(data.site_xpos[site], (3,), "site_xpos"),
            "rotation": rotation, "half_size": size,
            "region_tilt_rad": tilt, "region_tilt_limit_rad": REGION_TILT_LIMIT_RAD,
            "body_id": int(_field(model, "site_bodyid", site, "site", "bodyid"))}


def _object_geometry(base, model, data, object_name, frame):
    entry = ms.resolve_free_joint(model, object_name)
    _not_robot(entry)
    body = int(_field(model, "jnt_bodyid", _joint_id(model, entry), "joint", "bodyid"))
    origin = ms.get_object_pos(base, model, entry.name)
    bounds = [_geom_bounds(model, data, g, origin, frame) for g in _collision_geoms(model, body)]
    lo = np.min([item[0] for item in bounds], axis=0)
    hi = np.max([item[1] for item in bounds], axis=0)
    if np.any(hi - lo <= 0):
        raise ValueError(f"object {object_name!r} has degenerate collision bounds")
    return entry, origin, lo, hi


def object_support_geometry(base_state, model, data, object_name: str) -> dict:
    """Bound seeds above an unchanged free-joint support such as a plate.

    This does not invent a region site or substitute a predicate. The official
    object-level On predicate is still evaluated on the original object name.
    Candidates stay near its body origin, use its actual collision geometry,
    and leave the support's entire state untouched.
    """
    base, _ = _base(base_state, model)
    entry = ms.resolve_free_joint(model, object_name)
    _not_robot(entry)
    body = int(_field(model, "jnt_bodyid", _joint_id(model, entry), "joint", "bodyid"))
    rotation = _rotation(data.body_xmat[body], "support body_xmat")
    normal = rotation[:, 2]
    tilt = float(np.arctan2(np.linalg.norm(normal[:2]), normal[2]))
    if tilt > np.nextafter(REGION_TILT_LIMIT_RAD, np.inf):
        raise ValueError("tilted/inverted object supports exceed the candidate construction limit")
    _, origin, lo, hi = _object_geometry(base, model, data, object_name, rotation)
    # The centered square lies inside the official origin-distance disk; a
    # horizontal margin below makes boundary seeds strictly interior.
    half_xy = np.minimum(np.minimum(-lo[:2], hi[:2]), OBJECT_ON_ORIGIN_RADIUS / np.sqrt(2))
    if np.any(half_xy <= 0):
        raise ValueError("support collision bounds do not cover its body origin")
    return {"name": object_name, "id": None, "body_id": body,
            "center": origin, "rotation": rotation,
            "half_size": np.r_[half_xy, max(abs(lo[2]), abs(hi[2]))],
            "region_tilt_rad": tilt, "region_tilt_limit_rad": REGION_TILT_LIMIT_RAD}


def state_diff_whitelist(base_state, edited_state, model, allowed_indices) -> dict:
    """Exact numeric diff against explicit flattened-state indices, not prefixes."""
    base, layout = _base(base_state, model)
    edited, _ = _base(edited_state, model)
    allowed = set()
    for index in allowed_indices:
        if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index < len(base):
            raise ValueError("allowed_indices must contain valid integer state indices")
        allowed.add(int(index))
    names = {0: ("time", "time")}
    for entry in ms.iter_joints(model):
        for segment, start, count in (("qpos", layout.qpos_slice.start + entry.qpos_adr, entry.qpos_dim),
                                      ("qvel", layout.qvel_slice.start + entry.dof_adr, entry.dof_dim)):
            for offset in range(count):
                names[start + offset] = (segment, f"{entry.name}[{offset}]")
    changed = []
    for index in np.flatnonzero(base != edited):
        index = int(index)
        segment, name = names.get(index, ("act", f"act[{index - (1 + layout.nq + layout.nv)}]"))
        changed.append({"index": index, "segment": segment, "name": name,
                        "before": float(base[index]), "after": float(edited[index]),
                        "allowed": index in allowed})
    unexpected = [item["index"] for item in changed if not item["allowed"]]
    return {"valid": not unexpected, "unexpected_indices": unexpected, "changed": changed}


def _candidate(base, state, model, allowed, joints, placements, diagnostics):
    audit = state_diff_whitelist(base, state, model, allowed)
    if not audit["valid"]:
        raise ValueError("construction changed a non-whitelisted state coordinate")
    return {"state": state.copy(), "allowed_indices": sorted(set(allowed)),
            "edited_joints": list(joints), "placements": deepcopy(placements),
            "diagnostics": {"status": "candidate", "predicate_verified": False,
                            "physics_validated": False,
                            "base_state_sha256": hashlib.sha256(base.tobytes()).hexdigest(),
                            "diff": audit, **diagnostics}}


def placement_candidates(base_state, model, data, object_name: str, region_site: str, *,
                         relation: str = "in", reservation_objects=None,
                         clearances=(0.002, 0.01, 0.025), max_candidates: int = 24,
                         horizontal_margin: float = 0.001, target_kind: str = "region") -> list[dict]:
    """Enumerate fixed slot/height candidates using collision support geometry.

    Provide the same ordered ``reservation_objects`` in every mask (including
    10/01) when multiple objects share a region. Matching reservation plans are
    paired by ``combine_goal_candidates``. Bounding boxes guide candidates but
    do not prove absence of contact; especially, diagonal cylinders can have
    overlapping AABBs without intersecting. Seed quaternions remain unchanged,
    but the edit whitelist includes the target object's full free-joint pose:
    after settling, the driver must transplant its actual settled orientation
    together with position and velocity into every matching completed mask.
    Near-horizontal support tilt is retained, not corrected. Local-frame AABBs
    only provide conservative seeds; gravity settling and full physical checks
    must reject unstable, colliding, or goal-invalid candidates.
    """
    base, layout = _base(base_state, model)
    limit = _limit(max_candidates, "max_candidates")
    if relation not in ("in", "on"):
        raise ValueError("relation must be 'in' or 'on'")
    if target_kind not in ("region", "object") or target_kind == "object" and relation != "on":
        raise ValueError("object targets require On; target_kind must be region or object")
    if target_kind == "object" and object_name == region_site:
        raise ValueError("an object cannot be placed on itself")
    if not np.array_equal(_array(data.qpos, (layout.nq,), "data.qpos"), base[layout.qpos_slice]):
        raise ValueError("data.qpos differs from base_state; restore and forward the base first")
    heights = _array(clearances, name="clearances")
    if heights.ndim != 1 or not heights.size or np.any(heights < 0):
        raise ValueError("clearances must be nonnegative local support offsets")
    margin = float(horizontal_margin)
    if not np.isfinite(margin) or margin < 0:
        raise ValueError("horizontal_margin must be finite and nonnegative")
    reservations = list(reservation_objects) if reservation_objects is not None else [object_name]
    if object_name not in reservations or len(set(reservations)) != len(reservations):
        raise ValueError("reservation_objects must include the object exactly once")
    region = (object_support_geometry(base, model, data, region_site) if target_kind == "object"
              else region_geometry(model, data, region_site))
    rotation, center, half = region["rotation"], region["center"], region["half_size"]
    entry, origin, bottom, top = _object_geometry(base, model, data, object_name, rotation)
    _, _, world_bottom, world_top = _object_geometry(base, model, data, object_name, np.eye(3))
    # Feasible free-joint origins account for non-centered object collision geoms.
    low = -half[:2] + margin - bottom[:2]
    high = half[:2] - margin - top[:2]
    footprint_contained = bool(np.all(low <= high)) and target_kind == "region"
    if target_kind == "object" or not footprint_contained:
        if relation == "in":
            return []
        # On permits overhang (e.g. a frying-pan handle). Bound the object
        # origin inside the support, never silently stretch an In container.
        low, high = -half[:2] + margin, half[:2] - margin
        if np.any(low > high):
            return []
    support = [_geom_bounds(model, data, geom, center, rotation)
               for geom in _collision_geoms(model, region["body_id"])]
    slot = reservations.index(object_name)
    if len(reservations) == 1:
        offsets = [(0., 0.), (-.75, 0.), (.75, 0.), (0., -.75), (0., .75),
                   (-.75, -.75), (.75, .75), (-.75, .75), (.75, -.75)]
    else:
        # Diagonal-first, then axial layouts. Fixed order, independent of mask.
        offsets = []
        for phase in (np.pi / 4, -np.pi / 4, 0., np.pi / 2,
                      5 * np.pi / 4, 3 * np.pi / 4, np.pi, 3 * np.pi / 2):
            angle = phase + 2 * np.pi * slot / len(reservations)
            vector = np.array([np.cos(angle), np.sin(angle)])
            offsets.append(tuple(vector / np.max(np.abs(vector))))
    allowed = list(range(1 + entry.qpos_adr, 1 + entry.qpos_adr + entry.qpos_dim))
    allowed += list(range(layout.qvel_slice.start + entry.dof_adr,
                          layout.qvel_slice.start + entry.dof_adr + entry.dof_dim))
    output = []
    for plan, offset in enumerate(offsets):
        xy = (low + high) / 2 + np.asarray(offset) * (high - low) / 2
        supporting = [hi[2] for lo, hi in support
                      if np.all(xy >= lo[:2]) and np.all(xy <= hi[:2])
                      and (relation == "on" or hi[2] <= 0)]
        if not supporting:
            continue
        floor = max(supporting)
        for clearance in heights:
            local = np.array([*xy, floor - bottom[2] + clearance])
            if relation == "in" and not -half[2] <= local[2] <= half[2]:
                continue
            position = center + rotation @ local
            support_world_position = center + rotation @ np.array([*xy, floor])
            state = ms.clear_object_velocity(ms.set_object_pos(base, model, entry.name, position),
                                             model, entry.name)
            placement = {"object": object_name, "joint": entry.name, "region": region_site,
                         "target_kind": target_kind,
                         "relation": relation, "position": position.tolist(),
                         "aabb_min": (position + world_bottom).tolist(),
                         "aabb_max": (position + world_top).tolist(),
                         "reservation_objects": reservations, "reservation_plan": plan,
                         "slot_index": slot, "clearance": float(clearance)}
            output.append(_candidate(base, state, model, allowed, [entry.name], [placement], {
                "method": "region_collision_support", "region_center": center.tolist(),
                "target_kind": target_kind, "full_collision_footprint_contained": footprint_contained,
                "origin_only_search": not footprint_contained,
                "region_half_size": half.tolist(), "region_rotation": rotation.tolist(),
                "region_tilt_rad": region["region_tilt_rad"],
                "region_tilt_limit_rad": region["region_tilt_limit_rad"],
                "gravity_settle_required": True,
                "object_bottom_offset": float(bottom[2]), "support_local_z": float(floor),
                "support_world_z": float(support_world_position[2]),
                "support_world_position": support_world_position.tolist(),
                "candidate_local_origin": local.tolist(),
                "seed_orientation_preserved": True,
                "settled_component_includes_orientation": True,
                "zeroed_velocity_joint": entry.name,
            }))
            if len(output) >= limit:
                return output
    return output


def joint_candidates(base_state, model, joint_name: str, *, predicate_range=None,
                     predicate_range_source: str | None = None, sample_count: int = 9) -> list[dict]:
    """Enumerate interior values in a bounded hinge/slide range, both directions.

    Without an explicitly sourced predicate range, these are only geometric
    samples and may leave the goal false. Never infer an opening direction.
    With a predicate range, sample its intersection with the mechanical range;
    the driver still has to evaluate the official predicate after restoration.
    """
    base, layout = _base(base_state, model)
    count = _limit(sample_count, "sample_count")
    entry = ms.resolve_single_dof_joint(model, joint_name)
    _not_robot(entry)
    joint_id = _joint_id(model, entry)
    if not bool(_field(model, "jnt_limited", joint_id, "joint", "limited")):
        raise ValueError("unlimited joint cannot be assigned an invented search range")
    limits = _array(_field(model, "jnt_range", joint_id, "joint", "range"), (2,), "joint range")
    low, high = limits
    if low >= high:
        raise ValueError("joint range must be strictly increasing")
    supplied = None
    if predicate_range is not None:
        if not isinstance(predicate_range_source, str) or not predicate_range_source.strip():
            raise ValueError("predicate_range requires a documented predicate_range_source")
        supplied = _array(predicate_range, (2,), "predicate_range")
        if supplied[0] >= supplied[1]:
            raise ValueError("predicate_range must be strictly increasing")
        low, high = max(low, supplied[0]), min(high, supplied[1])
        if low >= high:
            raise ValueError("predicate range has no nonempty interior mechanical intersection")
    # Interior only, avoiding joint stops and exact strict predicate boundaries.
    samples = np.linspace(low, high, count + 2)[1:-1]
    samples = sorted(samples, key=lambda value: (abs(value - (low + high) / 2), value))
    allowed = [1 + entry.qpos_adr, layout.qvel_slice.start + entry.dof_adr]
    output = []
    for value in samples:
        state = ms.set_joint_pos(base, model, entry.name, float(value))
        state[allowed[1]] = 0.
        output.append(_candidate(base, state, model, allowed, [entry.name], [], {
            "method": "bounded_single_dof", "joint": entry.name,
            "joint_range": limits.tolist(), "predicate_range": None if supplied is None else supplied.tolist(),
            "predicate_range_source": predicate_range_source, "sample_interval": [float(low), float(high)],
            "chosen_value": float(value), "opening_direction_assumed": False,
        }))
    return output


def drawer_candidates(base_state, model, site_name: str, contract: dict, *,
                      predicate_range, predicate_range_source: str,
                      sample_count: int = 9) -> list[dict]:
    """Edit one explicitly verified drawer slide, never a fixture name prefix.

    The driver separately verifies LIBERO's site-to-joints registration and
    predicate interval. Here, compiled topology must agree: the named region
    belongs directly to its one named slide body, under the pinned fixed base.
    Other drawers, fixture pose, robot, time and every unrelated slot survive.
    """
    entry = ms.resolve_single_dof_joint(model, contract["joint"])
    if entry.name != contract["joint"]:
        raise ValueError("drawer contract requires an exact joint name")
    joint_id = _joint_id(model, entry)
    try:
        site_id = int(model.site_name2id(site_name))
    except AttributeError:
        site_id = int(model.site(site_name).id)
    if site_id < 0 or site_id >= int(model.nsite):
        raise ValueError("drawer region site is missing")
    body = int(_field(model, "site_bodyid", site_id, "site", "bodyid"))
    owner = int(_field(model, "jnt_bodyid", joint_id, "joint", "bodyid"))
    parent = int(_field(model, "body_parentid", body, "body", "parentid"))
    if (body != owner or ms.body_name(model, body) != contract["site_body"]
            or ms.body_name(model, parent) != contract["parent_body"]
            or int(_field(model, "site_type", site_id, "site", "type")) != 6
            or int(_field(model, "jnt_type", joint_id, "joint", "type")) != ms.MJ_JNT_SLIDE
            or not np.array_equal(_field(model, "jnt_range", joint_id, "joint", "range"), contract["joint_range"])
            or not np.array_equal(_field(model, "jnt_axis", joint_id, "joint", "axis"), contract["joint_axis"])):
        raise ValueError("compiled drawer topology/range/axis differs from the exact joint contract")
    owners = [int(_field(model, "jnt_bodyid", index, "joint", "bodyid")) for index in range(int(model.njnt))]
    if owners.count(body) != 1:
        raise ValueError("drawer body must own exactly one joint")
    seen = {body}
    while parent not in seen:
        seen.add(parent)
        if parent in owners:
            raise ValueError("drawer fixture ancestry must be fixed")
        next_parent = int(_field(model, "body_parentid", parent, "body", "parentid"))
        if next_parent == parent:
            break
        parent = next_parent
    else:
        raise ValueError("drawer body ancestry contains a cycle")
    candidates = joint_candidates(base_state, model, entry.name, predicate_range=predicate_range,
                                   predicate_range_source=predicate_range_source, sample_count=sample_count)
    for candidate in candidates:
        candidate["diagnostics"].update(region_site=site_name, exact_joint_contract=deepcopy(contract),
                                         compiled_site_joint_ancestry_verified=True)
    return candidates


def _fair_candidate_product(candidate_lists):
    """Deterministic diagonals visit every component before Cartesian tails.

    Lexicographic products can spend the entire budget varying only the last
    goal (e.g. 24 placements, all paired with one of 9 drawer values). The first
    diagonal advances every goal's rank, wrapping shorter lists. Subsequent
    cyclic offsets cover the full product without returning duplicate tuples.
    This reorders search only; the caller still bounds examined combinations
    and applies all reservation, whitelist and later physical checks.
    """
    lengths = [len(items) for items in candidate_lists]
    if not lengths:
        yield ()
        return
    if not all(lengths):
        return
    seen = set()
    for offsets in itertools.product(*(range(length) for length in lengths[1:])):
        for rank in range(max(lengths)):
            indices = (rank % lengths[0], *( (rank + offset) % length
                         for offset, length in zip(offsets, lengths[1:])))
            if indices in seen:
                continue
            seen.add(indices)
            yield tuple(items[index] for items, index in zip(candidate_lists, indices))


def combine_goal_candidates(base_state, model, per_goal_candidates, mask, *,
                            max_candidates: int = 32) -> list[dict]:
    """Combine independent edits from exactly the same base; 00 stays untouched.

    Placement AABB overlap is diagnostic, not a physical collision verdict.
    Shared-region reservations must agree and choose distinct slots. No state
    outside the selected goals' exact whitelist is copied from a candidate.
    """
    base, _ = _base(base_state, model)
    limit = _limit(max_candidates, "max_candidates")
    mask_array = np.asarray(mask)
    if mask_array.dtype.kind != "b" or mask_array.shape != (len(per_goal_candidates),) or not mask_array.size:
        raise ValueError("mask must be one boolean per goal candidate list")
    selected = [per_goal_candidates[i] for i, flag in enumerate(mask_array) if flag]
    base_hash = hashlib.sha256(base.tobytes()).hexdigest()
    output = []
    # Stop after a bounded number of combinations, including rejected pairs.
    for combination in itertools.islice(_fair_candidate_product(selected), max(1024, limit * 64)):
        state, allowed, joints, placements, edits = base.copy(), set(), [], [], []
        for candidate in combination:
            if candidate["diagnostics"]["base_state_sha256"] != base_hash:
                raise ValueError("candidate was constructed from a different base state")
            candidate_indices = set(candidate["allowed_indices"])
            if allowed & candidate_indices:
                raise ValueError("independent goal edits have overlapping state whitelists")
            if not state_diff_whitelist(base, candidate["state"], model, candidate_indices)["valid"]:
                raise ValueError("candidate has an unexpected state edit")
            indices = sorted(candidate_indices)
            state[indices] = candidate["state"][indices]
            allowed.update(indices)
            joints.extend(candidate["edited_joints"])
            placements.extend(deepcopy(candidate["placements"]))
            edits.append(deepcopy(candidate["diagnostics"]))
        pairs, incompatible = [], False
        for first, second in itertools.combinations(placements, 2):
            if first["region"] == second["region"]:
                if (first["reservation_objects"] != second["reservation_objects"]
                        or first["reservation_plan"] != second["reservation_plan"]
                        or first["slot_index"] == second["slot_index"]):
                    incompatible = True
                    break
            min_a, max_a = np.asarray(first["aabb_min"]), np.asarray(first["aabb_max"])
            min_b, max_b = np.asarray(second["aabb_min"]), np.asarray(second["aabb_max"])
            center_distance = float(np.linalg.norm((min_a + max_a - min_b - max_b)[:2] / 2))
            if center_distance <= 1e-9:
                incompatible = True
                break
            gap = np.maximum(min_b - max_a, min_a - max_b)
            pairs.append({"objects": [first["object"], second["object"]],
                          "horizontal_center_distance": center_distance,
                          "aabb_overlap": bool(np.all(gap < 0)),
                          "aabb_gap": gap.tolist(), "actual_contacts_checked": False})
        if incompatible:
            continue
        output.append(_candidate(base, state, model, allowed, joints, placements, {
            "method": "independent_goal_composition", "requested_mask": mask_array.tolist(),
            "goal_edits": edits, "placement_pairs": pairs,
        }))
        if len(output) >= limit:
            break
    return output
