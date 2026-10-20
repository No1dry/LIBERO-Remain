"""Ten-task read-only headless evaluator. No import-time native construction.

The endpoint/confirmation logic belongs to the headless runner. This adapter
only observes official predicates, a fixed native TCP site and physical event
candidates. It never latches a hold, opens the gripper or changes an action.
"""
from copy import deepcopy
import sys
import numpy as np

from ..libero_env import LiberoGoalEnv, _task_environment
from ..finish.environment import _release
from .roles import build_roles, task_key, validate_roles
from . import geometry as geo

LEGACY_SCHEMA = "remaining-headless-measurement-v1"
SCHEMA = "remaining-headless-measurement-v2"
LEGACY_SUPPORT_RULE = "direct-table-top-contact-body-origin-v1"
SUPPORT_RULE = "direct-table-top-contact-no-body-origin-v2"
LIFT_METERS = DROP_METERS = .02
EVENTS = ("wrong_grasp", "wrong_placement", "table_drop")


def _finite(value, shape, label):
    return geo._array(value, shape, label)


def _callback_status():
    getter = getattr(sys.modules.get("mujoco"), "get_mjcb_contactfilter", None)
    if not callable(getter): return "unverified"
    try: return "absent" if getter() is None else "present"
    except Exception: return "unverified"


def _tri_and(*values):
    return False if any(v is False for v in values) else True if all(v is True for v in values) else None


def _tri_or(values):
    values = list(values)
    return True if any(v is True for v in values) else False if all(v is False for v in values) else None


def _tcp(env):
    robots = getattr(env, "robots", None)
    if not isinstance(robots, (list, tuple)) or len(robots) != 1:
        raise geo.MeasurementError("headless TCP requires exactly one native robot")
    robot, model = robots[0], env.sim.model
    name = robot.gripper.important_sites["grip_site"]
    sid = robot.eef_site_id
    if (isinstance(sid, (bool, np.bool_)) or not isinstance(sid, (int, np.integer)) or sid < 0
            or model.site_name2id(name) != sid or model.site_id2name(int(sid)) != name):
        raise geo.MeasurementError("native TCP/eef site identity mismatch")
    if getattr(robot, "sim", env.sim) is not env.sim:
        raise geo.MeasurementError("native robot refers to a stale simulation")
    return {"site_id": int(sid), "site_name": name, "frame": "world",
            "position": _finite(env.sim.data.site_xpos[int(sid)], (3,), "TCP world position").tolist()}


def _contacts(data, ngeom):
    raw = getattr(data, "_data", data)
    count = geo._count(raw.ncon, "contact count")
    if count > len(raw.contact): raise geo.MeasurementError("invalid native contact count")
    result = []
    for index in range(count):
        contact = raw.contact[index]
        ids = [geo._count(contact.geom1, "contact geometry"), geo._count(contact.geom2, "contact geometry")]
        if max(ids) >= ngeom: raise geo.MeasurementError("invalid contact geometry reference")
        result.append({"geom_ids": ids, "position": _finite(contact.pos, (3,), "contact position").tolist(),
                       "normal": _finite(contact.frame, (9,), "contact frame")[:3].tolist(),
                       "distance": float(_finite(contact.dist, (), "contact distance")),
                       "includemargin": float(_finite(contact.includemargin, (), "contact margin"))})
    return result


