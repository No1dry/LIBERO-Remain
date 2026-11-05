"""Pure-read, conservative whole-group world-axis release certificates.

MuJoCo 2.3.7 engine_collision_convex.c:mjccd_support uses native box half
sizes and compiled mesh vertices, then geom_xmat/geom_xpos. A projection
interval contains the convex collision hull; its gap is NOT closest distance.
No MuJoCo imports, native calls, RNG, controller or policy access occur here.
"""
from copy import deepcopy
import hashlib
import numpy as np

from .evaluation import (RELEASE_V1, RELEASE_V2, MEASUREMENT_SCHEMA, canonical_hash,
                         validate_evaluation_contract)

STATIC_SCHEMA = "remaining-finish-release-geometry-v1"
POSE_SCHEMA = "remaining-finish-release-poses-v1"
AXES = ("x", "y", "z")
MARGIN = 0.002


class MeasurementError(ValueError):
    """Invalid measurement evidence, never a held/policy-negative label."""


def _array(value, shape, name, *, integer=False):
    array = np.asarray(value)
    if (array.shape != shape or array.dtype.kind not in ("iu" if integer else "fiu")
            or not np.all(np.isfinite(array))):
        raise MeasurementError(f"invalid measurement {name}: expected finite shape {shape}")
    return array.astype(np.int64 if integer else np.float64, copy=True)


def _count(value, name, minimum=0):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise MeasurementError(f"invalid measurement {name}")
    return int(value)


def _names(model, kind, count):
    result = [getattr(model, kind + "_id2name")(i) for i in range(count)]
    present = [n for n in result if n is not None]
    if any(not isinstance(n, str) or not n for n in present) or len(set(present)) != len(present):
        raise MeasurementError(f"invalid {kind} names")
    return result


def _ids(model, names):
    if not isinstance(names, (list, tuple)) or not names or len(set(names)) != len(names):
        raise MeasurementError("incomplete/duplicate collision geometry group")
    result = []
    for name in names:
        if not isinstance(name, str) or not name:
            raise MeasurementError("invalid collision geometry name")
        gid = _count(model.geom_name2id(name), "geometry ID")
        if gid >= model.ngeom or model.geom_id2name(gid) != name:
            raise MeasurementError("collision geometry name/ID identity mismatch")
        result.append(gid)
    return result


def _descendant(body, root, parents):
    for _ in range(len(parents)):
        if body == root:
            return True
        if body == 0:
            return False
        body = int(parents[body])
    raise MeasurementError("cyclic body ancestry")


