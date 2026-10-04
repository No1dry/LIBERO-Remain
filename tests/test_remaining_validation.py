"""Pure fixtures for physical-state acceptance; no LIBERO/model dependency."""

from copy import deepcopy
import json

import numpy as np
import pytest

from benchmark.remaining_goals.validation import (
    compare_observations, validate_candidate, RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_RULE,
)


def observation(value=0):
    return {"images": {"front": np.full((2, 2, 3), value, dtype=np.uint8)}, "proprio": np.zeros(8)}


def snapshot(step=0):
    state = np.array([step * 0.05, 0.0, 0.0])
    return {
        "state": state, "state_before_refresh": state.copy(), "qvel": np.zeros(2),
        "robot_qpos": np.zeros(9), "object_positions": {"box": np.array([0.1, 0.2, 0.3])},
        "penetrations": [], "goals": [True, False], "fresh_observation": observation(),
    }


class CandidateEnv:
    def __init__(self, snapshots=None, returned=None):
        self.snapshots = snapshots or [snapshot(i) for i in range(3)]
        self.returned = returned
        self.index = 0
        self.actions = []
        self.restored = None

    def restore_candidate(self, episode):
        # No manifest validation or legal=True prerequisite.
        self.restored = deepcopy(episode)
        self.index = 0
        return deepcopy(self.returned or self.snapshots[0]["fresh_observation"])

    def step(self, action):
        self.actions.append(action.copy())
        self.index += 1
        return deepcopy(self.returned or self.snapshots[self.index].get("fresh_observation", observation()))

    def validation_snapshot(self):
        return deepcopy(self.snapshots[self.index])


def run(env=None, **kwargs):
    return validate_candidate(env or CandidateEnv(), {"episode_id": "candidate", "initial_mask": [True, False]},
                              steps=2, hold_action=[0] * 7, **kwargs)


def test_complete_validation_preserves_numeric_trace_and_does_not_claim_legality():
    env = CandidateEnv()
    audit = run(env)
    assert audit["technical_acceptance"] is True
    assert audit["static_acceptance"] is True
    assert audit["dynamic_stability"] is True
    assert audit["completed_steps"] == 2
    assert len(audit["trace"]) == 3
    assert audit["trace"][2]["state"][0] == 0.1  # Physics time may advance.
    assert audit["cross_mask_pose_checked"] is False
    assert audit["checks"]["reference_robot_pose_matches"] is None
    assert audit["refresh_nonstepping_checked"] is True
    assert "legal" not in audit and "construction" not in env.restored
    assert len(env.actions) == 2
    json.dumps(audit, allow_nan=False)


def test_static_only_does_not_claim_dynamic_stability():
    audit = validate_candidate(CandidateEnv(), {"initial_mask": [True, False]}, steps=0, hold_action=np.zeros(7))
    assert audit["technical_acceptance"] is True
    assert audit["dynamic_stability"] is None
    assert len(audit["trace"]) == 1


def test_temporary_predicate_violation_is_not_erased_by_recovery():
    rows = [snapshot(i) for i in range(3)]
    rows[1]["goals"] = [False, False]
    audit = run(CandidateEnv(rows))
    assert audit["technical_acceptance"] is False
    assert audit["checks"]["predicate_mask_matches"] is False
    assert audit["trace"][2]["goals"] == [True, False]


@pytest.mark.parametrize("field,value,check", [
    ("object_positions", {"box": [0.11, 0.2, 0.3]}, "object_positions_stable"),
    ("qvel", [0.02, 0.0], "velocities_below_limit"),
    ("robot_qpos", [0.01] + [0] * 8, "robot_pose_stable"),
    ("penetrations", [{"geom1": "object", "geom2": "table", "depth": 0.003}], "contact_penetration_within_limit"),
])
def test_measured_limit_failures_are_recorded(field, value, check):
    rows = [snapshot(i) for i in range(3)]
    rows[1][field] = value
    audit = run(CandidateEnv(rows))
    assert audit["technical_acceptance"] is False
    assert audit["checks"][check] is False
    assert audit["error"] is None