def _table_entry(gid, name, position, rotation, kind, size):
    position = _finite(position, (3,), "table geometry position")
    rotation = _finite(rotation, (3, 3), "table geometry rotation")
    size = _finite(size, (3,), "table geometry size")
    if (not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-7)
            or abs(np.linalg.det(rotation) - 1) > 1e-7):
        raise geo.MeasurementError("invalid table geometry rotation")
    item = {"geom_id": gid, "name": name, "position": position.tolist(), "rotation": rotation.tolist(),
            "type": kind, "size": size.tolist(), "top_z": None, "top_lower_bound_m": None,
            "coverage": "unsupported"}
    if kind == 6 and np.any(np.abs(rotation[2]) > 1 - 1e-7):
        interval = geo.project_geometry(6, size, None, position, rotation, conservative=False)
        axis = int(np.argmax(np.abs(rotation[2])))
        terms = np.abs(rotation[2]) * size
        # Lower bound on the *lowest* point of this upward face. Tiny rotation
        # roundoff never raises the severe-drop threshold to the face's maximum.
        low_face = position[2] + terms[axis] - sum(terms[i] for i in range(3) if i != axis)
        eps = np.finfo(np.float64).eps
        padding = (16 * eps / (1 - 16 * eps)) * max(abs(position[2]) + terms.sum(), np.finfo(np.float64).tiny)
        lower = float(np.nextafter(low_face - padding, -np.inf))
        item.update(top_z=float(interval[2, 1]), top_lower_bound_m=lower,
                    coverage="horizontal_box_top")
    return item


def _table_snapshot(env, roles, geometry):
    model, data, arrays = env.sim.model, env.sim.data, geometry["arrays"]
    bid = int(model.body_name2id(roles["table_body"]))
    if bid <= 0 or model.body_id2name(bid) != roles["table_body"] or arrays["body_weldid"][bid] != 0:
        raise geo.MeasurementError("workspace table is not the fixed named world-welded body")
    ids = [i for i in range(model.ngeom) if (arrays["geom_contype"][i] or arrays["geom_conaffinity"][i])
           and geo._descendant(arrays["geom_bodyid"][i], bid, arrays["body_parentid"])]
    if not ids: raise geo.MeasurementError("workspace table collision inventory is empty")
    positions = _finite(data.geom_xpos, (model.ngeom, 3), "geometry world positions")
    rotations = _finite(data.geom_xmat, (model.ngeom, 9), "geometry world rotations").reshape(-1, 3, 3)
    items = []
    for gid in ids:
        items.append(_table_entry(gid, model.geom_id2name(gid), positions[gid], rotations[gid],
                                  arrays["geom_type"][gid], arrays["geom_size"][gid]))
    return {"body_id": bid, "body_name": roles["table_body"], "geometries": items,
            "rule": "initial direct top-face native contact; fixed horizontal collision box support"}


def _initial_support(name, position, table, geometry, contacts, callback, *, support_rule=SUPPORT_RULE):
    """Use contact surfaces, not the object's arbitrary body-frame origin.

    The legacy branch exists solely to validate historical v1 measurements.
    All tolerances, normal direction and unsupported/unknown branches are shared.
    """
    if support_rule not in (LEGACY_SUPPORT_RULE, SUPPORT_RULE):
        raise geo.MeasurementError("unknown table support rule")
    ids = set(geometry["groups"][name])
    tables = {item["geom_id"]: item for item in table["geometries"]}
    matching = [c for c in contacts if (c["geom_ids"][0] in ids and c["geom_ids"][1] in tables)
                or (c["geom_ids"][1] in ids and c["geom_ids"][0] in tables)]
    result = {"eligible": None, "table_height_m": None, "support_geom_ids": [], "contacts": matching,
              "reason": "initial_direct_table_support_unproven"}
    if not matching:
        if callback != "absent": result.update(eligible=None, reason="contact_filter_coverage_unknown")
        return result
    valid, uncertain = [], False
    for contact in matching:
        a, b = contact["geom_ids"]
        tid = a if a in tables else b
        table_geom = tables[tid]
        if table_geom["coverage"] != "horizontal_box_top":
            uncertain = True; continue
        nz = contact["normal"][2] if a == tid else -contact["normal"][2]
        height = table_geom["top_z"]
        # Contact position is the midpoint between surfaces. The contact
        # distance / explicit margin bound plus 1e-7 numerical tolerance is
        # used only to identify that existing horizontal top-face contact.
        tolerance = abs(contact["distance"]) / 2 + abs(contact["includemargin"]) + 1e-7
        origin_pass = support_rule != LEGACY_SUPPORT_RULE or position[2] >= height - tolerance
        if nz > 1 - 1e-5 and abs(contact["position"][2] - height) <= tolerance and origin_pass:
            valid.append((tid, table_geom["top_lower_bound_m"]))
        else:
            uncertain = True
    if valid:
        result.update(eligible=True, table_height_m=min(height for _, height in valid),
                      support_geom_ids=sorted({gid for gid, _ in valid}), reason="initial_direct_top_face_support")
    elif uncertain:
        result.update(eligible=None, reason="initial_table_contact_not_proven_support")
    return result