def _unsigned_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_measurement_static(model, objects, gripper, *, compiled_xml=None, contact_filter_status="unverified"):
    """Read native compiled geometry once. ``objects`` contains all released roles.

    Completeness is independently checked against every collision-enabled geom
    under each object's / gripper's actual root body, including both fingerpads.
    """
    try:
        raw = getattr(model, "_model", model)
        n, b, nm = (_count(getattr(raw, key), key, minimum) for key, minimum in
                    (("ngeom", 1), ("nbody", 1), ("nmesh", 0)))
        arrays = {}
        for name in ("geom_type", "geom_bodyid", "geom_dataid", "geom_contype", "geom_conaffinity"):
            arrays[name] = _array(getattr(raw, name), (n,), name, integer=True).tolist()
        for name in ("geom_margin", "geom_gap", "geom_rbound"):
            arrays[name] = _array(getattr(raw, name), (n,), name).tolist()
        for name, width in (("geom_size", 3), ("geom_pos", 3), ("geom_quat", 4)):
            arrays[name] = _array(getattr(raw, name), (n, width), name).tolist()
        for name in ("body_parentid", "body_weldid"):
            arrays[name] = _array(getattr(raw, name), (b,), name, integer=True).tolist()
        groups = {name: _ids(model, list(obj.contact_geoms)) for name, obj in objects.items()}
        if set(groups) & {"hand", "left_fingerpad", "right_fingerpad"}:
            raise MeasurementError("reserved geometry group name")
        groups["hand"] = _ids(model, list(gripper.contact_geoms))
        for side in ("left_fingerpad", "right_fingerpad"):
            groups[side] = _ids(model, gripper.important_geoms[side])
        owners = {**objects, "hand": gripper}
        roots = {}
        for name, obj in owners.items():
            root = obj.root_body
            rid = _count(model.body_name2id(root), "root body ID")
            if rid >= b or model.body_id2name(rid) != root:
                raise MeasurementError("owner root body identity mismatch")
            roots[name] = rid
        relevant = sorted(set(i for ids in groups.values() for i in ids))
        meshes = {}
        for gid in relevant:
            if arrays["geom_type"][gid] != 7:
                continue
            mid = arrays["geom_dataid"][gid]
            if not 0 <= mid < nm:
                raise MeasurementError("invalid compiled mesh reference")
            first = _count(raw.mesh_vertadr[mid], "mesh vertex address")
            count = _count(raw.mesh_vertnum[mid], "mesh vertex count", 1)
            if first + count > len(raw.mesh_vert):
                raise MeasurementError("compiled mesh vertex range exceeds storage")
            verts = _array(raw.mesh_vert[first:first + count], (count, 3), "compiled mesh vertices")
            meshes[str(mid)] = {"name": model.mesh_id2name(mid), "vertex_address": first,
                                "vertices": verts.tolist(), "vertices_sha256": canonical_hash(verts.tolist())}
        pairs = _count(raw.npair, "npair")
        excludes = _count(raw.nexclude, "nexclude")
        filters = {"pair_geom1": _array(raw.pair_geom1, (pairs,), "pair_geom1", integer=True).tolist(),
                   "pair_geom2": _array(raw.pair_geom2, (pairs,), "pair_geom2", integer=True).tolist(),
                   "exclude_signature": _array(raw.exclude_signature, (excludes,), "exclude_signature", integer=True).tolist(),
                   "collision": _count(raw.opt.collision, "collision"),
                   "disableflags": _count(raw.opt.disableflags, "disableflags"),
                   "enableflags": _count(raw.opt.enableflags, "enableflags"),
                   "contact_filter_callback": contact_filter_status}
        # The native wrapper serializes through mj_saveLastXML. Use it only
        # once on initialization; per-frame identity checks reuse this binding.
        xml = model.get_xml() if compiled_xml is None else compiled_xml
        if not isinstance(xml, str) or not xml:
            raise MeasurementError("compiled model XML unavailable")
        result = {"schema_version": STATIC_SCHEMA, "method": RELEASE_V2,
                  "compiled_model_xml": xml, "compiled_model_xml_sha256": _unsigned_hash(xml),
                  "ngeom": n, "nbody": b, "nmesh": nm,
                  "geom_names": _names(model, "geom", n), "body_names": _names(model, "body", b),
                  "arrays": arrays, "groups": groups, "owner_roots": roots,
                  "relevant_geom_ids": relevant, "meshes": meshes, "filters": filters,
                  "projection_semantics": "compiled box halfsizes / mesh vertices; full group world-axis union; conservative gap, not closest distance"}
        result["static_sha256"] = canonical_hash(result)
        return validate_measurement_static(result)
    except (AttributeError, KeyError, IndexError, TypeError) as error:
        raise MeasurementError(f"measurement geometry field unavailable: {type(error).__name__}: {error}") from error


