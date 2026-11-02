"""Task033 v6 numerical rule; pure arrays and auditor fakes, no simulator."""
from copy import deepcopy

import numpy as np
import pytest

from benchmark.remaining_goals.validation import compare_observations, validate_candidate, RGB_QUANTIZATION_AUDIT
from tests.test_remaining_validation import CandidateEnv, snapshot

V6 = "named-uint8-rgb-one-level-v6"


def obs(value=0):
    return {"agentview_image": np.full((16, 16, 3), value, dtype=np.uint8),
            "robot0_eye_in_hand_image": np.full((16, 16, 3), value, dtype=np.uint8),
            "proprio": np.zeros(8)}


def compare(left, right, **kwargs):
    return compare_observations(left, right, observation_profile=V6,
                                refresh_state_unchanged=kwargs.pop("refresh_state_unchanged", True), **kwargs)


def test_v6_all_pixels_may_differ_by_one_without_modifying_images():
    left, right = obs(), obs(1)
    before = deepcopy(right)
    result = compare(left, right)
    assert result["matches"] is True
    assert result["observation_profile"] == V6
    camera = result["image_diagnostics"]["observation.agentview_image"]
    assert camera["changed_pixels"] == 256 and camera["changed_fraction"] == 1.
    assert camera["max_changed_pixels"] is None and camera["max_abs_error"] == 1
    assert camera["shape"] == [16, 16, 3] and camera["dtype"] == "uint8"
    assert len(camera["returned_sha256"]) == len(camera["fresh_sha256"]) == 64
    assert camera["returned_sha256"] != camera["fresh_sha256"]
    assert all(np.array_equal(right[k], before[k]) for k in right)


@pytest.mark.parametrize("value", [2, 255])
def test_v6_one_pixel_error_above_one_rejected_without_uint8_overflow(value):
    left, right = obs(), obs()
    right["agentview_image"][0, 0, 0] = value
    result = compare(left, right)
    assert result["matches"] is False
    assert result["image_diagnostics"]["observation.agentview_image"]["max_abs_error"] == value


@pytest.mark.parametrize("state", [False, None])
def test_v6_unknown_or_changed_refresh_state_rejects_even_exact_images(state):
    assert compare(obs(), obs(), refresh_state_unchanged=state)["matches"] is False


@pytest.mark.parametrize("change", ["missing", "different_name", "shape", "dtype", "float_both", "no_camera"])
def test_v6_camera_identity_shape_and_uint8_contract_are_required(change):
    left, right = obs(), obs()
    if change == "missing": del right["agentview_image"]
    if change == "different_name": right["unknown_image"] = right.pop("agentview_image")
    if change == "shape": right["agentview_image"] = right["agentview_image"][:1]
    if change == "dtype": right["agentview_image"] = right["agentview_image"].astype(np.int16)
    if change == "float_both":
        left["agentview_image"] = left["agentview_image"].astype(float)
        right["agentview_image"] = right["agentview_image"].astype(float)
    if change == "no_camera": left = right = {"proprio": np.zeros(8)}
    assert compare(left, right)["matches"] is False


def test_v6_preserves_dynamic_nonrgb_tolerance_and_exact_initial_requirement():
    left, right = obs(), obs(1)
    right["proprio"][0] = 1e-9
    assert compare(left, right)["matches"] is True
    assert compare(left, right)["non_rgb_bit_exact"] is False
    assert compare(left, right, require_non_rgb_exact=True)["matches"] is False
    right["proprio"][0] = 2e-8
    assert compare(left, right)["matches"] is False


def test_v4_good_and_bad_areas_are_unchanged_next_to_v6():
    left, right = obs(), obs()
    right["agentview_image"][0, 0, 0] = 1
    assert compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)["matches"]
    right["agentview_image"][0, 1, 0] = 1
    legacy = compare_observations(left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert legacy["matches"] is False and "observation_profile" not in legacy
    assert compare(left, right)["matches"] is True


def test_v6_validate_records_profile_and_keeps_dynamic_nonrgb_original_rule():
    rows = [snapshot(i) for i in range(3)]
    for row in rows: row["fresh_observation"] = obs(1)
    rows[1]["fresh_observation"]["proprio"][0] = 1e-9
    env = CandidateEnv(rows, returned=obs())
    audit = validate_candidate(env, {"initial_mask": [True, False]}, steps=2, hold_action=[0] * 7,
                               observation_profile=V6)
    assert audit["technical_acceptance"] is True and audit["completed_steps"] == 2
    assert audit["observation_profile"] == V6
    assert audit["observation_audit_rule"]["rule_id"] == V6
    assert audit["limits"]["rgb_max_changed_fraction"] is None
    assert audit["trace"][1]["observation_check"]["non_rgb_bit_exact"] is False
    assert len(env.actions) == 2


def test_unknown_profile_and_conflicting_bounds_rejected():
    with pytest.raises(ValueError):
        compare_observations(obs(), obs(), observation_profile="unreviewed-v7")
    with pytest.raises(ValueError):
        compare(obs(), obs(), rgb_max_abs_error=2)
