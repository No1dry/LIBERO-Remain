"""Explicit ten-task roles, checked against official predicates and site owners."""
from copy import deepcopy
from ..task_catalog import TASKS, COMMON_TEN_TASKS
from ..libero_env import _predicate

SCHEMA = "remaining-headless-roles-v1"
PROFILES = {
    "basket": {"basket_1_contain_region": "basket_1"},
    "basket_cheese_butter": {"basket_1_contain_region": "basket_1"},
    "basket_soup_cheese": {"basket_1_contain_region": "basket_1"},
    "stove": {"flat_stove_1_cook_region": "flat_stove_1"},
    "frypan_stove3": {"flat_stove_1_cook_region": "flat_stove_1"},
    "frypan_stove9": {"flat_stove_1_cook_region": "flat_stove_1"},
    "dual_mugs": {"plate_1": "plate_1", "plate_2": "plate_2"},
    "mug_pudding": {"plate_1": "plate_1", "living_room_table_plate_right_region": "living_room_table"},
    "cabinet_close_top_bowl": {"wooden_cabinet_1_top_region": "wooden_cabinet_1", "wooden_cabinet_1_top_side": "wooden_cabinet_1"},
    "cabinet_close_bottom_open_top": {"white_cabinet_1_bottom_region": "white_cabinet_1", "white_cabinet_1_top_region": "white_cabinet_1"},
}


def task_key(episode):
    matches = [key for key in COMMON_TEN_TASKS if TASKS[key]["suite"] == episode.get("suite")
               and TASKS[key]["name"] == episode.get("task_name")]
    if len(matches) != 1:
        raise ValueError("headless protocol requires one fixed ten-task catalog identity")
    return matches[0]


def _owner(inner, reference, expected, inventory, workspace):
    if reference in inventory:
        actual = reference
    else:
        site = getattr(inner, "object_sites_dict", {}).get(reference)
        if site is None:
            raise ValueError(f"task region is absent: {reference}")
        candidates = []
        parent = getattr(site, "parent_name", None)
        if parent is not None:
            candidates.append(parent)
        region = inner.parsed_problem.get("regions", {}).get(reference)
        if isinstance(region, dict) and region.get("target") is not None:
            candidates.append(region["target"])
        if not candidates or any(value != candidates[0] for value in candidates):
            raise ValueError(f"ambiguous official task region owner: {reference}")
        actual = candidates[0]
    if actual != expected or (actual not in inventory and actual != workspace):
        raise ValueError(f"task region owner mismatch: {reference}")
    return actual


def build_roles(inner, model, key):
    if key not in COMMON_TEN_TASKS:
        raise ValueError("unsupported headless task")
    profile = TASKS[key]
    predicates = [list(_predicate(p)) for goal in profile["goals"] for p in goal["predicates"]]
    if sorted(tuple(p) for p in predicates) != sorted(_predicate(p) for p in inner.parsed_problem["goal_state"]):
        raise ValueError("headless role catalog differs from official final predicates")
    objects, fixtures = inner.objects_dict, inner.fixtures_dict
    if not isinstance(objects, dict) or not isinstance(fixtures, dict) or set(objects) & set(fixtures):
        raise ValueError("ambiguous physical object/fixture inventory")
    inventory = {**objects, **fixtures}
    living = profile["name"].startswith("LIVING_ROOM_")
    workspace, table_body = ("living_room_table", "living_room_table") if living else ("kitchen_table", "table")
    if getattr(inner, "workspace_name", None) != workspace:
        raise ValueError("headless task workspace identity mismatch")
    free = {}
    body_ids = {}
    for name, obj in inventory.items():
        bid = int(model.body_name2id(obj.root_body))
        if bid < 0 or model.body_id2name(bid) != obj.root_body:
            raise ValueError("object root-body identity mismatch")
        body_ids[name] = bid
        joints = list(getattr(obj, "joints", None) or [])
        types = [int(model.jnt_type[int(model.joint_name2id(joint))]) for joint in joints]
        free[name] = 0 in types
        if free[name] and (types != [0] or name in fixtures):
            raise ValueError("unsupported movable object joint/fixture contract")
    targets, related, containers, relations = set(), set(), set(), []
    for predicate in predicates:
        op = predicate[0]
        if op in {"in", "on"}:
            name, reference = predicate[1:]
            if name not in objects or not free[name]:
                raise ValueError("placement target is not a movable physical object")
            targets.add(name)
            owner = _owner(inner, reference, PROFILES[key][reference], inventory, workspace)
            related.add(owner)
            if op == "in": containers.add(owner)
            relation = {"operator": op, "reference": reference, "owner": owner}
            if relation not in relations: relations.append(relation)
        elif op in {"open", "close", "turnon"}:
            reference = predicate[1]
            expected = PROFILES[key].get(reference, reference)
            related.add(_owner(inner, reference, expected, inventory, workspace))
        else:
            raise ValueError("unsupported headless task predicate")
    roles = {}
    for name in inventory:
        role = ("target" if name in targets else "container" if name in containers else
                "support" if name in related else "fixture" if not free[name] else "distractor")
        roles[name] = {"role": role, "movable": free[name], "body_id": body_ids[name], "root_body": inventory[name].root_body}
    return {"schema_version": SCHEMA, "task_key": key, "suite": profile["suite"], "task_name": profile["name"],
            "goal_specs": deepcopy(profile["goals"]), "roles": roles, "movable_targets": sorted(targets),
            "relations": relations, "workspace": workspace, "table_body": table_body,
            "wrong_grasp_objects": sorted(name for name, role in roles.items() if role["role"] == "distractor"),
            "wrong_placement_objects": sorted(name for name, role in roles.items() if role["role"] == "distractor"),
            "table_drop_objects": sorted(name for name, role in roles.items() if role["movable"] and role["role"] != "target")}