def validate_measurement_static(static):
    """Validate self-contained JSON geometry and all group/reference identities."""
    try:
        if not isinstance(static, dict) or static.get("schema_version") != STATIC_SCHEMA or static.get("method") != RELEASE_V2:
            raise MeasurementError("unsupported release geometry schema/method")
        if static.get("static_sha256") != canonical_hash({k: v for k, v in static.items() if k != "static_sha256"}):
            raise MeasurementError("release geometry static hash mismatch")
        if _unsigned_hash(static["compiled_model_xml"]) != static["compiled_model_xml_sha256"]:
            raise MeasurementError("compiled model XML hash mismatch")
        n, b, nm = (_count(static[k], k, minimum) for k, minimum in (("ngeom", 1), ("nbody", 1), ("nmesh", 0)))
        for key, count in (("geom_names", n), ("body_names", b)):
            names = static[key]
            if not isinstance(names, list) or len(names) != count:
                raise MeasurementError("invalid geometry/body name table")
            present = [v for v in names if v is not None]
            if any(not isinstance(v, str) or not v for v in present) or len(set(present)) != len(present):
                raise MeasurementError("ambiguous geometry/body name table")
        a = static["arrays"]
        ints = {k: _array(a[k], (n,), k, integer=True) for k in
                ("geom_type", "geom_bodyid", "geom_dataid", "geom_contype", "geom_conaffinity")}
        parents = _array(a["body_parentid"], (b,), "body_parentid", integer=True)
        welds = _array(a["body_weldid"], (b,), "body_weldid", integer=True)
        if parents[0] != 0 or np.any((parents < 0) | (parents >= b)):
            raise MeasurementError("invalid body ancestry")
        for body in range(1, b):
            _descendant(body, 0, parents)
        if welds[0] != 0 or np.any((welds < 0) | (welds >= b)) or any(not _descendant(i, int(welds[i]), parents) for i in range(b)):
            raise MeasurementError("invalid welded body reference")
        if np.any((ints["geom_bodyid"] < 0) | (ints["geom_bodyid"] >= b)) or np.any((ints["geom_type"] < 0) | (ints["geom_type"] > 7)):
            raise MeasurementError("invalid geometry type/body reference")
        if np.any(ints["geom_contype"] < 0) or np.any(ints["geom_conaffinity"] < 0):
            raise MeasurementError("negative collision bitmask")
        for key in ("geom_margin", "geom_gap", "geom_rbound"):
            vals = _array(a[key], (n,), key)
            if np.any(vals < 0):
                raise MeasurementError("negative geometry margin/gap/radius")
        size = _array(a["geom_size"], (n, 3), "geom_size")
        _array(a["geom_pos"], (n, 3), "geom_pos")
        quat = _array(a["geom_quat"], (n, 4), "geom_quat")
        if np.any(size < 0) or np.any(np.abs(np.linalg.norm(quat, axis=1) - 1) > 1e-7):
            raise MeasurementError("invalid geometry size/quaternion")
        groups, roots = static["groups"], static["owner_roots"]
        if not isinstance(groups, dict) or not isinstance(roots, dict) or set(groups) != set(roots) | {"left_fingerpad", "right_fingerpad"} or "hand" not in roots:
            raise MeasurementError("incomplete collision group/owner inventory")
        for name, ids in groups.items():
            if (not isinstance(name, str) or not name or not isinstance(ids, list) or not ids
                    or any(type(i) is not int or not 0 <= i < n for i in ids) or len(set(ids)) != len(ids)):
                raise MeasurementError("invalid/duplicate collision group IDs")
        for name, root in roots.items():
            if type(root) is not int or not 0 < root < b:
                raise MeasurementError("invalid collision owner root")
            expected = {i for i in range(n) if (ints["geom_contype"][i] or ints["geom_conaffinity"][i])
                        and _descendant(int(ints["geom_bodyid"][i]), root, parents)}
            if expected != set(groups[name]):
                raise MeasurementError(f"incomplete collision geometry group: {name}")
        hand = set(groups["hand"])
        if (not set(groups["left_fingerpad"]).issubset(hand) or not set(groups["right_fingerpad"]).issubset(hand)
                or set(groups["left_fingerpad"]) & set(groups["right_fingerpad"])):
            raise MeasurementError("fingerpad coverage mismatch")
        owner_groups = [set(groups[name]) for name in roots]
        if any(x & y for i, x in enumerate(owner_groups) for y in owner_groups[i+1:]):
            raise MeasurementError("collision owner groups overlap")
        relevant = sorted(set(i for ids in groups.values() for i in ids))
        if static["relevant_geom_ids"] != relevant:
            raise MeasurementError("relevant geometry inventory mismatch")
        needed = set()
        for gid in relevant:
            kind, mid = ints["geom_type"][gid], ints["geom_dataid"][gid]
            if kind == 6 and np.any(size[gid] <= 0):
                raise MeasurementError("nonpositive box halfsize")
            if kind == 6 and mid != -1:
                raise MeasurementError("box has invalid mesh data reference")
            if kind == 7:
                if not 0 <= mid < nm:
                    raise MeasurementError("invalid compiled mesh ID")
                needed.add(str(mid))
        if set(static["meshes"]) != needed:
            raise MeasurementError("compiled mesh coverage mismatch")
        for mesh in static["meshes"].values():
            verts = np.asarray(mesh["vertices"])
            if verts.ndim != 2 or verts.shape[1] != 3 or not len(verts):
                raise MeasurementError("invalid compiled mesh vertex shape")
            _array(verts, verts.shape, "compiled mesh vertices")
            _count(mesh["vertex_address"], "vertex address")
            if mesh["vertices_sha256"] != canonical_hash(mesh["vertices"]):
                raise MeasurementError("compiled mesh vertex hash mismatch")
        filters = static["filters"]
        if filters["contact_filter_callback"] not in {"absent", "present", "unverified"}:
            raise MeasurementError("invalid contact filter callback coverage")
        for name in ("collision", "disableflags", "enableflags"):
            _count(filters[name], name)
        if len(filters["pair_geom1"]) != len(filters["pair_geom2"]):
            raise MeasurementError("invalid explicit collision pair inventory")
        for name in ("pair_geom1", "pair_geom2"):
            if any(type(i) is not int or not 0 <= i < n for i in filters[name]):
                raise MeasurementError("invalid explicit collision pair reference")
        for signature in filters["exclude_signature"]:
            _count(signature, "exclude signature")
            if signature >> 16 >= b or signature & 65535 >= b:
                raise MeasurementError("invalid explicit body exclusion reference")
        return deepcopy(static)
    except MeasurementError:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as error:
        raise MeasurementError(f"invalid release geometry evidence: {error}") from error


