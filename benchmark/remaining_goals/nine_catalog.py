"""Explicit Task033 active-goal semantics; legacy catalogs remain immutable.

Pure helpers only: importing this module never imports or creates LIBERO.
"""
from copy import deepcopy

from .task_catalog import TASKS, _goal

SEMANTICS_VERSION = "remaining-nine-task-semantics-v1"
NINE_TASKS = ("basket", "basket_cheese_butter", "stove", "bowl_drawer_close",
              "dual_mugs", "mug_pudding", "basket_soup_cheese", "two_pots", "mug_microwave_close")
NEW_TASKS = ("bowl_drawer_close", "two_pots", "mug_microwave_close")
REUSE_TASKS = tuple(key for key in NINE_TASKS if key not in NEW_TASKS)
NINE_PROTOCOLS = ("nine-normal00", "nine-mask10")
FACT_FIELDS = ("goals", "invariant_values", "official_goal_values", "official_success", "required_open_values")

_PROFILES = {key: deepcopy(TASKS[key]) for key in NINE_TASKS if key in TASKS}
_PROFILES["bowl_drawer_close"] = {
    "suite": "libero_10",
    "name": "KITCHEN_SCENE4_put_the_black_bowl_in_the_bottom_drawer_of_the_cabinet_and_close_it",
    "goals": [_goal("bowl_in_bottom_drawer", "put the black bowl in the bottom drawer", "in", "akita_black_bowl_1", "white_cabinet_1_bottom_region"),
              _goal("bottom_drawer_closed", "close the bottom drawer", "close", "white_cabinet_1_bottom_region")],
    "required_open_predicates": [["open", "white_cabinet_1_bottom_region"]],
}
_PROFILES["mug_microwave_close"] = {
    "suite": "libero_10",
    "name": "KITCHEN_SCENE6_put_the_yellow_and_white_mug_in_the_microwave_and_close_it",
    "goals": [_goal("mug_in_microwave", "put the yellow and white mug in the microwave", "in", "white_yellow_mug_1", "microwave_1_heating_region"),
              _goal("microwave_closed", "close the microwave", "close", "microwave_1")],
    "required_open_predicates": [["open", "microwave_1"]],
}
_PROFILES["two_pots"]["goals"] = _PROFILES["two_pots"]["goals"][:2]
_PROFILES["two_pots"].pop("requires_invariant_protocol", None)
_PROFILES["two_pots"]["selection_reason"] = "Two active pot placements retain the official initially satisfied Turnon invariant."
_PROFILES["two_pots"]["reservation_objects"] = {"flat_stove_1_cook_region": ["moka_pot_1", "moka_pot_2"]}
for _key, _id in zip(NINE_TASKS, (0, 1, 2, 3, 4, 6, 7, 8, 9)):
    _profile = _PROFILES[_key]
    _profile["official_task_id"] = _id
    _profile.setdefault("invariant_predicates", [])
    _profile.setdefault("required_open_predicates", [])
    _profile["official_goal_predicates"] = [deepcopy(p) for g in _profile["goals"] for p in g["predicates"]] + deepcopy(_profile["invariant_predicates"])


def get_task(key):
    if key not in _PROFILES:
        raise ValueError("nine-task protocol requires an exact LIBERO-10 compound task key")
    return deepcopy(_PROFILES[key])


