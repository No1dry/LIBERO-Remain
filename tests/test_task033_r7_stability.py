"""R7 raw-evidence acceptance with CPU-only compiled-model doubles."""
from copy import deepcopy
import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.validation import validate_candidate, V6_PROFILE
from benchmark.remaining_goals.nine_catalog import episode_fields, get_task

PROFILE = "active-free-object-pose-stability-v7"


class FakeModel:
    nq, nv, na, njnt = 17, 16, 0, 11
    joint_names = [f"robot_joint{i}" for i in range(9)] + ["white_yellow_mug_1_joint0", "microwave_door"]
    jnt_type = np.array([3] * 9 + [0, 3])
    jnt_qposadr = np.array(list(range(10)) + [16])
    jnt_dofadr = np.array(list(range(10)) + [15])


def helper():
    try:
        return importlib.import_module("benchmark.remaining_goals.stability")
    except ImportError:
        pytest.fail("R7 stability helper is not implemented")


def episode():
    profile = get_task("mug_microwave_close")
    return {"episode_id": "r7_fake", "task_id": "mug_microwave_close", "suite": "libero_10",
            "libero_task_id": 9, "task_name": profile["name"],
            **episode_fields("mug_microwave_close"), "initial_mask": [True, False],
            "initial_state_index": 0, "model_xml_sha256": "a" * 64,
            "reference_robot_qpos": [0.] * 9, "construction": {"protocol": "nine-mask10"},
            "observation_profile": V6_PROFILE, "stability_profile": PROFILE,
            "stability_binding": helper().binding_from_model(FakeModel(), "a" * 64)}


def snapshots(count=151):
    binding = helper().binding_from_model(FakeModel(), "a" * 64)
    rows = []
    for i in range(count):
        state = np.zeros(34)
        state[0], state[10:13], state[13] = i * .05, [0., 0., .8], (-1. if i % 2 else 1.)
        state[27:33] = .1  # Actual six A generalized velocities, retained.
        obs = {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8), "robot": np.zeros(9)}
        rows.append({"state": state, "state_before_refresh": state.copy(), "qvel": state[18:].copy(),
                     "robot_qpos": np.zeros(9), "object_positions": {"white_yellow_mug_1": state[10:13].copy()},
                     "penetrations": [], "goals": [True, False], "invariant_values": [],
                     "official_goal_values": [True, False], "official_success": False,
                     "required_open_values": [True], "fresh_observation": obs,
                     "stability_binding": deepcopy(binding)})
    return rows


class FakeEnv:
    def __init__(self, rows):
        self.rows, self.index = rows, 0

    def restore_candidate(self, episode):
        self.index = 0
        return deepcopy(self.rows[0]["fresh_observation"])

    def step(self, action):
        self.index += 1
        return deepcopy(self.rows[self.index]["fresh_observation"])

    def validation_snapshot(self):
        return deepcopy(self.rows[self.index])


def run(rows=None, **options):
    return validate_candidate(FakeEnv(snapshots() if rows is None else rows), episode(),
                              hold_action=[0.] * 6 + [-1.], observation_profile=V6_PROFILE,
                              stability_profile=PROFILE, **options)


def test_sign_equivalent_quaternion_and_high_a_velocity_admit_complete_raw_window():
    result = run()
    assert result["technical_acceptance"] is True
    assert result["schema_version"] == "remaining-goals-validation-v2-active-pose"
    assert len(result["trace"]) == 151
    assert result["stability_window"]["position_span_m"] == 0.
    assert result["stability_window"]["orientation_span_deg"] == 0.
    assert result["stability_window"]["active_velocity_exceedance_fraction"] == 1.
    assert result["stability_window"]["peak_abs_active_velocity"] == .1
    assert result["trace"][1]["state"][13] == -1.
    assert result["trace"][1]["qvel"][9:15] == [.1] * 6
    assert result["trace"][1]["max_abs_velocity"] == .1


@pytest.mark.parametrize("failure", ["translation", "rotation", "non_a_speed", "predicate", "penetration",
                                    "robot", "observation", "qvel_binding", "mapping", "missing_mapping",
                                    "position_binding", "zero_quaternion", "missing_point"])