def _poses(poses, static):
    if (not isinstance(poses, dict) or set(poses) != {"schema_version", "geom_ids", "positions", "rotations"}
            or poses["schema_version"] != POSE_SCHEMA or poses["geom_ids"] != static["relevant_geom_ids"]):
        raise MeasurementError("dynamic geometry identity/coverage mismatch")
    n = len(poses["geom_ids"])
    pos = _array(poses["positions"], (n, 3), "world geometry positions")
    rot = _array(poses["rotations"], (n, 3, 3), "world geometry rotations")
    if not np.allclose(rot.transpose(0, 2, 1) @ rot, np.eye(3), rtol=0, atol=1e-7) or np.any(np.abs(np.linalg.det(rot) - 1) > 1e-7):
        raise MeasurementError("invalid world geometry rotation")
    return {gid: (pos[i], rot[i]) for i, gid in enumerate(poses["geom_ids"])}


def read_geometry_pose(model, data, static):
    n, ids = static["ngeom"], static["relevant_geom_ids"]
    raw = getattr(data, "_data", data)
    pos = _array(raw.geom_xpos, (n, 3), "geom_xpos")
    rot = _array(raw.geom_xmat, (n, 9), "geom_xmat").reshape(n, 3, 3)
    result = {"schema_version": POSE_SCHEMA, "geom_ids": ids.copy(),
              "positions": pos[ids].tolist(), "rotations": rot[ids].tolist()}
    _poses(result, static)
    return result


