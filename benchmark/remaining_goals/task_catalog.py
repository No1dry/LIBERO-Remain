"""Curated independent final-goal tasks from pinned official LIBERO BDDL.

Selection is a construction hypothesis, not a legality or reachability verdict.
Every source must pass all 2**K matched-state audits and later semantic review.
Object/support relationships stay exactly as written in the official goals.
"""

from numbers import Integral

PRIMARY_SUITE = "libero_10"


def _goal(identifier, language, *predicate):
    return {"id": identifier, "language": language, "predicates": [list(predicate)]}


def _drawer_contract(cabinet, level):
    """Pinned cabinet XML topology and ArticulatedObject predicate intervals."""
    return {"fixture": cabinet, "joint": f"{cabinet}_{level}_level",
            "site_body": f"{cabinet}_cabinet_{level}", "parent_body": f"{cabinet}_base",
            "joint_range": [-0.16, 0.01], "joint_axis": [0., 1., 0.],
            "predicate_ranges": {"open": [-0.16, -0.14], "close": [0., 0.005]}}


TASKS = {
    "basket": {
        "suite": "libero_10",
        "name": "LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket",
        "selection_reason": "Two separate movable objects share an unchanged basket; fixed reserved slots across masks.",
        "goals": [
            _goal("soup_in_basket", "put the alphabet soup in the basket", "in", "alphabet_soup_1", "basket_1_contain_region"),
            _goal("sauce_in_basket", "put the tomato sauce in the basket", "in", "tomato_sauce_1", "basket_1_contain_region"),
        ],
    },
    "stove": {
        "suite": "libero_10",
        "name": "KITCHEN_SCENE3_turn_on_the_stove_and_put_the_moka_pot_on_it",
        "selection_reason": "Stove articulation and separate pot pose have disjoint editable state components.",
        "goals": [
            _goal("stove_on", "turn on the stove", "turnon", "flat_stove_1"),
            _goal("pot_on_stove", "put the moka pot on the stove", "on", "moka_pot_1", "flat_stove_1_cook_region"),
        ],
    },
    "basket_cheese_butter": {
        "suite": "libero_10",
        "name": "LIVING_ROOM_SCENE2_put_both_the_cream_cheese_box_and_the_butter_in_the_basket",
        "selection_reason": "A second shared-container pair changes object shape and contact geometry, not only language.",
        "goals": [
            _goal("cheese_in_basket", "put the cream cheese box in the basket", "in", "cream_cheese_1", "basket_1_contain_region"),
            _goal("butter_in_basket", "put the butter in the basket", "in", "butter_1", "basket_1_contain_region"),
        ],
    },
    "basket_soup_cheese": {
        "suite": "libero_10",
        "name": "LIVING_ROOM_SCENE1_put_both_the_alphabet_soup_and_the_cream_cheese_box_in_the_basket",
        "selection_reason": "Completes the main-suite shared-basket object/scene coverage; this is another configuration of the same task family.",
        "goals": [
            _goal("soup_in_basket", "put the alphabet soup in the basket", "in", "alphabet_soup_1", "basket_1_contain_region"),
            _goal("cheese_in_basket", "put the cream cheese box in the basket", "in", "cream_cheese_1", "basket_1_contain_region"),
        ],
    },
    "dual_mugs": {
        "suite": "libero_10",
        "name": "LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate_and_put_the_yellow_and_white_mug_on_the_right_plate",
        "object_supports": ["plate_1", "plate_2"],
        "selection_reason": "Two mugs go to distinct unchanged supports; tests spatial routing as well as retention.",
        "goals": [
            _goal("white_mug_on_left_plate", "put the white mug on the left plate", "on", "porcelain_mug_1", "plate_1"),
            _goal("yellow_mug_on_right_plate", "put the yellow and white mug on the right plate", "on", "white_yellow_mug_1", "plate_2"),
        ],
    },
    "mug_pudding": {
        "suite": "libero_10",
        "name": "LIVING_ROOM_SCENE6_put_the_white_mug_on_the_plate_and_put_the_chocolate_pudding_to_the_right_of_the_plate",
        "object_supports": ["plate_1"],
        "selection_reason": "Combines object-on-object placement and a distinct named tabletop region, without moving the plate.",
        "goals": [
            _goal("mug_on_plate", "put the white mug on the plate", "on", "porcelain_mug_1", "plate_1"),
            _goal("pudding_right_of_plate", "put the chocolate pudding to the right of the plate", "on", "chocolate_pudding_1", "living_room_table_plate_right_region"),
        ],
    },
    "two_pots": {
        "suite": "libero_10",
        "name": "KITCHEN_SCENE8_put_both_moka_pots_on_the_stove",
        "requires_invariant_protocol": True,
        "invariant_predicates": [["turnon", "flat_stove_1"]],
        "selection_reason": "Official BDDL init and goal both require Turnon: stove power is an initially satisfied constraint to retain, not a third pending goal. Excluded from the all-false matched protocol until invariants are explicitly supported; official goals remain unchanged.",
        "goals": [
            _goal("first_pot_on_stove", "put the first moka pot on the stove", "on", "moka_pot_1", "flat_stove_1_cook_region"),
            _goal("second_pot_on_stove", "put the second moka pot on the stove", "on", "moka_pot_2", "flat_stove_1_cook_region"),
            _goal("stove_on", "turn on the stove", "turnon", "flat_stove_1"),
        ],
    },
    "frypan_stove3": {
        "suite": "libero_90",
        "name": "KITCHEN_SCENE3_turn_on_the_stove_and_put_the_frying_pan_on_it",
        "selection_reason": "Joint-plus-placement task with a large handled object; contact is audited rather than requiring its handle to fit the burner region.",
        "goals": [
            _goal("stove_on", "turn on the stove", "turnon", "flat_stove_1"),
            _goal("pan_on_stove", "put the frying pan on the stove", "on", "chefmate_8_frypan_1", "flat_stove_1_cook_region"),
        ],
    },
    "frypan_stove9": {
        "suite": "libero_90",
        "name": "KITCHEN_SCENE9_turn_on_the_stove_and_put_the_frying_pan_on_it",
        "selection_reason": "Replicates the pan/stove predicates in another canonical scene with a shelf and different distractors; not a new semantic task family.",
        "goals": [
            _goal("stove_on", "turn on the stove", "turnon", "flat_stove_1"),
            _goal("pan_on_stove", "put the frying pan on the stove", "on", "chefmate_8_frypan_1", "flat_stove_1_cook_region"),
        ],
    },
    "cabinet_close_top_bowl": {
        "suite": "libero_90",
        "name": "KITCHEN_SCENE10_close_the_top_drawer_of_the_cabinet_and_put_the_black_bowl_on_top_of_it",
        "selection_reason": "The top drawer starts open; closing its slide is independent of placing a bowl on the fixed cabinet shell's top_side. The target surface does not move with the drawer.",
        "joint_contracts": {"wooden_cabinet_1_top_region": _drawer_contract("wooden_cabinet_1", "top")},
        "goals": [
            _goal("top_drawer_closed", "close the top drawer of the cabinet", "close", "wooden_cabinet_1_top_region"),
            _goal("bowl_on_cabinet", "put the black bowl on top of the cabinet", "on", "akita_black_bowl_1", "wooden_cabinet_1_top_side"),
        ],
    },
    "cabinet_close_bottom_open_top": {
        "suite": "libero_90",
        "name": "KITCHEN_SCENE4_close_the_bottom_drawer_of_the_cabinet_and_open_the_top_drawer",
        "selection_reason": "Bottom and top drawers are sibling slide bodies with disjoint state components; the bottom starts open and the top is not open. No object is placed inside either drawer.",
        "joint_contracts": {
            "white_cabinet_1_bottom_region": _drawer_contract("white_cabinet_1", "bottom"),
            "white_cabinet_1_top_region": _drawer_contract("white_cabinet_1", "top"),
        },
        "goals": [
            _goal("bottom_drawer_closed", "close the bottom drawer of the cabinet", "close", "white_cabinet_1_bottom_region"),
            _goal("top_drawer_open", "open the top drawer of the cabinet", "open", "white_cabinet_1_top_region"),
        ],
    },
}

