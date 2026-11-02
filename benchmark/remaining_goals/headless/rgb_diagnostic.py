"""File-only R2 RGB proposal diagnostics. Never changes source acceptance.

The recorded v4 checks remain authoritative. This module cannot be selected by
the construction, replay, source-acceptance or policy paths as an alternate gate.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "remaining-task033-r2-rgb-diagnostic-v1"
PROPOSAL = {
    "rule_id": "named-uint8-rgb-one-level-area-cap-v5-proposal-only",
    "status": "pending_codex_decision_not_an_acceptance_rule",
    "max_abs_channel_error": 1,
    "max_changed_fraction": 0.00015,
    "pixel_cap_formula": "max(1, floor(height * width * 0.00015))",
    "scope": "two_pots mask10; recorded 256x256 agentview and wrist cameras",
    "requires_exact_state_and_non_rgb_at_every_comparison": True,
    "basis": "post-hoc minimum proposal covering the read 7-9 pixel examples; not a renderer error bound",
}
CAMERAS = {"observation.agentview_image", "observation.robot0_eye_in_hand_image"}
PHYSICAL_CHECKS = {"finite_state_and_velocity", "predicate_mask_matches", "object_positions_stable",
    "velocities_below_limit", "robot_pose_stable", "reference_robot_pose_matches",
    "contact_penetration_within_limit", "initial_constraints_match"}
LIMITATION = ("Uses recorded comparison diagnostics and their original hashes, not independently recomputed RGB pixels. "
    "A matching proposal comparison does not validate the remaining frames, physical trajectory, source or renderer cause. "
    "Original failed booleans remain unchanged; no source can become ready through this tool.")


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def diagnose_comparison(check, *, state_verified):
    """Assess a counterfactual comparison rule only, preserving recorded v4 truth."""
    check = deepcopy(check) if isinstance(check, dict) else {}
    reasons, cameras = [], {}
    strict = check.get("matches") if type(check.get("matches")) is bool else None
    if strict is None:
        reasons.append("recorded_v4_result_missing")
    if state_verified is not True or check.get("rgb_allowance_state_verified") is not True:
        reasons.append("bit_exact_state_evidence_missing_or_false")
    hashes = ("returned_sha256", "fresh_sha256", "returned_non_rgb_sha256", "fresh_non_rgb_sha256")
    if any(not _digest(check.get(key)) for key in hashes):
        reasons.append("comparison_hash_evidence_missing")
    if (check.get("non_rgb_bit_exact") is not True
            or check.get("returned_non_rgb_sha256") != check.get("fresh_non_rgb_sha256")):
        reasons.append("non_rgb_not_bit_exact")
    if check.get("errors") != []:
        reasons.append("comparison_has_errors_or_missing_error_evidence")
    images = check.get("image_diagnostics")
    if not isinstance(images, dict) or set(images) != CAMERAS:
        reasons.append("expected_two_named_camera_diagnostics_missing")
        images = {}
    old_mismatches, old_changed, maximum = [], False, 0
    for name, item in images.items():
        if (not isinstance(item, dict) or any(type(item.get(k)) is not int for k in
                ("changed_pixels", "total_pixels", "max_abs_error", "max_changed_pixels"))):
            reasons.append(f"{name}: invalid_integer_diagnostics")
            continue
        count, area, error = item["changed_pixels"], item["total_pixels"], item["max_abs_error"]
        old_cap, proposed_cap = max(1, area // 10000), max(1, math.floor(area * 0.00015))
        old_allowance = state_verified is True and 0 < count <= old_cap and error <= 1
        if (area != 256 * 256 or not 0 <= count <= area or error < 0
                or (count == 0) != (error == 0)
                or item.get("max_changed_fraction") != 0.0001 or item["max_changed_pixels"] != old_cap
                or item.get("changed_fraction") != count / area
                or item.get("bit_exact") is not (count == 0)
                or item.get("bounded_allowance_used") is not old_allowance):
            reasons.append(f"{name}: inconsistent_or_out_of_scope_diagnostics")
        if count > proposed_cap or error > 1:
            reasons.append(f"{name}: exceeds_proposed_one_level_area_cap")
        if count > old_cap or error > 1:
            old_mismatches.append(name)
        old_changed |= old_allowance
        maximum = max(maximum, error)
        cameras[name] = {"changed_pixels": count, "total_pixels": area, "max_abs_error": error,
            "recorded_max_changed_pixels": old_cap, "proposed_max_changed_pixels": proposed_cap}
    if images:
        if (type(check.get("max_abs_error")) not in (int, float)
                or check["max_abs_error"] != maximum
                or check.get("bounded_allowance_used") is not old_changed
                or check.get("bit_exact") is not (maximum == 0)
                or (check.get("returned_sha256") == check.get("fresh_sha256")) != (maximum == 0)):
            reasons.append("global_comparison_diagnostics_inconsistent")
        if (check.get("mismatched_fields") != sorted(old_mismatches)
                or strict is not (not old_mismatches)):
            reasons.append("recorded_v4_outcome_inconsistent_with_rgb_only_evidence")
    supported = not reasons
    return {"classification": ("strict_match" if strict else "proposal_candidate") if supported else "not_supported",
        "recorded_v4_matches": strict, "proposal_comparison_would_match": supported,
        "acceptance_authorized": False, "reasons": sorted(set(reasons)), "cameras": cameras,
        "recorded_hashes": {key: check.get(key) for key in hashes},
        "input_evidence_level": "recorded_diagnostics_only", "raw_rgb_recomputed": False}


def diagnose_audit(audit):
    """Read existing construction/replay audit values; never replace its checks."""
    from ..validation import RGB_QUANTIZATION_RULE
    if (not isinstance(audit, dict) or audit.get("schema_version") != "remaining-goals-validation-v1"
            or not re.fullmatch(r"two_pots_s00[0-9]_10", str(audit.get("episode_id")))
            or audit.get("observation_audit_rule") != RGB_QUANTIZATION_RULE
            or not isinstance(audit.get("trace"), list)):
        raise ValueError("diagnostic requires an original v4 two_pots mask10 audit")
    observations = []
    for row in audit["trace"]:
        if not isinstance(row, dict) or type(row.get("step")) is not int or row["step"] < 0:
            raise ValueError("invalid recorded audit step")
        checks = row.get("checks") if isinstance(row.get("checks"), dict) else {}
        result = diagnose_comparison(row.get("observation_check"), state_verified=checks.get("refresh_did_not_step"))
        other = sorted(name for name in PHYSICAL_CHECKS if checks.get(name) is not True)
        other.extend(sorted(name for name, value in checks.items()
            if name not in PHYSICAL_CHECKS | {"observation_matches_fresh"}
            and value is not True))
        result.update(stage="initial" if row["step"] == 0 else "dynamic", step=row["step"],
            other_check_issues=other, only_rgb_failure=(not other and result["classification"] == "proposal_candidate"))
        observations.append(result)
    if audit.get("reset_observation_comparison") is not None:
        reset = audit.get("formal_reset_checks") or {}
        result = diagnose_comparison(audit["reset_observation_comparison"], state_verified=reset.get("saved_state_exact"))
        other = sorted(key for key in ("saved_state_exact", "initial_mask_exact", "initial_non_rgb_exact") if reset.get(key) is not True)
        result.update(stage="formal_reset", step=0, other_check_issues=other,
                      only_rgb_failure=(not other and result["classification"] == "proposal_candidate"))
        observations.insert(0, result)
    requested, completed = audit.get("requested_steps"), audit.get("completed_steps")
    complete = (type(requested) is int and type(completed) is int and 0 <= requested == completed
                and len(audit["trace"]) == requested + 1 and audit.get("error") is None
                and [r["step"] for r in audit["trace"]] == list(range(requested + 1)))
    return {"episode_id": audit["episode_id"], "original_technical_acceptance": audit.get("technical_acceptance"),
        "original_error": deepcopy(audit.get("error")), "complete_recorded_window": complete,
        "observations": observations, "recorded_comparisons": len(observations),
        "proposal_candidate_comparisons": sum(r["classification"] == "proposal_candidate" for r in observations),
        "can_change_source_status": False, "limitation": LIMITATION}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True, action="append", help="Saved original audit.json; repeat for each selected audit")
    parser.add_argument("--out", type=Path, required=True, help="New diagnostic JSON outside original audit directories")
    args = parser.parse_args(argv)
    output = args.out.resolve()
    inputs = [path.resolve() for path in args.audit]
    if any(output == path or path.parent in output.parents for path in inputs):
        raise ValueError("diagnostic output must be separate from original audit directories")
    if output.exists():
        raise FileExistsError(output)
    from .source_acceptance import _json
    reports = []
    for path in inputs:
        raw = path.read_bytes()
        report = diagnose_audit(_json(raw))
        report.update(source_path=str(path), source_sha256=hashlib.sha256(raw).hexdigest())
        reports.append(report)
    value = {"schema_version": SCHEMA, "proposal": deepcopy(PROPOSAL), "reports": reports,
        "acceptance_authorized": False, "old_reports_rewritten": False, "policy_called": False,
        "native_created": False, "limitation": LIMITATION}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "audits_read": len(reports), "acceptance_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