def _relation_read(inner, name, relation):
    predicate = [relation["operator"], name, relation["reference"]]
    try:
        reference = relation["reference"]
        if reference in getattr(inner, "object_sites_dict", {}):
            site = inner.object_sites_dict[reference]
            operation = "in_box" if relation["operator"] == "in" else "under"
            if not callable(getattr(site, operation, None)):
                return {"predicate": predicate, "value": None, "reason": "unsupported_site_predicate"}
        value = inner._eval_predicate(predicate)
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError("official relation predicate has no boolean value")
        return {"predicate": predicate, "value": bool(value), "reason": "official_predicate"}
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        return {"predicate": predicate, "value": None, "reason": "relation_evidence_unavailable", "error": str(error)}


def _frame_from_records(goals, tcp, records, poses, static):
    roles, geometry = static["role_profile"], static["geometry"]
    geo._poses(poses, geometry)
    objects = {}
    for name, role in roles["roles"].items():
        record = records[name]
        position = record["position"]
        if role["movable"]:
            _finite(position, (3,), "object body world position")
            released, release = geo.release_measurement(name, record["legacy_released"], record["legacy_release_evidence"], geometry, poses)
        else:
            released, release = None, {"method": geo.RELEASE_V2, "reason": "non_movable_role_no_release_requirement"}
        objects[name] = {"role": role["role"], "position": position, "released": released,
                         "release_evidence": release, "raw_evidence": deepcopy(record)}
    objects[static["pose_carrier"]]["geometry_poses"] = deepcopy(poses)
    events, evidence = {kind: {} for kind in EVENTS}, {kind: {} for kind in EVENTS}
    for name in roles["wrong_grasp_objects"]:
        record = records[name]
        initial = static["initial_objects"][name]
        rise = float(record["position"][2] - initial["position"][2])
        dual = record["legacy_release_evidence"].get("dual_pad_grasp")
        if type(dual) is not bool: dual = None
        if dual is False and geometry["filters"]["contact_filter_callback"] != "absent": dual = None
        value = _tri_and(dual, rise >= LIFT_METERS)
        events["wrong_grasp"][name] = value
        evidence["wrong_grasp"][name] = {"method": "dual_pad_and_initial_body_lift-v1", "dual_pad_grasp": dual,
            "initial_position": initial["position"], "position": record["position"], "lift_m": rise,
            "minimum_lift_m": LIFT_METERS, "contact_coverage": geometry["filters"]["contact_filter_callback"]}
    for name in roles["wrong_placement_objects"]:
        checks = []
        for previous, current in zip(static["initial_objects"][name]["relations"], records[name]["relations"]):
            before, now = previous["value"], current["value"]
            fresh = False if before is True or now is False else True if before is False and now is True else None
            checks.append({"predicate": current["predicate"], "initial": before, "current": now,
                           "new_relation": fresh, "released": objects[name]["released"],
                           "candidate": _tri_and(fresh, objects[name]["released"])})
        events["wrong_placement"][name] = _tri_or(check["candidate"] for check in checks)
        evidence["wrong_placement"][name] = {"method": "new_official_task_relation_and_release-v1", "relations": checks,
            "reason": "checked_task_destinations" if checks else "no_task_placement_relations"}
    for name in roles["table_drop_objects"]:
        support = static["initial_objects"][name]["table_support"]
        bounds = geo.object_bounds(geometry, poses, name)
        below = None
        if support["table_height_m"] is not None and bounds["intervals"] is not None:
            below = bounds["intervals"][2][1] < support["table_height_m"] - DROP_METERS
        events["table_drop"][name] = _tri_and(support["eligible"], below)
        evidence["table_drop"][name] = {"method": "whole_collision_group_below_initial_table-v1",
            "initial_support": deepcopy(support), "object_bounds": bounds, "below_table_margin": below,
            "minimum_drop_m": DROP_METERS}
    target_release = [objects[name]["released"] for name in roles["movable_targets"]]
    return {"goals": list(goals), "released": _tri_and(*target_release), "tcp": deepcopy(tcp), "objects": objects,
            "event_candidates": events, "event_evidence": evidence}