TASK_TRACKS = {
    "primary": {"suite": "libero_10", "tasks": ["basket", "stove", "basket_cheese_butter",
                                                  "basket_soup_cheese", "dual_mugs", "mug_pudding"]},
    "extension": {"suite": "libero_90", "tasks": ["frypan_stove3", "frypan_stove9",
                                                    "cabinet_close_top_bowl", "cabinet_close_bottom_open_top"]},
}
# A ten-task catalog, deliberately requiring two suite-specific manifests.
COMMON_TEN_TASKS = tuple(TASK_TRACKS["primary"]["tasks"] + TASK_TRACKS["extension"]["tasks"])

EXCLUDED_FAMILIES = {
    "put_in_and_close_drawer_or_microwave": "Closing changes access to the remaining placement; independent components do not imply independent execution.",
    "open_drawer_and_put_in": "Container articulation moves the target support and gates access to it.",
    "stack_bowls_and_move_stack_to_tray": "One goal moves the support of the other; transplanting independent poses breaks the stack.",
    "single_final_predicate": "No nontrivial partially completed final-goal subset exists.",
}


def mask_order(n_goals):
    """First goal is the least significant bit: preserve 00,10,01,11 order."""
    if isinstance(n_goals, bool) or not isinstance(n_goals, Integral) or n_goals not in (2, 3):
        raise ValueError("matched groups require two or three goals")
    return tuple("".join(str((value >> index) & 1) for index in range(n_goals))
                 for value in range(1 << n_goals))


def select_tasks(selection="all"):
    """Default to the primary checkpoint suite; extensions require explicit keys.

    A build produces a single-suite manifest for the formal evaluator. Separate
    calls must be used for libero_90 extension tasks; do not pool their scores
    with checkpoints trained for the primary libero_10 suite.
    """
    if selection == "all":
        keys = list(TASK_TRACKS["primary"]["tasks"])
    elif isinstance(selection, str) and selection in TASK_TRACKS:
        keys = list(TASK_TRACKS[selection]["tasks"])
    else:
        keys = selection.split(",") if isinstance(selection, str) else list(selection)
    if not keys or len(keys) != len(set(keys)) or any(key not in TASKS for key in keys):
        raise ValueError(f"tasks must be distinct catalog keys or 'all': {', '.join(TASKS)}")
    if len({TASKS[key]["suite"] for key in keys}) != 1:
        raise ValueError("mixed-suite construction is not supported; build each suite in a separate output directory")
    if any(TASKS[key].get("requires_invariant_protocol", False) for key in keys):
        raise ValueError("selected task requires invariant protocol; the all-false matched builder cannot construct it")
    return keys