def test_cross_mask_robot_reference_is_checked_at_initial_restore():
    rows = [snapshot(i) for i in range(3)]
    for row in rows:
        row["robot_qpos"] = np.full(9, 0.1)
    audit = validate_candidate(CandidateEnv(rows), {"initial_mask": [True, False], "reference_robot_qpos": [0] * 9},
                               steps=2, hold_action=[0] * 7)
    assert audit["cross_mask_pose_checked"] is True
    assert audit["checks"]["robot_pose_stable"] is True
    assert audit["checks"]["reference_robot_pose_matches"] is False
    assert audit["static_acceptance"] is False


def test_explicit_ignored_contact_pairs_remain_visible_in_trace():
    rows = [snapshot(i) for i in range(3)]
    for row in rows:
        row["penetrations"] = [{"geom1": "support", "geom2": "base", "depth": 0.05}]
    audit = run(CandidateEnv(rows), ignored_contact_pairs=[("base", "support")])
    assert audit["technical_acceptance"] is True
    assert audit["trace"][0]["max_raw_penetration"] == 0.05
    assert audit["trace"][0]["max_checked_penetration"] == 0.0
    assert audit["trace"][0]["penetrations"][0]["ignored"] is True


def test_stale_restored_or_step_observation_is_rejected():
    audit = run(CandidateEnv(returned=observation(1)))
    assert audit["technical_acceptance"] is False
    assert audit["checks"]["observation_matches_fresh"] is False
    assert audit["trace"][0]["observation_check"]["mismatched_fields"] == ["observation.images.front"]


def test_observation_refresh_must_not_change_physics_state():
    rows = [snapshot(i) for i in range(3)]
    rows[1]["state_before_refresh"] = [100, 0, 0]
    audit = run(CandidateEnv(rows))
    assert audit["technical_acceptance"] is False
    assert audit["checks"]["refresh_did_not_step"] is False


def test_unavailable_independent_refresh_state_check_is_declared():
    rows = [snapshot(i) for i in range(3)]
    for row in rows:
        row.pop("state_before_refresh")
    audit = run(CandidateEnv(rows))
    assert audit["technical_acceptance"] is True
    assert audit["refresh_nonstepping_checked"] is False
    assert audit["checks"]["refresh_did_not_step"] is None


@pytest.mark.parametrize("change", [
    lambda row: row.update(state=[float("nan"), 0]),
    lambda row: row.update(qvel=[float("inf")]),
    lambda row: row.update(goals=[1, False]),
    lambda row: row.update(robot_qpos=[0]),
    lambda row: row.update(object_positions={"other": [0, 0, 0]}),
    lambda row: row.pop("penetrations"),
    lambda row: row.pop("fresh_observation"),
])
def test_invalid_snapshot_fails_without_nonfinite_json(change):
    rows = [snapshot(i) for i in range(3)]
    change(rows[1])
    audit = run(CandidateEnv(rows))
    assert audit["technical_acceptance"] is False
    assert audit["checks"]["snapshot_contract_valid"] is False
    assert audit["error"]["phase"] == "validation_snapshot"
    assert audit["static_acceptance"] is True
    assert audit["checks"]["finite_state_and_velocity"] is None
    json.dumps(audit, allow_nan=False)


def test_restore_exception_returns_diagnostic_audit():
    class Broken(CandidateEnv):
        def restore_candidate(self, episode):
            raise RuntimeError("candidate restoration failed")
    audit = run(Broken())
    assert audit["technical_acceptance"] is False
    assert audit["trace"] == []
    assert audit["error"]["phase"] == "restore_candidate"
    assert audit["dynamic_stability"] is False