def _support_rule(static):
    if not isinstance(static, dict):
        raise geo.MeasurementError("invalid headless measurement schema")
    if static.get("schema_version") == LEGACY_SCHEMA and "support_rule" not in static:
        return LEGACY_SUPPORT_RULE
    if static.get("schema_version") == SCHEMA and static.get("support_rule") == SUPPORT_RULE:
        return SUPPORT_RULE
    raise geo.MeasurementError("invalid headless measurement/support version")


def validate_measurement_static(static, episode=None):
    support_rule = _support_rule(static)
    if static.get("static_sha256") != geo.canonical_hash({k: v for k, v in static.items() if k != "static_sha256"}):
        raise geo.MeasurementError("headless measurement static hash mismatch")
    geometry = geo.validate_measurement_static(static["geometry"])
    role = static["role_profile"]
    try:
        validate_roles(role, geometry)
    except (ValueError, KeyError, TypeError) as error:
        raise geo.MeasurementError(f"invalid headless task role identity: {error}") from error
    key = role["task_key"]
    source_xml = static["source_reset_model_xml_sha256"]
    if source_xml is not None and (not isinstance(source_xml, str) or len(source_xml) != 64
                                   or any(c not in "0123456789abcdef" for c in source_xml)):
        raise geo.MeasurementError("invalid source reset XML digest")
    if episode is not None:
        if task_key(episode) != key or source_xml is None or episode.get("model_xml_sha256") != source_xml:
            raise geo.MeasurementError("headless static/episode task or XML identity mismatch")
        if episode.get("initial_mask") != [True, False]:
            raise geo.MeasurementError("headless source must be mask10")
    names = set(role["roles"])
    if set(static["initial_objects"]) != names or static["pose_carrier"] not in names:
        raise geo.MeasurementError("headless initial object inventory mismatch")
    movable = {name for name, fact in role["roles"].items() if fact["movable"]}
    if set(geometry["owner_roots"]) != movable | {"hand"}:
        raise geo.MeasurementError("headless movable collision inventory mismatch")
    table, arrays = static["table"], geometry["arrays"]
    bid = table["body_id"]
    if (type(bid) is not int or not 0 < bid < geometry["nbody"]
            or table["body_name"] != role["table_body"] or geometry["body_names"][bid] != table["body_name"]
            or arrays["body_weldid"][bid] != 0):
        raise geo.MeasurementError("invalid fixed table identity")
    ids = [i for i in range(geometry["ngeom"]) if (arrays["geom_contype"][i] or arrays["geom_conaffinity"][i])
           and geo._descendant(arrays["geom_bodyid"][i], bid, arrays["body_parentid"])]
    if not ids or [item["geom_id"] for item in table["geometries"]] != ids:
        raise geo.MeasurementError("incomplete table collision inventory")
    for item in table["geometries"]:
        gid = item["geom_id"]
        expected = _table_entry(gid, geometry["geom_names"][gid], item["position"], item["rotation"],
                                arrays["geom_type"][gid], arrays["geom_size"][gid])
        if geo.canonical_hash(item) != geo.canonical_hash(expected):
            raise geo.MeasurementError("table surface evidence differs from geometry")
    contacts = static["initial_contacts"]
    if not isinstance(contacts, list): raise geo.MeasurementError("invalid initial contact inventory")
    for contact in contacts:
        ids = contact["geom_ids"]
        if not isinstance(ids, list) or len(ids) != 2 or any(type(g) is not int or not 0 <= g < geometry["ngeom"] for g in ids):
            raise geo.MeasurementError("invalid initial contact geometry identity")
        _finite(contact["position"], (3,), "initial contact position")
        normal = _finite(contact["normal"], (3,), "initial contact normal")
        if abs(np.linalg.norm(normal) - 1) > 1e-7: raise geo.MeasurementError("invalid initial contact normal")
        _finite(contact["distance"], (), "initial contact distance")
        _finite(contact["includemargin"], (), "initial contact margin")
    for name, info in role["roles"].items():
        if type(info["movable"]) is not bool or info["role"] not in {"target", "container", "support", "fixture", "distractor"}:
            raise geo.MeasurementError("invalid headless role")
        initial = static["initial_objects"][name]
        if info["movable"]: _finite(initial["position"], (3,), "initial object position")
        if name in role["wrong_placement_objects"]:
            expected = [[r["operator"], name, r["reference"]] for r in role["relations"]]
            if [item["predicate"] for item in initial["relations"]] != expected:
                raise geo.MeasurementError("initial relation inventory mismatch")
            if any(item["value"] is not None and type(item["value"]) is not bool for item in initial["relations"]):
                raise geo.MeasurementError("invalid initial relation value")
        if name in role["table_drop_objects"]:
            expected = _initial_support(name, initial["position"], table, geometry, contacts,
                                        geometry["filters"]["contact_filter_callback"], support_rule=support_rule)
            if geo.canonical_hash(initial["table_support"]) != geo.canonical_hash(expected):
                raise geo.MeasurementError("initial table support differs from contact evidence")
    return deepcopy(static)