def project_geometry(kind, size, vertices, position, rotation, *, conservative=True):
    """World-axis intervals; default includes outward floating-point padding.

    ``conservative=False`` is only the nominal diagnostic projection. The
    certificate always uses padded intervals. gamma(16) bounds the few float64
    products/additions and extreme selection; nextafter rounds outwards again.
    """
    position = _array(position, (3,), "projection position")
    rotation = _array(rotation, (3, 3), "projection rotation")
    if kind == 6:
        size = _array(size, (3,), "box halfsizes")
        if np.any(size <= 0):
            raise MeasurementError("nonpositive box halfsize")
        radius = np.abs(rotation) @ size
        nominal = np.stack((position - radius, position + radius), axis=1)
        magnitude = np.abs(position) + np.abs(rotation) @ np.abs(size)
    elif kind == 7:
        verts = np.asarray(vertices)
        if verts.ndim != 2 or verts.shape[1] != 3 or not len(verts):
            raise MeasurementError("invalid compiled mesh vertices")
        verts = _array(verts, verts.shape, "compiled mesh vertices")
        world = verts @ rotation.T + position
        nominal = np.stack((world.min(axis=0), world.max(axis=0)), axis=1)
        magnitude = np.abs(position) + np.abs(rotation) @ np.max(np.abs(verts), axis=0)
    else:
        raise MeasurementError("projection called with unsupported geometry type")
    if not np.isfinite(nominal).all() or not np.isfinite(magnitude).all():
        raise MeasurementError("geometry projection overflow")
    if not conservative:
        return nominal
    eps = np.finfo(np.float64).eps
    gamma = 16 * eps / (1 - 16 * eps)
    padding = gamma * np.maximum(magnitude, np.finfo(np.float64).tiny)
    bounded = np.stack((np.nextafter(nominal[:, 0] - padding, -np.inf),
                        np.nextafter(nominal[:, 1] + padding, np.inf)), axis=1)
    if not np.isfinite(bounded).all():
        raise MeasurementError("conservative geometry projection overflow")
    return bounded


def separation_certificate(static, poses, object_name):
    """Whole groups only; unsupported valid coverage never certifies release."""
    locations = _poses(poses, static)
    a, groups, filters = static["arrays"], static["groups"], static["filters"]
    if object_name not in static["owner_roots"] or object_name == "hand":
        raise MeasurementError("unknown release object geometry group")
    objids, handids = groups[object_name], groups["hand"]
    relevant = sorted(set(objids + handids))
    reasons = []
    unsupported = [i for i in relevant if a["geom_type"][i] not in (6, 7)]
    if unsupported:
        reasons.append("unsupported_geometry_type")
    if any(a["geom_margin"][i] != 0 or a["geom_gap"][i] != 0 for i in relevant):
        reasons.append("unsupported_nonzero_margin_or_gap")
    if filters["pair_geom1"] or filters["exclude_signature"] or filters["collision"] != 0 or filters["disableflags"] != 0 or filters["enableflags"] != 0:
        reasons.append("unsupported_collision_filter_configuration")
    if filters["contact_filter_callback"] != "absent":
        reasons.append("contact_filter_callback_" + filters["contact_filter_callback"])
    compatible = sum(bool((a["geom_contype"][i] & a["geom_conaffinity"][j]) or
                          (a["geom_contype"][j] & a["geom_conaffinity"][i])) for i in objids for j in handids)
    if compatible != len(objids) * len(handids):
        reasons.append("incompatible_collision_masks")
    # Match the conservative unsupported boundary for built-in welded/parent
    # body filtering. World parents (weld ID 0) are exempt in MuJoCo 2.3.7.
    body_filtered = []
    for i in objids:
        for j in handids:
            w1, w2 = (a["body_weldid"][a["geom_bodyid"][k]] for k in (i, j))
            p1, p2 = (a["body_weldid"][a["body_parentid"][w]] for w in (w1, w2))
            if w1 == w2 or (w1 != 0 and w2 != 0 and (w1 == p2 or w2 == p1)):
                body_filtered.append([i, j])
    if body_filtered:
        reasons.append("unsupported_welded_or_parent_body_filter")
    certificate = {"method": RELEASE_V2, "object_name": object_name,
                   "static_sha256": static["static_sha256"], "axes": list(AXES),
                   "clearance_margin_m": MARGIN, "object_geom_ids": objids.copy(), "hand_geom_ids": handids.copy(),
                   "compatible_pairs": compatible, "expected_pairs": len(objids) * len(handids),
                   "body_filtered_pairs": body_filtered,
                   "coverage": "unsupported" if reasons else "complete", "coverage_reasons": reasons,
                   "unsupported_geom_ids": unsupported, "certified": False,
                   "selected_axis": None, "gap_lower_bound_m": None, "axes_evidence": [], "geom_intervals": []}
    if reasons:
        return certificate
    intervals, nominal = {}, {}
    for gid in relevant:
        mesh = static["meshes"].get(str(a["geom_dataid"][gid]))
        args = (a["geom_type"][gid], a["geom_size"][gid], None if mesh is None else mesh["vertices"], *locations[gid])
        intervals[gid] = project_geometry(*args)
        nominal[gid] = project_geometry(*args, conservative=False)
        certificate["geom_intervals"].append({"geom_id": gid, "intervals": intervals[gid].tolist(),
            "nominal_intervals": nominal[gid].tolist(),
            "outward_padding_m": np.abs(intervals[gid] - nominal[gid]).tolist()})
    certificate["floating_point_bound"] = "float64 gamma(16) scale bound plus outward nextafter; gap subtraction rounded toward -infinity"
    gaps = []
    for axis, name in enumerate(AXES):
        record = {"axis": name}
        bounds = {}
        for label, ids in (("object", objids), ("hand", handids)):
            lo = min(ids, key=lambda i: (intervals[i][axis, 0], i))
            hi = min(ids, key=lambda i: (-intervals[i][axis, 1], i))
            bounds[label] = [float(intervals[lo][axis, 0]), float(intervals[hi][axis, 1])]
            record[label + "_interval"] = bounds[label]
            record[label + "_extreme_geom_ids"] = [lo, hi]
        gap = float(np.nextafter(max(bounds["hand"][0] - bounds["object"][1], bounds["object"][0] - bounds["hand"][1]), -np.inf))
        gaps.append(gap)
        record["gap_lower_bound_m"] = float(gap)
        certificate["axes_evidence"].append(record)
    selected = int(np.argmax(gaps))  # first x/y/z breaks an exact tie
    certificate["gap_lower_bound_m"] = float(gaps[selected])
    if gaps[selected] > MARGIN:
        certificate["certified"] = True
        certificate["selected_axis"] = AXES[selected]
    return certificate