@pytest.mark.parametrize("kwargs", [
    {"steps": -1}, {"steps": True}, {"hold_action": [0] * 6},
    {"hold_action": [float("nan")] * 7}, {"position_tolerance": -0.1},
    {"velocity_tolerance": True}, {"ignored_contact_pairs": [("only-one",)]},
])
def test_invalid_arguments_raise_value_error(kwargs):
    options = {"steps": 2, "hold_action": [0] * 7, **kwargs}
    with pytest.raises(ValueError):
        validate_candidate(CandidateEnv(), {"initial_mask": [True, False]}, **options)


def test_observation_comparison_is_strict_for_images_but_tolerant_for_float_noise():
    left = observation()
    right = deepcopy(left)
    right["proprio"][0] = 1e-10
    assert compare_observations(left, right)["matches"] is True
    right["images"]["front"][0, 0, 0] = 1
    assert compare_observations(left, right, atol=2)["matches"] is False


def test_observation_comparison_rejects_missing_keys_and_nonfinite_channels():
    assert compare_observations(observation(), {"proprio": np.zeros(8)})["matches"] is False
    bad = observation()
    bad["proprio"][0] = float("nan")
    assert compare_observations(observation(), bad)["matches"] is False


def test_optin_rgb_quantization_is_per_pixel_per_camera_and_retains_raw_evidence():
    left = {"agentview_image": np.zeros((4, 4, 3), dtype=np.uint8),
            "robot0_eye_in_hand_image": np.zeros((4, 4, 3), dtype=np.uint8), "proprio": np.zeros(3)}
    right = deepcopy(left)
    right["agentview_image"][1, 2, :2] = 1  # Two channels, exactly one pixel.
    right["robot0_eye_in_hand_image"][0, 1, :] = 1
    right["proprio"][0] = 1e-10
    before_left, before_right = deepcopy(left), deepcopy(right)
    result = compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert result["matches"] is True and result["bit_exact"] is False
    assert result["bounded_allowance_used"] is True
    assert result["returned_sha256"] != result["fresh_sha256"]
    for info in result["image_diagnostics"].values():
        assert info == {"bit_exact": False, "changed_pixels": 1, "total_pixels": 16,
                        "changed_fraction": 1 / 16, "max_changed_pixels": 1,
                        "max_changed_fraction": 0.0001,
                        "max_abs_error": 1, "bounded_allowance_used": True}
    for key in left:
        np.testing.assert_array_equal(left[key], before_left[key])
        np.testing.assert_array_equal(right[key], before_right[key])


@pytest.mark.parametrize("kind", ["two_pixels", "error_two", "full_image", "uint16", "rgba", "float_image", "integer_proprio",
                                   "unnamed_rgb_array", "float_proprio"])
def test_quantization_does_not_hide_stale_images_or_other_channel_changes(kind):
    left = observation()
    right = deepcopy(left)
    if kind == "two_pixels":
        right["images"]["front"][0, :, 0] = 1
    elif kind == "error_two":
        right["images"]["front"][0, 0, 0] = 2
    elif kind == "full_image":
        right["images"]["front"][:] = 1
    elif kind in ("uint16", "rgba", "float_image"):
        shape = (2, 2, 4) if kind == "rgba" else (2, 2, 3)
        dtype = {"uint16": np.uint16, "rgba": np.uint8, "float_image": np.float64}[kind]
        left["images"]["front"] = np.zeros(shape, dtype=dtype)
        right = deepcopy(left)
        right["images"]["front"][0, 0, 0] = 1
    elif kind == "integer_proprio":
        left["proprio"] = np.zeros(8, dtype=np.uint8)
        right["proprio"] = np.zeros(8, dtype=np.uint8)
        right["proprio"][0] = 1
    elif kind == "unnamed_rgb_array":
        left["proprio"] = np.zeros((2, 2, 3), dtype=np.uint8)
        right["proprio"] = np.ones((2, 2, 3), dtype=np.uint8)
    else:
        right["proprio"][0] = 2e-8
    result = compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert result["matches"] is False
    assert result["bounded_allowance_used"] is False


