"""Technical acceptance of a restored candidate, without running a policy.

Static checks and stability under one explicit control action do not prove
physical reachability or that the remaining task can be executed. In particular,
this module never writes ``construction.legal=True`` and never uses model success
to admit candidates. Thresholds are declared measurement limits, not universal
physics constants; a state-generation protocol must calibrate and freeze them.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from numbers import Real
from typing import Any

import numpy as np

RGB_QUANTIZATION_AUDIT = {"rgb_max_abs_error": 1, "rgb_max_changed_fraction": 0.0001}
RGB_QUANTIZATION_RULE = {
    "rule_id": "named-uint8-rgb-one-level-area-cap-v4-typed-initial-evidence",
    "scope": "construction/reset and returned/fresh observations; initial non-RGB channels are dtype-and-byte exact",
    "max_abs_channel_error": 1,
    "max_changed_fraction": 0.0001,
    "changed_pixel_definition": "any RGB channel differs at that pixel",
    "pixel_cap_formula": "max(1, floor(height * width * max_changed_fraction))",
    "minimum_pixel_cap": 1,
    "eligible_channels": "named uint8 HxWx3 cameras only",
    "requires_bit_exact_nonstepping_refresh_state": True,
    "policy_images_modified": False,
    "formal_reset_hash_check": "raw hashes retained; compare SHA-bound typed observation artifacts with exact state/non-RGB and bounded RGB",
    "basis": "conservative engineering tolerance; not an empirically established renderer error bound",
}
RGB_QUANTIZATION_LIMITATION = (
    "Opt-in technical audit caps changed uint8 RGB pixels per camera at "
    "max(1, floor(height * width * 0.0001)): 6 pixels at 256x256. The minimum-one rule "
    "can exceed 0.01% on small images. This is a conservative engineering tolerance, "
    "not an empirically established renderer error bound, "
    "with channel error at most 1, only after bit-exact non-stepping state verification. "
    "Initial non-RGB channels must have identical dtype, shape and bytes; initial RGB uses the same fixed bound. "
    "Cross-reset comparisons use SHA-bound original typed observations, not hashes alone. "
    "Raw image hashes and differences remain recorded; policy images are unchanged."
)

# Explicit new profile. Legacy v4 constants and unversioned callers stay frozen.
V6_PROFILE = "named-uint8-rgb-one-level-v6"
V6_RGB_RULE = {
    "rule_id": V6_PROFILE,
    "scope": "construction/reset and returned/fresh observations; unchanged initial and dynamic non-RGB requirements",
    "max_abs_channel_error": 1,
    "max_changed_fraction": None,
    "changed_pixel_definition": "any RGB channel differs at that pixel",
    "changed_area_role": "diagnostic_only",
    "eligible_channels": "named uint8 HxWx3 cameras only",
    "requires_bit_exact_nonstepping_refresh_state": True,
    "policy_images_modified": False,
    "formal_reset_hash_check": "SHA-bound original typed observations with exact saved state and initial non-RGB",
    "basis": "uniform 8-bit numerical consistency definition; not a calibrated renderer or policy invariance claim",
}
V6_RGB_LIMITATION = (
    "Explicit v6 accepts uint8 RGB channel differences at most one after verified bit-exact non-stepping "
    "state correspondence. Changed area is diagnostic only. Initial/reset non-RGB remains dtype-and-byte "
    "exact; dynamic non-RGB retains the original 1e-8 absolute limit. Original images and hashes are "
    "retained. This is a numerical operation definition, not calibrated GL error or VLA invariance."
)


def observation_profile_config(profile=None):
    """Return a detached, versioned rule; None preserves the original v4 producer."""
    if profile in (None, RGB_QUANTIZATION_RULE["rule_id"]):
        return {"rule": deepcopy(RGB_QUANTIZATION_RULE), "limits": dict(RGB_QUANTIZATION_AUDIT),
                "limitation": RGB_QUANTIZATION_LIMITATION}
    if profile != V6_PROFILE:
        raise ValueError("unsupported observation profile")
    return {"rule": deepcopy(V6_RGB_RULE),
            "limits": {"rgb_max_abs_error": 1, "rgb_max_changed_fraction": None},
            "limitation": V6_RGB_LIMITATION}


def _observation_settings(profile, max_error, max_fraction):
    if profile is None:
        return _rgb_bounds(max_error, max_fraction), max_error, max_fraction
    config = observation_profile_config(profile)
    expected = config["limits"]
    if (type(max_error) is not int or max_fraction is not None and type(max_fraction) not in (int, float)
            or (max_error, max_fraction) != (0, 0.0)
            and (max_error, max_fraction) != (expected["rgb_max_abs_error"], expected["rgb_max_changed_fraction"])):
        raise ValueError("observation profile conflicts with explicit RGB bounds")
    return True, expected["rgb_max_abs_error"], expected["rgb_max_changed_fraction"]


def _rgb_bounds(max_error, max_fraction):
    if (type(max_error) is not int or type(max_fraction) not in (int, float)
            or (max_error, max_fraction) not in ((0, 0.0), (1, 0.0001))):
        raise ValueError("RGB audit bounds must be disabled (0,0) or the fixed one-level/area-fraction rule (1,0.0001)")
    return bool(max_error)


def _vector(value: Any, name: str, size: int | None = None) -> np.ndarray:
    array = np.asarray(value)
    if (array.ndim != 1 or not array.size or array.dtype.kind not in "fiu"
            or not np.isfinite(array).all()):
        raise ValueError(f"{name} must be a nonempty finite real vector")
    if size is not None and array.size != size:
        raise ValueError(f"{name} must contain {size} elements")
    return array.astype(np.float64, copy=True)


def _limit(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _array_hash(array: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(array, dtype="<f8").tobytes()).hexdigest()


def compare_observations(observation: dict, fresh_observation: dict, *, atol: float = 1e-8,
                         rgb_max_abs_error: int = 0, rgb_max_changed_fraction: float = 0.0,
                         refresh_state_unchanged: bool | None = None,
                         require_non_rgb_exact: bool = False, observation_profile: str | None = None) -> dict:
    """Compare returned observations with an independently refreshed observation.

    Nested dictionaries of finite numeric arrays/scalars are supported. Integer
    images are compared exactly by default; floating channels use absolute tolerance with
    zero relative tolerance. A mismatch or malformed observation is a failed
    check, not a truthy coercion. The adapter must force a non-stepping simulator
    refresh for ``fresh_observation``: comparing two copies of the same stale
    cache cannot establish freshness. The optional fixed RGB quantization rule
    applies only to named uint8 HxWx3 camera channels and a verified unchanged
    refresh state. Integer proprioception and other channels remain exact.
    require_non_rgb_exact additionally checks original dtype, shape and bytes
    outside eligible RGB channels, including signed zero and tiny float changes.
    Images are neither changed nor embedded in the audit; raw hashes survive.
    """
    tolerance = _limit(atol, "observation tolerance")
    rgb_enabled, rgb_max_abs_error, rgb_max_changed_fraction = _observation_settings(
        observation_profile, rgb_max_abs_error, rgb_max_changed_fraction)
    v6 = observation_profile == V6_PROFILE
    if type(require_non_rgb_exact) is not bool:
        raise ValueError("require_non_rgb_exact must be a boolean")
    rgb_eligible = rgb_enabled and refresh_state_unchanged is True
    image_diagnostics = {}
    mismatches: list[str] = []
    errors: list[str] = []
    max_error = 0.0
    digests = [hashlib.sha256(), hashlib.sha256()]
    non_rgb_digests = [hashlib.sha256(), hashlib.sha256()]
    non_rgb_exact = True

    def walk(left: Any, right: Any, path: str) -> None:
        nonlocal max_error, non_rgb_exact
        if isinstance(left, dict) or isinstance(right, dict):
            if not isinstance(left, dict) or not isinstance(right, dict) or not left or not right:
                mismatches.append(path)
                errors.append(f"{path}: observation dictionaries must be nonempty and match")
                return
            if any(not isinstance(key, str) for key in [*left, *right]):
                mismatches.append(path)
                errors.append(f"{path}: observation keys must be strings")
                return
            if left.keys() != right.keys():
                mismatches.append(path)
                errors.append(f"{path}: observation keys differ")
            for key in sorted(left.keys() & right.keys()):
                walk(left[key], right[key], f"{path}.{key}")
            return
        try:
            arrays = [np.asarray(left), np.asarray(right)]
            if any(not x.size or x.dtype.kind not in "fiu" or not np.isfinite(x).all() for x in arrays):
                raise ValueError("channels must contain finite real numbers")
            for digest, array in zip(digests, arrays):
                digest.update(path.encode("utf-8"))
                digest.update(str(array.shape).encode("ascii"))
                digest.update(np.asarray(array, dtype="<f8").tobytes())
            if arrays[0].shape != arrays[1].shape:
                raise ValueError("channel shapes differ")
            difference = float(np.max(np.abs(arrays[0].astype(float) - arrays[1].astype(float))))
            max_error = max(max_error, difference)
            channel_tolerance = 0.0 if any(x.dtype.kind in "iu" for x in arrays) else tolerance
            named_camera = path.startswith("observation.images.") or path in (
                "observation.agentview_image", "observation.robot0_eye_in_hand_image")
            rgb_channel = (named_camera and all(x.dtype == np.uint8 and x.ndim == 3
                                                and x.shape[-1] == 3 for x in arrays))
            if v6 and named_camera and not rgb_channel:
                raise ValueError("v6 named camera must match uint8 HxWx3 dtype and shape")
            if not rgb_channel:
                same_bytes = (arrays[0].dtype == arrays[1].dtype
                              and arrays[0].tobytes(order="C") == arrays[1].tobytes(order="C"))
                non_rgb_exact = non_rgb_exact and same_bytes
                for digest, array in zip(non_rgb_digests, arrays):
                    digest.update(path.encode("utf-8"))
                    digest.update(str(array.shape).encode("ascii"))
                    digest.update(array.dtype.str.encode("ascii"))
                    digest.update(array.tobytes(order="C"))
                if require_non_rgb_exact and not same_bytes:
                    mismatches.append(path)
            allowance_used = False
            if rgb_channel:
                changed_pixels = int(np.count_nonzero(np.any(arrays[0] != arrays[1], axis=-1)))
                total_pixels = int(arrays[0].shape[0] * arrays[0].shape[1])
                pixel_cap = None if v6 else max(1, int(np.floor(total_pixels * rgb_max_changed_fraction))) if rgb_enabled else 0
                allowance_used = bool(rgb_eligible and 0 < changed_pixels and (v6 or changed_pixels <= pixel_cap)
                                      and difference <= rgb_max_abs_error)
                image_diagnostics[path] = {"bit_exact": changed_pixels == 0,
                                           "changed_pixels": changed_pixels,
                                           "total_pixels": total_pixels,
                                           "changed_fraction": changed_pixels / total_pixels,
                                           "max_changed_pixels": pixel_cap,
                                           "max_changed_fraction": rgb_max_changed_fraction,
                                           "max_abs_error": int(difference),
                                           "bounded_allowance_used": allowance_used}
                if v6:
                    image_diagnostics[path].update(shape=list(arrays[0].shape), dtype=str(arrays[0].dtype),
                        returned_sha256=hashlib.sha256(arrays[0].tobytes(order="C")).hexdigest(),
                        fresh_sha256=hashlib.sha256(arrays[1].tobytes(order="C")).hexdigest())
            if difference > channel_tolerance and not allowance_used:
                mismatches.append(path)
        except (TypeError, ValueError, OverflowError) as exc:
            non_rgb_exact = False
            mismatches.append(path)
            errors.append(f"{path}: {exc}")

    if not isinstance(observation, dict) or not isinstance(fresh_observation, dict):
        return {"matches": False, "max_abs_error": None,
                "mismatched_fields": ["observation"], "errors": ["observations must be dictionaries"],
                "returned_sha256": None, "fresh_sha256": None,
                "returned_non_rgb_sha256": None, "fresh_non_rgb_sha256": None,
                "non_rgb_bit_exact": False,
                "bit_exact": False, "image_diagnostics": {}, "bounded_allowance_used": False,
                "rgb_allowance_state_verified": rgb_eligible}
    walk(observation, fresh_observation, "observation")
    if v6 and (not rgb_eligible or not image_diagnostics):
        mismatches.append("observation")
        errors.append("v6 requires known unchanged refresh state and named uint8 RGB cameras")
    result = {
        "matches": not mismatches,
        "max_abs_error": max_error,
        "mismatched_fields": sorted(set(mismatches)),
        "errors": errors,
        "returned_sha256": digests[0].hexdigest(),
        "fresh_sha256": digests[1].hexdigest(),
        "returned_non_rgb_sha256": non_rgb_digests[0].hexdigest(),
        "fresh_non_rgb_sha256": non_rgb_digests[1].hexdigest(),
        "non_rgb_bit_exact": not errors and non_rgb_exact,
        "bit_exact": not errors and digests[0].hexdigest() == digests[1].hexdigest(),
        "image_diagnostics": image_diagnostics,
        "bounded_allowance_used": any(item["bounded_allowance_used"] for item in image_diagnostics.values()),
        "rgb_allowance_state_verified": rgb_eligible,
    }
    if observation_profile is not None:
        result["observation_profile"] = observation_profile
    return result


def _contact_pairs(pairs) -> set[tuple[str, str]]:
    output = set()
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(x, str) or not x for x in pair)):
            raise ValueError("ignored_contact_pairs must contain pairs of geometry names")
        output.add(tuple(sorted(pair)))
    return output


def _snapshot(snapshot: dict, initial_mask: list[bool], ignored_pairs: set[tuple[str, str]], semantics=None) -> dict:
    if not isinstance(snapshot, dict):
        raise ValueError("validation_snapshot must return a dictionary")
    goals = snapshot.get("goals")
    if (not isinstance(goals, list) or len(goals) != len(initial_mask)
            or any(type(bit) is not bool for bit in goals)):
        raise ValueError("snapshot.goals must contain one boolean per initial goal")
    state = _vector(snapshot.get("state"), "snapshot.state")
    qvel = _vector(snapshot.get("qvel"), "snapshot.qvel")
    robot = _vector(snapshot.get("robot_qpos"), "snapshot.robot_qpos")
    positions = snapshot.get("object_positions")
    if not isinstance(positions, dict) or not positions:
        raise ValueError("snapshot.object_positions must identify monitored objects/fixtures")
    parsed_positions = {}
    for name, position in positions.items():
        if not isinstance(name, str) or not name:
            raise ValueError("object_positions keys must be nonempty names")
        parsed_positions[name] = _vector(position, f"object_positions.{name}", 3)
    penetrations = snapshot.get("penetrations")
    if not isinstance(penetrations, list):
        raise ValueError("snapshot.penetrations must be an explicit list, including when empty")
    contacts = []
    for contact in penetrations:
        if not isinstance(contact, dict):
            raise ValueError("each penetration must be a dictionary")
        pair = (contact.get("geom1"), contact.get("geom2"))
        if any(not isinstance(x, str) or not x for x in pair):
            raise ValueError("penetrations require geom1 and geom2 names")
        contacts.append({
            "geom1": pair[0], "geom2": pair[1],
            "depth": _limit(contact.get("depth"), "penetration depth"),
            "ignored": tuple(sorted(pair)) in ignored_pairs,
        })
    if "fresh_observation" not in snapshot:
        raise ValueError("snapshot requires an independently refreshed fresh_observation")
    refresh_unchanged = None
    if "state_before_refresh" in snapshot:
        before = _vector(snapshot["state_before_refresh"], "snapshot.state_before_refresh")
        refresh_unchanged = before.shape == state.shape and bool(np.array_equal(before.view(np.uint64), state.view(np.uint64)))
    extra = {}
    if semantics is not None:
        from .nine_catalog import validate_goal_facts, FACT_FIELDS
        validate_goal_facts(snapshot, semantics)
        extra = {field: deepcopy(snapshot[field]) for field in FACT_FIELDS if field != "goals"}
    return {
        "state": state, "qvel": qvel, "robot_qpos": robot,
        "goals": list(goals), "object_positions": parsed_positions,
        "penetrations": contacts, "fresh_observation": snapshot["fresh_observation"],
        "refresh_state_unchanged": refresh_unchanged,
        **extra,
    }


def validate_candidate(
    env: Any,
    episode: dict,
    *,
    steps: int = 150,
    hold_action,
    position_tolerance: float = 0.005,
    velocity_tolerance: float = 0.01,
    robot_position_tolerance: float = 0.002,
    penetration_tolerance: float = 0.002,
    observation_tolerance: float = 1e-8,
    rgb_max_abs_error: int = 0,
    rgb_max_changed_fraction: float = 0.0,
    observation_profile: str | None = None,
    stability_profile: str | None = None,
    ignored_contact_pairs=(),
) -> dict:
    """Restore a candidate and audit an explicit constant 7D hold controller.

    Wrapper protocol (independent of manifest ``construction.legal``):
      - ``restore_candidate(episode) -> observation`` restores the unapproved
        candidate without advancing physics; it may reset controller caches.
      - ``step(action) -> observation`` advances exactly one environment step.
      - ``validation_snapshot() -> dict`` returns goals (list[bool]), finite
        state/qvel/robot_qpos vectors, object_positions (name -> world xyz),
        penetrations (geom1/geom2/positive depth), and fresh_observation from
        an independent forced, non-stepping refresh. If available, supply
        state_before_refresh to independently assert no physical state change.

    The wrapper is responsible for monitoring all task-relevant bodies and
    extracting actual contact depths, normally max(0, -contact.dist). Explicit
    ignored geometry pairs may represent permanent base/support contacts;
    their raw depths remain recorded. No contacts are implicitly ignored.

    Object displacement uses Euclidean metres relative to step 0. qvel and
    robot_qpos limits use maximum absolute component values in native joint
    units (metres or radians); they need task-specific calibration. Robot
    drift is measured against step 0 and, if provided, the episode field
    reference_robot_qpos. Without that reference, cross-mask equality is
    unverified. To repair a settled pose, the driver must create a new
    candidate, restore the base pose, and repeat this complete validation;
    this function never repairs or silently settles a candidate.

    Returned JSON-safe audit contains technical_acceptance, initial static
    checks, dynamic stability, checks, declared limits and the full numeric
    validation trace (images represented by hashes). No legal=True is set.
    goals must equal initial_mask throughout. Physics time may advance;
    flattened state equality across ordinary steps is not required.
    steps=0 performs only static checks: dynamic_stability is None.

    Invalid arguments raise ValueError. Restoration/snapshot/step failures
    yield technical_acceptance=False with an error and partial trace. They
    are not silently accepted or conflated with ordinary predicate failure.
    No policy is called and no model outcome participates in candidate selection.
    """
    if type(steps) is not int or steps < 0:
        raise ValueError("steps must be a nonnegative integer")
    if not isinstance(episode, dict):
        raise ValueError("episode must be a dictionary")
    stability_binding = None
    if stability_profile is not None:
        from . import stability
        if stability_profile != stability.PROFILE:
            raise ValueError("unsupported stability profile")
        stability_binding = stability.validate_scope(episode)
        if (observation_profile != episode["observation_profile"] or steps not in (0, 150)
                or (position_tolerance, velocity_tolerance, robot_position_tolerance,
                    penetration_tolerance, observation_tolerance) != (.005, .01, .002, .002, 1e-8)
                or list(hold_action) != [0., 0., 0., 0., 0., 0., -1.] or ignored_contact_pairs):
            raise ValueError("R7 requires frozen physical/observation/hold rules and 150 steps (or static zero precheck)")
    elif episode.get("stability_profile") is not None or "stability_binding" in episode:
        raise ValueError("episode stability metadata requires an explicit supported stability profile")
    initial_mask = episode.get("initial_mask")
    if not isinstance(initial_mask, list) or not initial_mask or any(type(x) is not bool for x in initial_mask):
        raise ValueError("episode.initial_mask must be a nonempty list of booleans")
    action = _vector(hold_action, "hold_action", 7)
    ignored_pairs = _contact_pairs(ignored_contact_pairs)
    rgb_enabled, rgb_max_abs_error, rgb_max_changed_fraction = _observation_settings(
        observation_profile, rgb_max_abs_error, rgb_max_changed_fraction)
    profile_config = observation_profile_config(observation_profile)
    limits = {
        "position_tolerance": _limit(position_tolerance, "position_tolerance"),
        "velocity_tolerance": _limit(velocity_tolerance, "velocity_tolerance"),
        "robot_position_tolerance": _limit(robot_position_tolerance, "robot_position_tolerance"),
        "penetration_tolerance": _limit(penetration_tolerance, "penetration_tolerance"),
        "observation_tolerance": _limit(observation_tolerance, "observation_tolerance"),
        "rgb_max_abs_error": rgb_max_abs_error,
        "rgb_max_changed_fraction": rgb_max_changed_fraction,
    }
    reference = None
    if "reference_robot_qpos" in episode:
        reference = _vector(episode["reference_robot_qpos"], "reference_robot_qpos")
    audit = {
        "schema_version": "remaining-goals-validation-v1",
        "episode_id": episode.get("episode_id"),
        "technical_acceptance": False,
        "static_acceptance": False,
        "dynamic_stability": None,
        "requested_steps": steps, "completed_steps": 0,
        "initial_mask": list(initial_mask), "hold_action": action.tolist(),
        "limits": limits,
        "observation_audit_rule": profile_config["rule"] if rgb_enabled else None,
        "ignored_contact_pairs": [list(pair) for pair in sorted(ignored_pairs)],
        "reference_robot_qpos": reference.tolist() if reference is not None else None,
        "cross_mask_pose_checked": reference is not None,
        "refresh_nonstepping_checked": False,
        "checks": {}, "trace": [], "error": None,
        "limitations": [
            "Technical acceptance is not a declaration of physical/legal feasibility.",
            "One hold controller's stability does not prove remaining-task executability.",
            "Observation freshness relies on the adapter using an independent forced refresh.",
            "Monitored world positions do not fully characterize object orientation, force, or reachability.",
        ],
    }
    if observation_profile is not None:
        audit["observation_profile"] = observation_profile
    stability_samples = []
    if stability_binding is not None:
        audit.update(schema_version=stability.AUDIT_SCHEMA, stability_profile=stability_profile,
                     stability_binding=deepcopy(stability_binding), stability_window=None)
        audit["limitations"].append(
            "R7 is a post hoc source-preparation measurement revision: A instantaneous generalized velocity is diagnostic; "
            "a complete 150-control-step/151-observation pose window is required. CPU doubles do not prove physics.")
    semantics = episode.get("task_semantics")
    if semantics is not None:
        from .nine_catalog import validate_episode_semantics
        semantics = validate_episode_semantics(episode)
        audit["task_semantics"] = deepcopy(semantics)
    if rgb_enabled:
        audit["limitations"].append(profile_config["limitation"])
    phase = "restore_candidate"
    try:
        returned = deepcopy(env.restore_candidate(deepcopy(episode)))
        first = None
        for step in range(steps + 1):
            if step:
                phase = "step"
                returned = deepcopy(env.step(action.copy()))
                audit["completed_steps"] = step
            phase = "validation_snapshot"
            raw_snapshot = env.validation_snapshot()
            snapshot = _snapshot(raw_snapshot, initial_mask, ignored_pairs, semantics)
            stability_sample = stability_window = None
            if stability_binding is not None:
                live_binding = stability.validate_binding(raw_snapshot.get("stability_binding"), episode["model_xml_sha256"])
                if live_binding != stability_binding:
                    raise ValueError("live compiled-model stability binding differs from the episode")
                stability_sample = stability.sample(snapshot["state"], snapshot["qvel"], stability_binding)
                active_position = snapshot["object_positions"].get(stability.OBJECT)
                if active_position is None or not np.array_equal(
                        active_position.view(np.uint64),
                        np.array(stability_sample["active_pose_wxyz"][:3], dtype=np.float64).view(np.uint64)):
                    raise ValueError("monitored A position differs from the bound raw-state pose")
                stability_samples.append(stability_sample)
                stability_window = stability.pose_window(stability_samples)
                audit["stability_window"] = deepcopy(stability_window)
            if first is None:
                first = snapshot
                if reference is not None and reference.shape != first["robot_qpos"].shape:
                    raise ValueError("reference_robot_qpos shape does not match robot state")
            if snapshot["robot_qpos"].shape != first["robot_qpos"].shape:
                raise ValueError("robot_qpos shape changed during validation")
            if snapshot["state"].shape != first["state"].shape or snapshot["qvel"].shape != first["qvel"].shape:
                raise ValueError("state/velocity layout changed during validation")
            if snapshot["object_positions"].keys() != first["object_positions"].keys():
                raise ValueError("monitored object set changed during validation")
            drift = {name: float(np.linalg.norm(position - first["object_positions"][name]))
                     for name, position in snapshot["object_positions"].items()}
            robot_drift = float(np.max(np.abs(snapshot["robot_qpos"] - first["robot_qpos"])))
            reference_error = float(np.max(np.abs(snapshot["robot_qpos"] - reference))) if reference is not None else None
            max_velocity = float(np.max(np.abs(snapshot["qvel"])))
            contacts = snapshot["penetrations"]
            raw_penetration = max((c["depth"] for c in contacts), default=0.0)
            checked_penetration = max((c["depth"] for c in contacts if not c["ignored"]), default=0.0)
            observation_check = compare_observations(
                returned, snapshot["fresh_observation"], atol=limits["observation_tolerance"] if step else 0.0,
                require_non_rgb_exact=step == 0,
                rgb_max_abs_error=rgb_max_abs_error,
                rgb_max_changed_fraction=rgb_max_changed_fraction,
                observation_profile=observation_profile,
                refresh_state_unchanged=snapshot["refresh_state_unchanged"])
            checks = {
                "finite_state_and_velocity": True,
                "predicate_mask_matches": snapshot["goals"] == initial_mask,
                "object_positions_stable": max(drift.values()) <= limits["position_tolerance"],
                "velocities_below_limit": (stability_sample["max_abs_non_active_velocity"]
                    if stability_sample is not None else max_velocity) <= limits["velocity_tolerance"],
                "robot_pose_stable": robot_drift <= limits["robot_position_tolerance"],
                "reference_robot_pose_matches": reference_error <= limits["robot_position_tolerance"] if reference_error is not None else None,
                "contact_penetration_within_limit": checked_penetration <= limits["penetration_tolerance"],
                "observation_matches_fresh": observation_check["matches"],
                "initial_non_rgb_bit_exact": observation_check["non_rgb_bit_exact"] if step == 0 else True,
                "refresh_did_not_step": snapshot["refresh_state_unchanged"],
            }
            if rgb_enabled:
                checks["rgb_allowance_state_verified"] = snapshot["refresh_state_unchanged"] is True
            if semantics is not None:
                from .nine_catalog import initial_constraints_match
                checks["initial_constraints_match"] = initial_constraints_match(snapshot)
            if stability_sample is not None:
                checks.update(active_pose_stable=stability_window["stable"], stability_binding_matches=True)
            row = {
                "step": step, "goals": snapshot["goals"],
                "action": None if step == 0 else action.tolist(),
                "state": snapshot["state"].tolist(), "state_sha256": _array_hash(snapshot["state"]),
                "qvel": snapshot["qvel"].tolist(), "robot_qpos": snapshot["robot_qpos"].tolist(),
                "object_positions": {name: value.tolist() for name, value in snapshot["object_positions"].items()},
                "object_position_drift": drift, "max_abs_velocity": max_velocity,
                "max_abs_robot_drift": robot_drift, "max_abs_reference_robot_error": reference_error,
                "max_raw_penetration": raw_penetration, "max_checked_penetration": checked_penetration,
                "penetrations": contacts, "observation_check": observation_check,
                "checks": checks,
            }
            audit["trace"].append(row)
            if stability_sample is not None:
                row.update(stability_sample=stability_sample, stability_window=stability_window)
            if semantics is not None:
                from .nine_catalog import FACT_FIELDS
                row.update({field: deepcopy(snapshot[field]) for field in FACT_FIELDS})
            if step == 0:
                audit["static_acceptance"] = all(value is not False for value in checks.values())
    except Exception as exc:
        audit["error"] = {"phase": phase, "type": type(exc).__name__, "message": str(exc)}

    complete = len(audit["trace"]) == steps + 1 and audit["error"] is None
    names = set().union(*(row["checks"] for row in audit["trace"]))
    for name in sorted(names):
        values = [row["checks"][name] for row in audit["trace"]]
        # Do not turn successful checks on a truncated prefix into a statement
        # that the entire requested validation window passed.
        audit["checks"][name] = False if False in values else (True if complete and all(value is not None for value in values) else None)
    audit["checks"]["validation_window_complete"] = complete
    audit["checks"]["snapshot_contract_valid"] = audit["error"] is None
    if stability_binding is not None:
        audit["checks"]["formal_stability_window_complete"] = complete and steps == 150 and len(audit["trace"]) == 151
    audit["refresh_nonstepping_checked"] = complete and audit["checks"].get("refresh_did_not_step") is not None
    if steps:
        audit["dynamic_stability"] = complete and all(
            value is not False for row in audit["trace"] for value in row["checks"].values()
        )
    audit["technical_acceptance"] = complete and all(value is not False for value in audit["checks"].values())
    return audit
