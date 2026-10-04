"""Exact drawer-component construction and drift auditing without simulation."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import build as driver
from benchmark.remaining_goals.construction import drawer_candidates
from benchmark.remaining_goals.task_catalog import TASKS
from benchmark.remaining_goals.validation import validate_candidate


@pytest.fixture
def cabinet(monkeypatch):
    prefix = "white_cabinet_1"
    names = [f"{prefix}_{level}_region" for level in ("top", "middle", "bottom")]
    model = SimpleNamespace(
        nq=12, nv=12, na=0, njnt=12, nbody=6, nsite=3,
        joint_names=[*[f"robot0_joint{i}" for i in range(9)],
                     *[f"{prefix}_{level}_level" for level in ("top", "middle", "bottom")]],
        body_names=["world", "robot0", f"{prefix}_base", f"{prefix}_cabinet_top",
                    f"{prefix}_cabinet_middle", f"{prefix}_cabinet_bottom"],
        jnt_type=np.array([3] * 9 + [2] * 3), jnt_qposadr=np.arange(12), jnt_dofadr=np.arange(12),
        jnt_bodyid=np.array([1] * 9 + [3, 4, 5]), jnt_limited=np.ones(12),
        jnt_range=np.array([[-3., 3.]] * 9 + [[-.16, .01]] * 3),
        jnt_axis=np.tile([0., 1., 0.], (12, 1)),
        body_parentid=np.array([0, 0, 0, 2, 2, 2]),
        site_bodyid=np.array([3, 4, 5]), site_type=np.full(3, 6),
        site_name2id=lambda name: names.index(name) if name in names else -1,
    )
    base = np.zeros(25)
    base[1:10] = np.linspace(.01, .09, 9)
    base[10:13] = [0., -.03, -.15]  # Top not open, untouched middle, bottom open.
    data = SimpleNamespace(qpos=base[1:13].copy(), site_xpos=np.zeros((3, 3)), ncon=0, contact=[])
    sim = SimpleNamespace(model=model, data=data, state=base.copy())
    sim.get_state = lambda: SimpleNamespace(flatten=lambda: sim.state.copy())
    profile = deepcopy(TASKS["cabinet_close_bottom_open_top"])
    ranges = {"default_open_ranges": [-.16, -.14], "default_close_ranges": [0., .005]}
    sites = {name: SimpleNamespace(joints=[model.joint_names[9+i]], parent_name=prefix)
             for i, name in enumerate(names)}

    def predicate(p):
        value = sim.state[10 + names.index(p[1])]
        return bool(value < -.14 if p[0] == "open" else value > 0.)

    inner = SimpleNamespace(object_sites_dict=sites,
                            get_object=lambda name: SimpleNamespace(object_properties={"articulation": ranges}),
                            parsed_problem={"objects": {}}, _eval_predicate=predicate)
    env = SimpleNamespace(sim=sim, env=inner)
    observation = {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8), "proprio": np.zeros(3)}

    def restore(active, state):
        active.sim.state = state.copy()
        active.sim.data.qpos[:] = state[1:13]
        active.sim.data.site_xpos[:, 1] = state[10:13]
        return observation

    monkeypatch.setattr(driver, "restore_raw_state", restore)
    monkeypatch.setattr(driver, "fresh_observation", lambda active: observation)
    restore(env, base)
    return env, base, profile, ranges, restore, observation


def test_drawer_candidates_use_predicate_interior_and_only_the_named_joint(cabinet):
    env, base, profile, _, _, _ = cabinet
    lists = driver._per_goal(env, base, profile, max_candidates=4)
    assert [len(items) for items in lists] == [4, 4]
    for index, items in enumerate(lists):
        slots = [12, 24] if index == 0 else [10, 22]
        for candidate in items:
            assert candidate["allowed_indices"] == slots
            assert candidate["diagnostics"]["compiled_site_joint_ancestry_verified"]
            remaining = sorted(set(range(len(base))) - set(slots))
            np.testing.assert_array_equal(candidate["state"][remaining], base[remaining])
            value = candidate["state"][slots[0]]
            assert 0. < value < .005 if index == 0 else -.16 < value < -.14
    assert lists[0][0]["state"][12] == pytest.approx(.0025)
    assert lists[1][0]["state"][10] == pytest.approx(-.15)
    np.testing.assert_array_equal(env.sim.state, base)


def test_driver_evaluates_official_predicate_before_returning_drawer_candidate(cabinet):
    env, base, profile, _, _, _ = cabinet
    env.env._eval_predicate = lambda p: False
    assert driver._per_goal(env, base, profile, max_candidates=4) == [[], []]


@pytest.mark.parametrize("broken", ["joint", "multiple_joints", "fixture", "predicate_interval"])
def test_official_region_mapping_and_predicate_interval_fail_closed(cabinet, broken):
    env, base, profile, ranges, _, _ = cabinet
    site = env.env.object_sites_dict["white_cabinet_1_bottom_region"]
    if broken == "joint":
        site.joints = ["white_cabinet_1_top_level"]
    elif broken == "multiple_joints":
        site.joints.append("white_cabinet_1_top_level")
    elif broken == "fixture":
        site.parent_name = "other_cabinet"
    else:
        ranges["default_close_ranges"] = [-.01, .01]
    with pytest.raises(ValueError, match="differs from"):
        driver._per_goal(env, base, profile, max_candidates=4)


@pytest.mark.parametrize("field,index,value", [
    ("site_bodyid", 2, 3), ("jnt_bodyid", 11, 3), ("body_parentid", 5, 3),
    ("jnt_type", 11, 3), ("jnt_range", (11, 0), -.2), ("jnt_axis", (11, 0), 1.),
    ("jnt_bodyid", 10, 5), ("jnt_bodyid", 0, 2),
])
def test_compiled_drawer_identity_and_fixed_ancestry_are_mandatory(cabinet, field, index, value):
    env, base, profile, _, _, _ = cabinet
    contract = profile["joint_contracts"]["white_cabinet_1_bottom_region"]
    getattr(env.sim.model, field)[index] = value
    with pytest.raises(ValueError):
        drawer_candidates(base, env.sim.model, "white_cabinet_1_bottom_region", contract,
                           predicate_range=[0., .005], predicate_range_source="official fixture")


def test_goal_articulation_site_drift_rejects_motion_even_while_predicate_stays_true(cabinet, monkeypatch):
    env, base, profile, _, restore, observation = cabinet
    candidate = base.copy()
    candidate[10], candidate[12] = -.15, .0025  # Both goals true.
    wrapper = driver.CandidateAuditEnv(env, candidate, profile["goals"])

    def step(active, action):
        # Slow position change with zero qvel in this fake isolates the new
        # site-position check from the existing instantaneous velocity limit.
        moved = active.sim.state.copy()
        moved[12] += .006
        return restore(active, moved)

    monkeypatch.setattr(driver, "_step", step)
    report = validate_candidate(wrapper, {"episode_id": "drawers", "initial_mask": [True, True],
                                          "reference_robot_qpos": base[1:10].tolist()},
                                steps=1, hold_action=np.zeros(7))
    assert report["static_acceptance"] is True
    assert report["technical_acceptance"] is False
    assert report["checks"]["predicate_mask_matches"] is True
    assert report["checks"]["velocities_below_limit"] is True
    assert report["checks"]["object_positions_stable"] is False
    assert report["trace"][1]["object_position_drift"]["site:white_cabinet_1_bottom_region"] == pytest.approx(.006)


def test_missing_goal_site_is_not_silently_omitted_from_auditing(cabinet):
    env, base, profile, _, _, _ = cabinet
    env.sim.model.site_name2id = lambda name: -1
    with pytest.raises(ValueError, match="required articulated goal region site"):
        driver.CandidateAuditEnv(env, base, profile["goals"])