@pytest.mark.parametrize("unchanged", [False, None])
def test_quantization_requires_affirmative_refresh_state_verification(unchanged):
    left, right = observation(), observation()
    right["images"]["front"][0, 0, 0] = 1
    result = compare_observations(left, right, refresh_state_unchanged=unchanged, **RGB_QUANTIZATION_AUDIT)
    assert result["matches"] is False and result["bounded_allowance_used"] is False


def test_validation_records_rule_and_actual_allowance_use_without_claiming_bit_identity():
    rows = [snapshot(i) for i in range(3)]
    for row in rows[1:]:
        row["fresh_observation"]["images"]["front"][0, 0, 0] = 1
    audit = run(CandidateEnv(rows, returned=observation()), **RGB_QUANTIZATION_AUDIT)
    assert audit["technical_acceptance"] is True
    assert all(audit["limits"][key] == value for key, value in RGB_QUANTIZATION_AUDIT.items())
    assert audit["observation_audit_rule"] == RGB_QUANTIZATION_RULE
    assert any("max(1, floor(height * width * 0.0001))" in item for item in audit["limitations"])
    assert audit["trace"][0]["observation_check"]["bit_exact"] is True
    assert audit["trace"][0]["observation_check"]["bounded_allowance_used"] is False
    for row in audit["trace"][1:]:
        assert row["checks"]["rgb_allowance_state_verified"] is True
        assert row["observation_check"]["bounded_allowance_used"] is True
        assert row["observation_check"]["bit_exact"] is False


def test_initial_rgb_allows_fixed_quantization_with_exact_state_and_non_rgb_evidence():
    returned = observation()
    returned["images"]["front"][0, 0, 0] = 1
    audit = run(CandidateEnv(returned=returned), **RGB_QUANTIZATION_AUDIT)
    assert audit["technical_acceptance"] is True
    first = audit["trace"][0]["observation_check"]
    assert first["bit_exact"] is False and first["bounded_allowance_used"] is True
    assert first["non_rgb_bit_exact"] is True
    assert first["returned_sha256"] != first["fresh_sha256"]
    assert first["returned_non_rgb_sha256"] == first["fresh_non_rgb_sha256"]
    assert audit["checks"]["initial_non_rgb_bit_exact"] is True


@pytest.mark.parametrize("change", ["tiny_float", "signed_zero", "dtype"])
def test_initial_non_rgb_requires_typed_byte_equality_even_when_dynamic_values_match(change):
    returned = observation()
    if change == "tiny_float":
        returned["proprio"][0] = 1e-10
    elif change == "signed_zero":
        returned["proprio"][0] = -0.0
    else:
        returned["proprio"] = returned["proprio"].astype(np.float32)
    audit = run(CandidateEnv(returned=returned), **RGB_QUANTIZATION_AUDIT)
    assert audit["technical_acceptance"] is False
    assert audit["static_acceptance"] is False
    assert audit["checks"]["initial_non_rgb_bit_exact"] is False
    first = audit["trace"][0]["observation_check"]
    assert first["non_rgb_bit_exact"] is False
    assert first["returned_non_rgb_sha256"] != first["fresh_non_rgb_sha256"]
    assert first["matches"] is False
    assert compare_observations(returned, observation())["matches"] is True


def test_initial_rgb_tolerance_cannot_apply_without_bit_exact_state_proof():
    rows = [snapshot(i) for i in range(3)]
    rows[0]["state_before_refresh"][1] = -0.0
    returned = observation()
    returned["images"]["front"][0, 0, 0] = 1
    audit = run(CandidateEnv(rows, returned=returned), **RGB_QUANTIZATION_AUDIT)
    assert audit["technical_acceptance"] is False
    assert audit["trace"][0]["checks"]["rgb_allowance_state_verified"] is False
    assert audit["trace"][0]["observation_check"]["bounded_allowance_used"] is False