def corrected_measurement_static(static):
    """Return a separate v2 static projection; never alter the original record.

    Validate the historical version once. Only its support version and the
    support fields derived from saved initial contacts change. No native state,
    additional contact, geometry calibration or execution evidence is created.
    """
    corrected = validate_measurement_static(static)
    if _support_rule(corrected) == SUPPORT_RULE:
        return corrected
    corrected["schema_version"] = SCHEMA
    corrected["support_rule"] = SUPPORT_RULE
    for name in corrected["role_profile"]["table_drop_objects"]:
        initial = corrected["initial_objects"][name]
        initial["table_support"] = _initial_support(name, initial["position"], corrected["table"],
            corrected["geometry"], corrected["initial_contacts"],
            corrected["geometry"]["filters"]["contact_filter_callback"], support_rule=SUPPORT_RULE)
    corrected["static_sha256"] = geo.canonical_hash({k: v for k, v in corrected.items() if k != "static_sha256"})
    return corrected


def recompute_table_drop(facts, corrected_static):
    """Project an already validated historical frame onto corrected support.

    Caller validates original raw/static once through the existing reader, and
    obtains ``corrected_static`` from ``corrected_measurement_static``. Reuse the
    recorded whole-object bounds rather than repeat geometry or release work for
    every frame. The returned copy changes only table-drop candidates/evidence;
    it is derived evidence, not a newly executed or SHA-bound original frame.
    """
    if _support_rule(corrected_static) != SUPPORT_RULE:
        raise geo.MeasurementError("table-drop correction requires v2 support")
    names = corrected_static["role_profile"]["table_drop_objects"]
    if (set(facts["event_candidates"]["table_drop"]) != set(names)
            or set(facts["event_evidence"]["table_drop"]) != set(names)):
        raise geo.MeasurementError("table-drop correction object inventory differs")
    result = deepcopy(facts)
    for name in names:
        old = facts["event_evidence"]["table_drop"][name]
        if (old.get("method") != "whole_collision_group_below_initial_table-v1"
                or old.get("minimum_drop_m") != DROP_METERS):
            raise geo.MeasurementError("unknown original table-drop method/threshold")
        bounds = old["object_bounds"]
        if bounds.get("geom_ids") != corrected_static["geometry"]["groups"][name]:
            raise geo.MeasurementError("table-drop geometry inventory differs")
        if bounds.get("coverage") == "complete":
            intervals = _finite(bounds.get("intervals"), (3, 2), "recorded whole-object bounds")
            if np.any(intervals[:, 0] > intervals[:, 1]):
                raise geo.MeasurementError("invalid recorded whole-object bounds")
        elif bounds.get("coverage") == "unsupported" and bounds.get("intervals") is None:
            intervals = None
        else:
            raise geo.MeasurementError("unknown recorded whole-object bound coverage")
        support = corrected_static["initial_objects"][name]["table_support"]
        below = None
        if support["table_height_m"] is not None and intervals is not None:
            below = bool(intervals[2, 1] < support["table_height_m"] - DROP_METERS)
        result["event_candidates"]["table_drop"][name] = _tri_and(support["eligible"], below)
        result["event_evidence"]["table_drop"][name] = {**deepcopy(old),
            "initial_support": deepcopy(support), "below_table_margin": below}
    return result