def test_r7_rejects_every_remaining_physical_or_evidence_failure(failure):
    rows = snapshots()
    row = rows[70]
    if failure == "translation":
        row["state"][10] = .0051
        row["object_positions"]["white_yellow_mug_1"][0] = .0051
    elif failure == "rotation":
        angle = np.deg2rad(1.01) / 2
        row["state"][13:17] = [np.cos(angle), 0., 0., np.sin(angle)]
    elif failure == "non_a_speed":
        row["state"][33] = row["qvel"][15] = .0101
    elif failure == "predicate":
        row["goals"], row["official_goal_values"] = [False, False], [False, False]
    elif failure == "penetration":
        row["penetrations"] = [{"geom1": "cup", "geom2": "door", "depth": .0021}]
    elif failure == "robot":
        row["robot_qpos"][0] = .0021
    elif failure == "observation":
        row["fresh_observation"]["agentview_image"] = np.zeros((2, 2, 4), dtype=np.uint8)
    elif failure == "qvel_binding":
        row["qvel"][9] = 0.
    elif failure == "mapping":
        row["stability_binding"]["model_xml_sha256"] = "b" * 64
    elif failure == "missing_mapping":
        del row["stability_binding"]
    elif failure == "position_binding":
        row["object_positions"]["white_yellow_mug_1"][0] = .001
    elif failure == "zero_quaternion":
        row["state"][13:17] = 0.
    elif failure == "missing_point":
        rows.pop()
    if failure in ("translation", "rotation", "non_a_speed", "zero_quaternion"):
        row["state_before_refresh"] = row["state"].copy()
    result = run(rows)
    assert result["technical_acceptance"] is False


def test_whole_window_checks_pairwise_rotation_and_bbox_not_only_initial_pose():
    h = helper()
    rows = snapshots(3)
    for row, sign in zip(rows, [-1, 0, 1]):
        row["state"][10] = sign * .003
        angle = np.deg2rad(sign * .6) / 2
        row["state"][13:17] = [np.cos(angle), 0., 0., np.sin(angle)]
    result = h.pose_window([h.sample(r["state"], r["qvel"], r["stability_binding"]) for r in rows])
    assert result["position_span_m"] == pytest.approx(.006)
    assert result["orientation_span_deg"] == pytest.approx(1.2)
    assert result["stable"] is False


def test_static_zero_can_precheck_but_never_certifies_formal_window():
    result = run(steps=0)
    assert result["static_acceptance"] is True
    assert result["technical_acceptance"] is False
    assert result["dynamic_stability"] is None


@pytest.mark.parametrize("field,value", [("velocity_tolerance", .02), ("position_tolerance", .006), ("steps", 149)])
def test_r7_rejects_changed_frozen_rules(field, value):
    with pytest.raises(ValueError):
        run(**{field: value})


@pytest.mark.parametrize("change", ["overlap", "unknown_type", "out_of_range", "wrong_target", "fractional_index"])
def test_compiled_joint_binding_rejects_invalid_full_layout(change):
    model = FakeModel()
    model.jnt_type, model.jnt_qposadr, model.jnt_dofadr = (x.copy() for x in
        (model.jnt_type, model.jnt_qposadr, model.jnt_dofadr))
    model.joint_names = list(model.joint_names)
    if change == "overlap": model.jnt_dofadr[10] = 14
    elif change == "unknown_type": model.jnt_type[0] = 7
    elif change == "out_of_range": model.jnt_qposadr[10] = 17
    elif change == "wrong_target": model.joint_names[9] = "other_object_joint0"
    elif change == "fractional_index": model.jnt_qposadr = model.jnt_qposadr.astype(float); model.jnt_qposadr[0] = .5
    with pytest.raises(ValueError):
        helper().binding_from_model(model, "a" * 64)


def test_episode_scope_and_profile_fail_closed():
    for field, value in [("task_id", "two_pots"), ("initial_state_index", 10), ("observation_profile", None)]:
        e = episode(); e[field] = value
        with pytest.raises(ValueError): helper().validate_scope(e)
    with pytest.raises(ValueError):
        validate_candidate(FakeEnv(snapshots()), episode(), hold_action=[0.] * 7,
                           observation_profile=V6_PROFILE)  # Never silently treat episode v7 as legacy.


def test_episode_cannot_omit_model_digest_or_disable_reference_pose():
    for field in ("model_xml_sha256", "reference_robot_qpos"):
        e = episode(); e.pop(field)
        with pytest.raises(ValueError): helper().validate_scope(e)


def test_binding_cannot_use_boolean_active_joint_metadata():
    binding = episode()["stability_binding"]
    binding["active_joint"] = dict(binding["active_joint"])
    binding["active_joint"]["type"] = False
    with pytest.raises(ValueError): helper().validate_binding(binding)


def test_nonunit_quaternion_is_normalized_for_rotation_only_and_raw_is_retained():
    rows = snapshots()
    rows[17]["state"][13:17] = [-3., 0., 0., 0.]
    rows[17]["state_before_refresh"] = rows[17]["state"].copy()
    result = run(rows)
    assert result["technical_acceptance"] is True
    assert result["stability_window"]["orientation_span_deg"] == 0.
    assert result["trace"][17]["state"][13] == -3.
    assert result["trace"][17]["stability_sample"]["active_pose_wxyz"][3] == -3.