def validate_roles(value, geometry):
    """Re-derive catalog roles and event sets without importing a native env."""
    key = value["task_key"]
    if key not in COMMON_TEN_TASKS or value["schema_version"] != SCHEMA:
        raise ValueError("unsupported headless role identity")
    profile = TASKS[key]
    if (value["suite"] != profile["suite"] or value["task_name"] != profile["name"]
            or value["goal_specs"] != profile["goals"]):
        raise ValueError("headless role catalog identity differs")
    living = profile["name"].startswith("LIVING_ROOM_")
    workspace, table = ("living_room_table", "living_room_table") if living else ("kitchen_table", "table")
    if value["workspace"] != workspace or value["table_body"] != table:
        raise ValueError("headless workspace identity differs")
    targets, related, containers, relations = set(), set(), set(), []
    for goal in profile["goals"]:
        for raw in goal["predicates"]:
            predicate = _predicate(raw)
            op = predicate[0]
            reference = predicate[-1]
            owner = PROFILES[key].get(reference, reference)
            related.add(owner)
            if op in {"in", "on"}:
                targets.add(predicate[1])
                if op == "in": containers.add(owner)
                relation = {"operator": op, "reference": reference, "owner": owner}
                if relation not in relations: relations.append(relation)
    roles = value["roles"]
    if not isinstance(roles, dict) or not roles or not targets <= set(roles) or not related <= set(roles) | {workspace}:
        raise ValueError("task-related physical object is missing")
    bodies = set()
    for name, info in roles.items():
        if not isinstance(name, str) or not name or type(info["movable"]) is not bool:
            raise ValueError("invalid physical role identity")
        bid = info["body_id"]
        if type(bid) is not int or not 0 < bid < geometry["nbody"] or bid in bodies:
            raise ValueError("invalid/duplicate physical role body")
        bodies.add(bid)
        if geometry["body_names"][bid] != info["root_body"]:
            raise ValueError("role root body differs from compiled model")
        expected = ("target" if name in targets else "container" if name in containers else
                    "support" if name in related else "fixture" if not info["movable"] else "distractor")
        if info["role"] != expected or (name in targets and not info["movable"]):
            raise ValueError("physical role differs from official goal semantics")
        if info["movable"] and geometry["owner_roots"].get(name) != bid:
            raise ValueError("movable role differs from collision owner")
    distractors = sorted(n for n, r in roles.items() if r["role"] == "distractor")
    drops = sorted(n for n, r in roles.items() if r["movable"] and r["role"] != "target")
    if (value["movable_targets"] != sorted(targets) or value["relations"] != relations
            or value["wrong_grasp_objects"] != distractors or value["wrong_placement_objects"] != distractors
            or value["table_drop_objects"] != drops):
        raise ValueError("headless event/target inventory differs from roles")
    return deepcopy(value)