def validate_evaluator_evidence(facts, static):
    validate_measurement_static(static)
    try:
        if set(facts) != {"goals", "released", "tcp", "objects", "event_candidates", "event_evidence"}:
            raise geo.MeasurementError("headless evaluator field mismatch")
        if set(facts["objects"]) != set(static["role_profile"]["roles"]):
            raise geo.MeasurementError("headless object inventory changed")
        if not isinstance(facts["goals"], list) or len(facts["goals"]) != 2 or any(type(v) is not bool for v in facts["goals"]):
            raise geo.MeasurementError("invalid official goal values")
        tcp = facts["tcp"]
        if {k: v for k, v in tcp.items() if k != "position"} != static["tcp_identity"]:
            raise geo.MeasurementError("headless TCP site identity changed")
        _finite(tcp["position"], (3,), "TCP position")
        records = {name: obj["raw_evidence"] for name, obj in facts["objects"].items()}
        role = static["role_profile"]
        for name in role["wrong_placement_objects"]:
            rows = records[name]["relations"]
            expected = [[r["operator"], name, r["reference"]] for r in role["relations"]]
            if [item["predicate"] for item in rows] != expected or any(item["value"] is not None and type(item["value"]) is not bool for item in rows):
                raise geo.MeasurementError("per-step official relation evidence malformed")
        poses = facts["objects"][static["pose_carrier"]]["geometry_poses"]
        expected = _frame_from_records(facts["goals"], tcp, records, poses, static)
        if geo.canonical_hash(expected) != geo.canonical_hash(facts):
            raise geo.MeasurementError("headless event/release evidence differs from recomputation")
        return deepcopy(facts)
    except (KeyError, TypeError, AttributeError) as error:
        raise geo.MeasurementError(f"missing headless physical evidence: {error}") from error