def _validate_legacy(legacy, static, locations):
    """All unknowns must be physical v1 unknowns, never missing measurements."""
    if not isinstance(legacy, dict) or set(legacy) != {"goals", "released", "objects", "release_evidence"}:
        raise MeasurementError("incomplete legacy measurement truth")
    if not isinstance(legacy["goals"], list) or len(legacy["goals"]) != 2 or any(type(v) is not bool for v in legacy["goals"]):
        raise MeasurementError("invalid legacy goals")
    facts, groups, arrays = legacy["objects"], static["groups"], static["arrays"]
    if not isinstance(facts, dict):
        raise MeasurementError("invalid legacy object inventory")
    keys = {"method", "clearance_margin_m", "dual_pad_grasp", "any_gripper_contact", "hand_sphere_clearance_m", "pinch_capsule_clearance_m", "reason"}
    targets = []
    for name, fact in facts.items():
        if not isinstance(fact, dict) or set(fact) != {"role", "in_basket", "released", "release_evidence"}:
            raise MeasurementError("incomplete legacy object fact")
        evidence, released, role = fact["release_evidence"], fact["released"], fact["role"]
        if role not in {"target", "distractor", "fixture", "container"} or not (released is None or type(released) is bool):
            raise MeasurementError("invalid legacy object role/release")
        if role in {"fixture", "container"}:
            if (released is not None or fact["in_basket"] is not None or evidence !=
                    {"method": RELEASE_V1, "reason": "excluded_container_or_fixture_role"}):
                raise MeasurementError("invalid excluded legacy fixture/container fact")
            continue
        if type(fact["in_basket"]) is not bool or not isinstance(evidence, dict) or set(evidence) != keys:
            raise MeasurementError("legacy measurement missing/technical evidence cannot be physical unknown")
        if evidence["method"] != RELEASE_V1 or type(evidence["clearance_margin_m"]) not in (int, float) or evidence["clearance_margin_m"] != MARGIN:
            raise MeasurementError("legacy release method/margin mismatch")
        grasp, contact = evidence["dual_pad_grasp"], evidence["any_gripper_contact"]
        sphere, pinch = evidence["hand_sphere_clearance_m"], evidence["pinch_capsule_clearance_m"]
        if type(grasp) is not bool or type(contact) is not bool:
            raise MeasurementError("legacy grasp/contact measurement unavailable")
        if grasp or contact:
            expected_reason = "both_fingerpads_contact_object" if grasp else "gripper_contact_without_proven_dualpad_grasp"
            if released is not (False if grasp else None) or evidence["reason"] != expected_reason or sphere is not None or pinch is not None:
                raise MeasurementError("legacy held/contact branch inconsistent")
        else:
            if any(type(v) not in (int, float) or not np.isfinite(v) for v in (sphere, pinch)):
                raise MeasurementError("legacy sphere/pinch measurement invalid")
            # Recompute the unchanged v1 geometry using the same ordered groups.
            ids, hand = groups[name], groups["hand"]
            points = np.asarray([locations[i][0] for i in ids])
            radii = np.asarray([arrays["geom_rbound"][i] for i in ids])
            handpoints = np.asarray([locations[i][0] for i in hand])
            handradii = np.asarray([arrays["geom_rbound"][i] for i in hand])
            sphere_actual = float(np.min(np.linalg.norm(points[:, None] - handpoints[None], axis=2) - radii[:, None] - handradii[None]))
            left, right = groups["left_fingerpad"], groups["right_fingerpad"]
            lp, rp = np.asarray([locations[i][0] for i in left]), np.asarray([locations[i][0] for i in right])
            lr, rr = np.asarray([arrays["geom_rbound"][i] for i in left]), np.asarray([arrays["geom_rbound"][i] for i in right])
            aa, bb = lp.mean(axis=0), rp.mean(axis=0)
            axis = bb - aa
            length = float(axis @ axis)
            if length <= 1e-12:
                raise MeasurementError("degenerate legacy pinch segment")
            radius = max(float(np.max(np.linalg.norm(lp - aa, axis=1) + lr)), float(np.max(np.linalg.norm(rp - bb, axis=1) + rr)))
            fraction = np.clip(((points - aa) @ axis) / length, 0, 1)
            closest = aa + fraction[:, None] * axis
            pinch_actual = float(np.min(np.linalg.norm(points - closest, axis=1) - radii - radius))
            if sphere != sphere_actual or pinch != pinch_actual:
                raise MeasurementError("legacy sphere/pinch differs from recorded geometry")
            expected = True if sphere > MARGIN and pinch > MARGIN else None
            expected_reason = "no_contact_and_clear_of_hand_and_pinch_envelope" if expected else "near_hand_or_inside_pinch_envelope"
            if released is not expected or evidence["reason"] != expected_reason:
                raise MeasurementError("legacy sphere/pinch branch inconsistent")
        if role == "target":
            targets.append(name)
    if len(targets) != 2:
        raise MeasurementError("legacy target inventory mismatch")
    states = [facts[name]["released"] for name in targets]
    aggregate = False if any(v is False for v in states) else True if all(v is True for v in states) else None
    if legacy["released"] is not aggregate or legacy["release_evidence"] != {"method": RELEASE_V1, "targets": {name: facts[name]["release_evidence"] for name in targets}}:
        raise MeasurementError("legacy aggregate release evidence inconsistent")