def test_non_rgb_exact_mode_requires_explicit_boolean():
    with pytest.raises(ValueError, match="require_non_rgb_exact"):
        compare_observations(observation(), observation(), require_non_rgb_exact=1)


@pytest.mark.parametrize("change", ["changed_state", "signed_zero", "missing_state"])
def test_validation_cannot_enable_rgb_rule_without_bit_exact_refresh_state(change):
    rows = [snapshot(i) for i in range(3)]
    if change == "changed_state":
        rows[1]["state_before_refresh"][1] = 1e-16
    elif change == "signed_zero":
        rows[1]["state_before_refresh"][1] = -0.
    else:
        rows[1].pop("state_before_refresh")
    returned = observation()
    returned["images"]["front"][0, 0, 0] = 1
    audit = run(CandidateEnv(rows, returned=returned), **RGB_QUANTIZATION_AUDIT)
    assert audit["technical_acceptance"] is False
    assert audit["trace"][1]["checks"]["rgb_allowance_state_verified"] is False
    assert audit["trace"][1]["observation_check"]["bounded_allowance_used"] is False


@pytest.mark.parametrize("bounds", [(2, 0.0001), (1, 0.0002), (True, 0.0001),
                                   (1, 0), (0, 0.0001), (1., 0.0001), (1, True),
                                   (1, float("nan")), (1, float("inf")), (1, -0.0001)])
def test_rgb_rule_cannot_be_widened_via_unbounded_configuration(bounds):
    with pytest.raises(ValueError, match="RGB audit bounds"):
        compare_observations(observation(), observation(), rgb_max_abs_error=bounds[0], rgb_max_changed_fraction=bounds[1])


@pytest.mark.parametrize("count,error,accepted", [(2, 1, True), (6, 1, True), (7, 1, False),
                                                (1, 2, False), (256 * 256, 1, False)])
def test_256_rgb_area_cap_accepts_sparse_rounding_but_rejects_dense_or_larger_errors(count, error, accepted):
    left = {"images": {"front": np.zeros((256, 256, 3), dtype=np.uint8)}}
    right = deepcopy(left)
    right["images"]["front"].reshape(-1, 3)[:count] = error
    result = compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert result["matches"] is accepted
    assert result["bounded_allowance_used"] is accepted
    assert result["returned_sha256"] != result["fresh_sha256"]
    info = result["image_diagnostics"]["observation.images.front"]
    assert info["total_pixels"] == 256 * 256
    assert info["max_changed_pixels"] == 6
    assert info["changed_pixels"] == count
    assert info["changed_fraction"] == count / (256 * 256)
    assert info["max_abs_error"] == error
    assert compare_observations(left, right)["matches"] is False


@pytest.mark.parametrize("height,width,cap", [(2, 2, 1), (128, 128, 1), (128, 256, 3),
                                           (256, 256, 6), (512, 512, 26)])
def test_rgb_cap_is_per_camera_resolution_and_rounds_down_with_minimum_one(height, width, cap):
    left = {"agentview_image": np.zeros((height, width, 3), dtype=np.uint8),
            "robot0_eye_in_hand_image": np.zeros((2, 2, 3), dtype=np.uint8)}
    right = deepcopy(left)
    right["agentview_image"].reshape(-1, 3)[:cap] = 1
    right["robot0_eye_in_hand_image"][0, 0] = 1
    result = compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert result["matches"] is True
    assert result["image_diagnostics"]["observation.agentview_image"]["max_changed_pixels"] == cap
    assert result["image_diagnostics"]["observation.robot0_eye_in_hand_image"]["max_changed_pixels"] == 1
    right["agentview_image"].reshape(-1, 3)[cap] = 1
    assert compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)["matches"] is False