def _predicates(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("official predicates must be a list")
    result = []
    for p in value:
        if (not isinstance(p, (list, tuple)) or len(p) not in (2, 3)
                or any(not isinstance(t, str) or not t or any(c.isspace() or c in "()" for c in t) for t in p)):
            raise ValueError("invalid official atomic predicate")
        result.append([p[0].lower(), *p[1:]])
    return result


def make_task_semantics(key, official_predicates=None):
    profile = get_task(key)
    official = _predicates(profile["official_goal_predicates"] if official_predicates is None else official_predicates)
    if (len({tuple(p) for p in official}) != len(official)
            or sorted(official) != sorted(profile["official_goal_predicates"])):
        raise ValueError("active goals and invariants must partition the complete official goal")
    return {"schema_version": SEMANTICS_VERSION, "task_key": key,
            "official_goal_predicates": official,
            "active_goal_indices": [[official.index(p) for p in goal["predicates"]] for goal in profile["goals"]],
            "invariant_indices": [official.index(p) for p in profile["invariant_predicates"]],
            "required_open_predicates": deepcopy(profile["required_open_predicates"])}


def episode_fields(task, official_predicates=None):
    return {"goal_specs": get_task(task)["goals"], "task_semantics": make_task_semantics(task, official_predicates)}


def validate_task_semantics(value, *, key=None, official_predicates=None):
    if not isinstance(value, dict):
        raise ValueError("explicit nine-task semantics are required")
    actual_key = value.get("task_key")
    if key is not None and key != actual_key:
        raise ValueError("task semantics key differs")
    expected = make_task_semantics(actual_key, value.get("official_goal_predicates"))
    if value != expected or any(type(i) is not int for g in value["active_goal_indices"] for i in g) or any(type(i) is not int for i in value["invariant_indices"]):
        raise ValueError("nine-task official/active/invariant mapping differs")
    if official_predicates is not None and sorted(_predicates(official_predicates)) != sorted(expected["official_goal_predicates"]):
        raise ValueError("installed official predicates differ from nine-task semantics")
    return deepcopy(expected)


def validate_episode_semantics(episode):
    semantics = validate_task_semantics(episode.get("task_semantics"), key=episode.get("task_id"))
    profile = get_task(semantics["task_key"])
    if (episode.get("suite") != "libero_10" or episode.get("task_name") != profile["name"]
            or type(episode.get("libero_task_id")) is not int or episode["libero_task_id"] != profile["official_task_id"]
            or episode.get("goal_specs") != profile["goals"]):
        raise ValueError("nine-task suite/name/id/active-goal identity differs")
    return semantics


def validate_goal_facts(facts, semantics):
    semantics = validate_task_semantics(semantics)
    if not isinstance(facts, dict):
        raise ValueError("nine-task goal facts must be an object")
    sizes = {"goals": 2, "official_goal_values": len(semantics["official_goal_predicates"]),
             "invariant_values": len(semantics["invariant_indices"]),
             "required_open_values": len(semantics["required_open_predicates"])}
    for field, size in sizes.items():
        values = facts.get(field)
        if not isinstance(values, list) or len(values) != size or any(type(v) is not bool for v in values):
            raise ValueError(f"invalid nine-task {field}")
    full = facts["official_goal_values"]
    if (facts["goals"] != [all(full[i] for i in group) for group in semantics["active_goal_indices"]]
            or facts["invariant_values"] != [full[i] for i in semantics["invariant_indices"]]):
        raise ValueError("active/invariant values differ from complete official predicates")
    if type(facts.get("official_success")) is not bool or facts["official_success"] != all(full):
        raise ValueError("native success disagrees with complete official predicates")
    return deepcopy(facts)


def read_goal_facts(evaluate_predicate, native_success, semantics):
    semantics = validate_task_semantics(semantics)
    if not isinstance(native_success, bool) and type(native_success).__name__ != "bool_":
        raise ValueError("native success returned a non-boolean value")
    def read(p):
        value = evaluate_predicate(list(p))
        # Native LIBERO may return numpy.bool_; refuse unknown/non-boolean scalars.
        if not isinstance(value, bool) and type(value).__name__ != "bool_":
            raise ValueError("native predicate returned a non-boolean value")
        return bool(value)
    full = [read(p) for p in semantics["official_goal_predicates"]]
    facts = {"goals": [all(full[i] for i in g) for g in semantics["active_goal_indices"]],
             "invariant_values": [full[i] for i in semantics["invariant_indices"]],
             "official_goal_values": full, "official_success": bool(native_success),
             "required_open_values": [read(p) for p in semantics["required_open_predicates"]]}
    return validate_goal_facts(facts, semantics)


def initial_constraints_match(facts):
    return all(facts["invariant_values"]) and all(facts["required_open_values"])