def measurement_frame(legacy, contract, static, poses):
    """Supplement v1 facts only; never changes goals, objects or control inputs."""
    contract = validate_evaluation_contract(contract)
    locations = _poses(poses, static)
    _validate_legacy(legacy, static, locations)
    result = deepcopy(legacy)
    facts = result["objects"]
    measured = {name for name, fact in facts.items() if fact["role"] in {"target", "distractor"}}
    if measured != set(static["owner_roots"]) - {"hand"}:
        raise MeasurementError("truth/geometry object inventory differs")
    for name, fact in facts.items():
        old = fact["release_evidence"]
        evidence = deepcopy(old)
        evidence["method"] = RELEASE_V2
        evidence["legacy_method"] = old["method"]
        evidence["axis_certificate"] = None
        if (fact["released"] is None and old.get("reason") == "near_hand_or_inside_pinch_envelope"
                and old.get("dual_pad_grasp") is False and old.get("any_gripper_contact") is False):
            pinch = old.get("pinch_capsule_clearance_m")
            if type(pinch) not in (int, float) or not np.isfinite(pinch):
                raise MeasurementError("eligible legacy pinch clearance is invalid")
            if pinch > MARGIN:
                cert = separation_certificate(static, poses, name)
                evidence["axis_certificate"] = cert
                if cert["certified"]:
                    fact["released"] = True
                    evidence["reason"] = "no_contact_pinch_clear_and_whole_group_axis_separated"
        fact["release_evidence"] = evidence
    target_names = [name for name, fact in facts.items() if fact["role"] == "target"]
    states = [facts[name]["released"] for name in target_names]
    result["released"] = False if any(v is False for v in states) else True if states and all(v is True for v in states) else None
    result["release_evidence"] = {"method": RELEASE_V2, "targets": {name: facts[name]["release_evidence"] for name in target_names}}
    result["measurement"] = {"schema_version": MEASUREMENT_SCHEMA, "contract_sha256": contract["contract_sha256"],
                             "legacy": deepcopy(legacy), "static_sha256": static["static_sha256"], "poses": deepcopy(poses)}
    return result


