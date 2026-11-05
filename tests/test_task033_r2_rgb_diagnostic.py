"""R2 RGB review is file-only evidence, never a source acceptance override."""
from copy import deepcopy
import importlib
import json

import numpy as np
import pytest

from benchmark.remaining_goals.validation import compare_observations, RGB_QUANTIZATION_AUDIT


def comparison(count=9, error=1):
    left = {"agentview_image": np.zeros((256, 256, 3), dtype=np.uint8),
            "robot0_eye_in_hand_image": np.zeros((256, 256, 3), dtype=np.uint8),
            "robot0_eef_pos": np.zeros(3)}
    right = deepcopy(left)
    right["robot0_eye_in_hand_image"].reshape(-1, 3)[:count, 0] = error
    return compare_observations(left, right, atol=0, require_non_rgb_exact=True,
                                refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)


@pytest.mark.parametrize("count", [7, 8, 9])
def test_recorded_sparse_one_level_failure_is_only_a_proposal_candidate(count):
    d = importlib.import_module("benchmark.remaining_goals.headless.rgb_diagnostic")
    check = comparison(count)
    before = deepcopy(check)
    result = d.diagnose_comparison(check, state_verified=True)
    assert check == before and check["matches"] is False
    assert result["recorded_v4_matches"] is False
    assert result["classification"] == "proposal_candidate"
    assert result["proposal_comparison_would_match"] is True
    assert result["acceptance_authorized"] is False
    assert "ready" not in result
    assert result["cameras"]["observation.robot0_eye_in_hand_image"]["proposed_max_changed_pixels"] == 9


@pytest.mark.parametrize("fault", ["ten_pixels", "error_two", "changed_state", "unknown_state", "non_rgb",
                                  "missing_camera", "missing_hash", "lying_hash", "fraction", "lying_pass"])
def test_proposal_does_not_hide_real_misalignment_or_missing_evidence(fault):
    d = importlib.import_module("benchmark.remaining_goals.headless.rgb_diagnostic")
    check = comparison(10 if fault == "ten_pixels" else 9, 2 if fault == "error_two" else 1)
    state = True
    if fault == "changed_state": state = False
    if fault == "unknown_state": state = None
    if fault == "non_rgb":
        check["non_rgb_bit_exact"] = False
        check["fresh_non_rgb_sha256"] = "f" * 64
    if fault == "missing_camera": check["image_diagnostics"].pop("observation.agentview_image")
    if fault == "missing_hash": check.pop("fresh_sha256")
    if fault == "lying_hash": check["fresh_sha256"] = check["returned_sha256"]
    if fault == "fraction": check["image_diagnostics"]["observation.robot0_eye_in_hand_image"]["changed_fraction"] = 0.
    if fault == "lying_pass": check["matches"] = True
    result = d.diagnose_comparison(check, state_verified=state)
    assert result["proposal_comparison_would_match"] is False
    assert result["classification"] == "not_supported"
    assert result["reasons"] and not result["acceptance_authorized"]


def test_strict_pass_remains_original_not_a_new_physical_result():
    d = importlib.import_module("benchmark.remaining_goals.headless.rgb_diagnostic")
    result = d.diagnose_comparison(comparison(6), state_verified=True)
    assert result["recorded_v4_matches"] is True
    assert result["classification"] == "strict_match"
    assert not result["acceptance_authorized"]


def audit(check=None):
    from benchmark.remaining_goals.validation import RGB_QUANTIZATION_RULE
    return {"schema_version": "remaining-goals-validation-v1", "episode_id": "two_pots_s000_10",
        "observation_audit_rule": deepcopy(RGB_QUANTIZATION_RULE), "technical_acceptance": False,
        "requested_steps": 0, "completed_steps": 0, "error": None,
        "trace": [{"step": 0, "observation_check": check or comparison(), "checks": {
            "finite_state_and_velocity": True, "predicate_mask_matches": True,
            "object_positions_stable": True, "velocities_below_limit": True,
            "robot_pose_stable": True, "reference_robot_pose_matches": True,
            "contact_penetration_within_limit": True, "observation_matches_fresh": False,
            "initial_non_rgb_bit_exact": True, "refresh_did_not_step": True,
            "rgb_allowance_state_verified": True, "initial_constraints_match": True}}]}


def test_audit_separates_observation_proposal_from_physical_failure_and_reset():
    d = importlib.import_module("benchmark.remaining_goals.headless.rgb_diagnostic")
    value = audit()
    value["trace"][0]["checks"]["velocities_below_limit"] = False
    result = d.diagnose_audit(value)
    assert result["observations"][0]["proposal_comparison_would_match"] is True
    assert result["observations"][0]["only_rgb_failure"] is False
    assert result["observations"][0]["other_check_issues"] == ["velocities_below_limit"]
    reset = audit()
    reset["trace"] = []
    reset["reset_observation_comparison"] = comparison(7)
    reset["formal_reset_checks"] = {"saved_state_exact": True, "initial_mask_exact": True,
        "construction_observation_matches": False, "initial_non_rgb_exact": True}
    result = d.diagnose_audit(reset)
    assert result["observations"][0]["stage"] == "formal_reset"
    assert result["observations"][0]["only_rgb_failure"] is True
    assert not result["complete_recorded_window"]
    assert result["can_change_source_status"] is False


def test_cli_reads_existing_audit_without_overwrite_or_native(tmp_path, capsys):
    d = importlib.import_module("benchmark.remaining_goals.headless.rgb_diagnostic")
    original = tmp_path / "original" / "audit.json"
    original.parent.mkdir()
    original.write_text(json.dumps(audit()), encoding="utf-8")
    raw = original.read_bytes()
    output = tmp_path / "review" / "rgb.json"
    assert d.main(["--audit", str(original), "--out", str(output)]) == 0
    report = json.loads(output.read_text())
    assert original.read_bytes() == raw
    assert report["policy_called"] is False and report["native_created"] is False
    assert report["reports"][0]["source_sha256"]
    assert report["reports"][0]["original_technical_acceptance"] is False
    assert report["acceptance_authorized"] is False and report["old_reports_rewritten"] is False
    with pytest.raises(FileExistsError):
        d.main(["--audit", str(original), "--out", str(output)])
    with pytest.raises(ValueError, match="separate"):
        d.main(["--audit", str(original), "--out", str(original.parent / "derived.json")])
    capsys.readouterr()