class HeadlessMeasurements:
    """Per-reset observer; native source fields are read, never advanced."""
    def __init__(self, env, key, *, source_reset_model_xml_sha256=None):
        self.env, self.inner = env, _task_environment(env)
        self.roles = build_roles(self.inner, env.sim.model, key)
        self.inventory = {**self.inner.objects_dict, **self.inner.fixtures_dict}
        self.gripper = env.robots[0].gripper
        movable = {name: self.inventory[name] for name, role in self.roles["roles"].items() if role["movable"]}
        self.geometry = geo.GeometryObserver(env, movable, self.gripper, contact_filter_getter=_callback_status)
        tcp = _tcp(env)
        table = _table_snapshot(env, self.roles, self.geometry.static)
        contacts = _contacts(env.sim.data, env.sim.model.ngeom)
        initial = self._records()
        for name in self.roles["table_drop_objects"]:
            initial[name]["table_support"] = _initial_support(name, initial[name]["position"], table,
                self.geometry.static, contacts, self.geometry.static["filters"]["contact_filter_callback"])
        self.static = {"schema_version": SCHEMA, "support_rule": SUPPORT_RULE,
                       "role_profile": deepcopy(self.roles), "geometry": self.geometry.static,
                       "source_reset_model_xml_sha256": source_reset_model_xml_sha256,
                       "initial_objects": initial, "initial_contacts": contacts, "table": table, "pose_carrier": sorted(self.inventory)[0],
                       "tcp_identity": {k: v for k, v in tcp.items() if k != "position"},
                       "limitations": ["Official relation values are native observed facts, not a reimplementation of all LIBERO predicates.",
                           "Initial table support requires direct horizontal top-face contact; unproven support remains unknown.",
                           "Only preregistered physical events are observed; no general semantic redundancy/damage classifier."]}
        self.static["static_sha256"] = geo.canonical_hash(self.static)
        validate_measurement_static(self.static)

    def _records(self):
        result = {}
        for name, info in self.roles["roles"].items():
            if info["movable"]:
                obj = self.inventory[name]
                bid = int(self.env.sim.model.body_name2id(obj.root_body))
                if bid != info["body_id"] or self.inner.obj_body_id.get(name) != bid:
                    raise geo.MeasurementError("current native object body reference differs")
                position = _finite(self.env.sim.data.body_xpos[bid], (3,), "object root position").tolist()
                released, release = _release(self.env, self.inner, self.gripper, obj)
            else:
                position, released, release = None, None, {"reason": "not_movable"}
            relations = [_relation_read(self.inner, name, relation) for relation in self.roles["relations"]] if name in self.roles["wrong_placement_objects"] else []
            result[name] = {"position": position, "legacy_released": released, "legacy_release_evidence": release, "relations": relations}
        return result

    def measurement_static(self):
        return deepcopy(self.static)

    def evaluator_state(self, goals):
        poses = self.geometry.pose()
        tcp = _tcp(self.env)
        if {k: v for k, v in tcp.items() if k != "position"} != self.static["tcp_identity"]:
            raise geo.MeasurementError("TCP site changed within episode")
        # The table is a world-welded scene fixture. A changed pose is a model
        # or measurement identity problem, not an inferred dropping event.
        for item in self.static["table"]["geometries"]:
            gid = item["geom_id"]
            if (not np.array_equal(self.env.sim.data.geom_xpos[gid], item["position"])
                    or not np.array_equal(np.asarray(self.env.sim.data.geom_xmat[gid]).reshape(3, 3), item["rotation"])):
                raise geo.MeasurementError("fixed workspace table pose changed")
        return _frame_from_records(goals, tcp, self._records(), poses, self.static)


class HeadlessLiberoEnv(LiberoGoalEnv):
    def __init__(self, config):
        if "hold_action" in config or "hold_contract" in config:
            raise ValueError("headless baseline never uses a scripted hold")
        super().__init__(config)
        self.measurements = None

    def reset(self, episode):
        self.measurements = None
        key = task_key(episode)
        if episode.get("initial_mask") != [True, False]:
            raise ValueError("headless baseline accepts only the fixed mask10 source")
        observation = super().reset(episode)
        try:
            if self.goal_values() != [True, False]:
                raise ValueError("restored official goals differ from source mask10")
            # The existing bridge has already checked this exact reset-model SHA
            # before restoring state. Native post-processing may legitimately change
            # stove indicator site RGBA; retain the post-restore XML independently.
            self.measurements = HeadlessMeasurements(self.env, key,
                source_reset_model_xml_sha256=episode["model_xml_sha256"])
        except BaseException:
            self._ready = False
            raise
        return observation

    def evaluator_state(self):
        if not self._ready or self.measurements is None:
            raise RuntimeError("headless evaluator requires a successful reset")
        return self.measurements.evaluator_state(self.goal_values())

    def measurement_static(self):
        if not self._ready or self.measurements is None:
            raise RuntimeError("headless evaluator requires a successful reset")
        return self.measurements.measurement_static()

    def hold_action(self):
        raise RuntimeError("headless baseline has no hold or automatic gripper action")

    def close(self):
        self.measurements = None
        super().close()


def make_env(config):
    return HeadlessLiberoEnv(config)