def validate_measurement_frame(frame, contract, static):
    """Offline recompute all certificates and the v1→v2 safety transition.

    Runner trace fields (step/action etc.) are ignored here, never fed to the
    geometry algorithm; all evaluator facts and measurement fields are exact.
    """
    validate_measurement_static(static)
    contract = validate_evaluation_contract(contract)
    try:
        measurement = frame["measurement"]
        if (set(measurement) != {"schema_version", "contract_sha256", "legacy", "static_sha256", "poses"}
                or measurement["schema_version"] != MEASUREMENT_SCHEMA
                or measurement["contract_sha256"] != contract["contract_sha256"]
                or measurement["static_sha256"] != static["static_sha256"]):
            raise MeasurementError("measurement contract/static binding mismatch")
        expected = measurement_frame(measurement["legacy"], contract, static, measurement["poses"])
        actual = {key: frame[key] for key in expected}
        if canonical_hash(actual) != canonical_hash(expected):
            raise MeasurementError("release certificate / v1-v2 facts differ from recomputation")
        return deepcopy(actual)
    except (AttributeError, KeyError, IndexError, TypeError) as error:
        raise MeasurementError(f"invalid release measurement frame: {error}") from error


class GeometryObserver:
    """One model generation only; a reset must construct a new observer."""
    def __init__(self, env, objects, gripper, *, contact_filter_getter=None):
        self.env, self.model, self.objects, self.gripper = env, env.sim.model, objects, gripper
        self.sim, self.raw_model = env.sim, getattr(env.sim.model, "_model", env.sim.model)
        self.contact_filter_getter = contact_filter_getter or (lambda: "unverified")
        self.static = build_measurement_static(self.model, objects, gripper,
                                              contact_filter_status=self.contact_filter_getter())

    def pose(self):
        if self.env.sim is not self.sim or self.env.sim.model is not self.model or getattr(self.model, "_model", self.model) is not self.raw_model:
            raise MeasurementError("measurement model generation changed; reset observer required")
        # XML belongs to the generation validated at reset. Rehash existing
        # compiled arrays/mesh/membership, without another get_xml/saveLastXML.
        current = build_measurement_static(self.model, self.objects, self.gripper,
                                           compiled_xml=self.static["compiled_model_xml"],
                                           contact_filter_status=self.contact_filter_getter())
        if current["static_sha256"] != self.static["static_sha256"]:
            raise MeasurementError("measurement compiled geometry/XML/group identity changed")
        return read_geometry_pose(self.model, self.env.sim.data, self.static)
