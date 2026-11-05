"""Explicit decision-relevant calibration and same-trajectory sensitivity.

No simulator, policy, head or new labels are created. None substitutions below
bound an offline timing reference only; they never overwrite physical truth.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .data import canonical_hash
from .calibration import THRESHOLDS, _truth, _first_stable
from .evaluation import CALIBRATION_SCHEMA_V3, RELEASE_V1, CALIBRATION_LEGACY, CALIBRATION_V2

CALIBRATION_SCHEMA = CALIBRATION_SCHEMA_V3
SENSITIVITY_SCHEMA = "remaining-finish-calibration-sensitivity-v1"
LEGACY_METHOD = RELEASE_V1
LEGACY_RULE = CALIBRATION_LEGACY
NEW_RULE = CALIBRATION_V2


def tau_bounds(truth, horizon, confirmation_steps=4):
    """Monotonic bounds on the first K-interval stable start within H.

    Making only unknown states True cannot delay the earliest stable start;
    making them False cannot advance it. Known False/True remain untouched.
    A missing upper endpoint means at least one completion has no reference.
    """
    if (not isinstance(truth, list) or not truth or any(value is not None and type(value) is not bool for value in truth)
            or type(horizon) is not int or horizon < 0 or horizon >= len(truth)
            or type(confirmation_steps) is not int or confirmation_steps < 1):
        raise ValueError("invalid three-state timing sequence or window")
    low = _first_stable([True if value is None else value for value in truth], horizon, confirmation_steps)
    high = _first_stable([False if value is None else value for value in truth], horizon, confirmation_steps)
    return {"tau_low": low, "tau_high": high,
            "completion_unknown_steps": [step for step, value in enumerate(truth) if value is None],
            "confirmation_steps": confirmation_steps,
            "reference_convention": "K intervals / K+1 states; start <= H; unknown substitution is not a physical label"}


def first_hit_timing(truth, queries, threshold, horizon, *, timely_steps=24, confirmation_steps=4):
    """Return one first-hit decision plus conservative interval timing evidence."""
    bounds = tau_bounds(truth, horizon, confirmation_steps)
    if (type(timely_steps) is not int or timely_steps < 0 or type(threshold) not in (int, float)
            or not math.isfinite(threshold) or not 0 < threshold <= 1 or not isinstance(queries, list)):
        raise ValueError("invalid first-hit timing arguments")
    previous = -1
    for query in queries:
        step, probability = query.get("observation_step"), query.get("p")
        if (type(step) is not int or not previous < step <= horizon
                or type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1):
            raise ValueError("invalid ordered first-hit query")
        previous = step
    first = next((query for query in queries if query["p"] >= threshold), None)
    step = None if first is None else first["observation_step"]
    current = None if step is None else truth[step]
    low, high = bounds["tau_low"], bounds["tau_high"]
    result = {**bounds, "first_crossing_step": step, "current_state_correct": current,
              "delay_steps_interval": None, "timing_unknown": False, "timely": False}
    if first is None:
        result.update(first_hit_status="not_triggered", timing_reason="not_triggered")
    elif current is False:
        result.update(first_hit_status="premature", timing_reason="known_false_at_first_hit")
    elif current is None:
        result.update(first_hit_status="unknown_first_hit", timely=None, timing_reason="unknown_current_truth_at_first_hit")
    else:
        result["first_hit_status"] = "correct"
        result["delay_steps_interval"] = {"minimum": None if high is None else step - high,
                                          "maximum": None if low is None else step - low}
        if low is None and high is None:
            result["timing_reason"] = "no_stable_reference_under_either_completion"
        elif low is None or high is None:
            # Conservatively reject the candidate: a no-reference completion
            # cannot be erased by selecting the favorable finite endpoint.
            result.update(timely=None, timing_unknown=True, timing_reason="one_completion_has_no_stable_reference")
        elif high <= step <= low + timely_steps:
            result.update(timely=True, timing_reason="all_reference_times_are_timely")
        elif step < low or step > high + timely_steps:
            result["timing_reason"] = "reference_interval_excludes_timely_window"
        else:
            result.update(timely=None, timing_unknown=True, timing_reason="timeliness_depends_on_unknown_completion")
    return result


def _contract(value):
    from .evaluation import validate_evaluation_contract
    return validate_evaluation_contract(value)


def _population(episodes, results, *, source_registry, split_identity, expected_validation_sources):
    from .data_registry import (validate_source_registry, validate_source_identity,
                                source_identity, registry_members)
    from .data_profiles import EVAL_DOMAIN
    if not isinstance(episodes, list) or not isinstance(results, list) or len(episodes) != 5:
        raise ValueError("v2 calibration requires the fixed five expected episodes")
    if source_registry is None or split_identity is None:
        raise ValueError("v2 calibration requires the actual two-domain registry and frozen source identity")
    validate_source_registry(source_registry, verify_files=False)
    validate_source_identity(split_identity)
    if split_identity != source_identity(source_registry):
        raise ValueError("calibration registry differs from frozen source identity")
    members = registry_members(source_registry, EVAL_DOMAIN, "normal_calibration")
    indices = [member["initial_state_index"] for member in members]
    if indices != list(range(35, 40)) or (expected_validation_sources is not None and list(expected_validation_sources) != indices):
        raise ValueError("new calibration is restricted to the fixed official-init 35..39 sources")
    expected = {}
    for episode in episodes:
        name = episode.get("episode_id")
        member = episode.get("eval_source")
        if (not isinstance(name, str) or not name or name in expected or not isinstance(member, dict)
                or member not in members or type(episode.get("initial_state_index")) is not int
                or episode["initial_state_index"] != member["initial_state_index"]
                or "source_index" in episode or "split" in episode):
            raise ValueError("invalid official-init normal_calibration episode identity")
        if episode.get("edited_variant", False) or episode.get("instruction_mode", "original") != "original":
            raise ValueError("edited/oracle data cannot calibrate thresholds")
        expected[name] = episode
    if sorted(episode["initial_state_index"] for episode in episodes) != indices:
        raise ValueError("expected calibration episodes must cover each fixed source once")
    indexed = {}
    for result in results:
        if not isinstance(result, dict) or result.get("episode_id") not in expected or result["episode_id"] in indexed:
            raise ValueError("duplicate or unknown calibration result")
        indexed[result["episode_id"]] = result
    heads = {canonical_hash(query.get("head_identity")) for result in results if result.get("status") == "completed"
             for query in result.get("queries", [])}
    if len(heads) > 1:
        raise ValueError("calibration cannot pool different head/base artifacts")
    return expected, indexed, members, heads


def _inspect(result, contract, method):
    from .schema import validate_finish_result
    if (result.get("schema_version") != "remaining-finish-episode-v2" or result.get("protocol_version") != "remaining-finish-v1"
            or result.get("evaluation_contract") != contract or result.get("mode") != "shadow"
            or result.get("sensitivity_only", False)):
        raise ValueError("new calibration needs original v2 shadow results with the same evaluation contract")
    validate_finish_result(result)
    horizon, retention = result["configuration"]["horizon"], result["configuration"]["retention_steps"]
    trace = result["trace"]
    if len(trace) != horizon + retention + 1 or [row["step"] for row in trace] != list(range(len(trace))):
        raise ValueError("calibration requires the complete physical evidence window")
    if result.get("finish_step") is not None or result.get("timeout_step") != horizon:
        raise ValueError("calibration shadow must end at its budget timeout")
    truth = []
    for frame in trace:
        if method == "legacy":
            measurement = frame.get("measurement")
            if (not isinstance(measurement, dict) or measurement.get("schema_version") != "remaining-finish-dual-measurement-v1"
                    or measurement.get("contract_sha256") != contract["contract_sha256"]
                    or not isinstance(measurement.get("legacy"), dict)):
                raise ValueError("legacy sensitivity evidence is missing or belongs to another contract")
            chosen = measurement["legacy"]
        else:
            chosen = frame
        truth.append(_truth(chosen))
        if len(chosen["goals"]) != len(trace[0]["goals"]):
            raise ValueError("measurement goal dimensions changed")
    if any(trace[0]["goals"]):
        raise ValueError("calibration needs normal00 initial states")
    queries = result["queries"]
    if not queries or queries[0]["observation_step"] != 0 or queries[-1]["observation_step"] != horizon:
        raise ValueError("calibration queries must include initial and deadline observations")
    for query in queries:
        if query["applied_decision"] != ("timeout" if query["observation_step"] == horizon else "continue"):
            raise ValueError("shadow cannot apply model FINISH")
    return truth, queries, horizon


def _prepare(expected, indexed, contract, method):
    prepared, issues, unknown_coverage = {}, [], []
    errors = missing = 0
    for name, episode in expected.items():
        result = indexed.get(name)
        if result is None:
            missing += 1
            issues.append({"episode_id": name, "reason": "missing"})
            continue
        if result.get("status") != "completed":
            errors += 1
            issues.append({"episode_id": name, "reason": "technical_error", "status": result.get("status")})
            continue
        try:
            for key in ("initial_state_index", "eval_source", "state_sha256"):
                if key in result and key in episode and (type(result[key]) is not type(episode[key]) or result[key] != episode[key]):
                    raise ValueError("result source identity conflicts with the expected episode")
            truth, queries, horizon = _inspect(result, contract, method)
            prepared[name] = (truth, queries, horizon)
            frames = [frame["measurement"]["legacy"] if method == "legacy" else frame for frame in result["trace"]]
            unknown_coverage.append({"episode_id": name, "unknown_frames": sum(value is None for value in truth),
                                     "unknown_steps": [step for step, value in enumerate(truth) if value is None],
                                     "release_unknown_steps": [step for step, frame in enumerate(frames) if frame["released"] is None],
                                     "object_release_unknown_steps": {name: [step for step, frame in enumerate(frames)
                                         if frame["objects"][name]["released"] is None] for name in frames[0]["objects"]},
                                     "observed_frames": len(truth)})
        except (ValueError, TypeError, KeyError, IndexError) as error:
            errors += 1
            issues.append({"episode_id": name, "reason": "invalid_evidence", "message": str(error)})
    return prepared, issues, unknown_coverage, errors, missing


def _search(prepared, expected_count, *, rule, technical_issues, unknown_coverage):
    candidates = []
    for threshold in THRESHOLDS:
        counts = {"premature": 0, "correct": 0, "timely": 0, "robust_timely": 0, "not_triggered": 0,
                  "unknown_first_hit": 0, "timing_unknown": 0, "without_stable_reference": 0}
        details = []
        for name, (truth, queries, horizon) in prepared.items():
            if rule == NEW_RULE:
                detail = first_hit_timing(truth, queries, threshold, horizon)
                counts["timing_unknown"] += int(detail["timing_unknown"])
                counts["without_stable_reference"] += int(detail["tau_high"] is None)
            else:
                tau = _first_stable(truth, horizon, 4)
                first = next((query for query in queries if query["p"] >= threshold), None)
                step = first["observation_step"] if first else None
                current = truth[step] if first else None
                timely = current is True and tau is not None and 0 <= step - tau <= 24
                status = "not_triggered" if first is None else "unknown_first_hit" if current is None else "premature" if current is False else "correct"
                detail = {"first_crossing_step": step, "current_state_correct": current, "tau": tau,
                          "first_hit_status": status, "timely": timely,
                          "delay_steps": step - tau if current is True and tau is not None else None}
                counts["without_stable_reference"] += int(tau is None)
            counts[detail["first_hit_status"]] += 1
            counts["timely"] += int(detail["timely"] is True)
            counts["robust_timely"] += int(detail["timely"] is True and rule == NEW_RULE)
            details.append({"episode_id": name, **detail})
        feasible = counts["premature"] == counts["unknown_first_hit"] == counts["timing_unknown"] == 0
        candidates.append({"threshold": threshold, **counts, "expected": expected_count,
                           "timely_rate": counts["timely"] / expected_count, "decision_feasible": feasible,
                           "episodes": details})
    feasible = [item for item in candidates if item["decision_feasible"]]
    chosen = max(feasible, key=lambda item: (item["timely"], item["threshold"])) if feasible else None
    unknown = sum(row["unknown_frames"] > 0 for row in unknown_coverage)
    valid = not technical_issues and (rule == NEW_RULE or unknown == 0)
    useful = chosen is not None and chosen["timely"] > 0
    calibrated = bool(valid and useful)
    return {"candidates": candidates, "validation_evidence_valid": valid, "calibrated": calibrated,
            "selected_threshold": chosen["threshold"] if calibrated else None,
            "best_candidate_threshold": chosen["threshold"] if chosen else None,
            "status": "candidate_threshold_frozen" if calibrated else "capability_not_established",
            "reason": "independent_normal_active_test_required" if calibrated else
                      "validation_evidence_incomplete_or_unknown" if not valid else
                      "no_timely_finish" if chosen else "no_zero_premature_unknown_timing_candidate"}


def _report(episodes, results, *, evaluation_contract, source_registry, split_identity,
            expected_validation_sources=None, method="current", rule=NEW_RULE, sensitivity=False):
    contract = _contract(evaluation_contract)
    expected, indexed, members, heads = _population(episodes, results, source_registry=source_registry,
        split_identity=split_identity, expected_validation_sources=expected_validation_sources)
    prepared, issues, unknown, errors, missing = _prepare(expected, indexed, contract, method)
    search = _search(prepared, len(expected), rule=rule, technical_issues=issues, unknown_coverage=unknown)
    result = {"schema_version": CALIBRATION_SCHEMA, **search, "evaluation_contract": deepcopy(contract),
              "release_method": LEGACY_METHOD if method == "legacy" else contract["release_method"],
              "calibration_rule": rule, "sensitivity_only": sensitivity, "active_eligible": search["calibrated"] and not sensitivity,
              "expected": len(expected), "completed": len(prepared), "errors": errors, "missing": missing,
              "coverage": len(prepared) / len(expected), "unknown": sum(row["unknown_frames"] > 0 for row in unknown),
              "unknown_coverage": unknown, "issues": issues, "threshold_search_completed": True,
              "candidate_stopping_behavior_observed": search["calibrated"],
              "ordinary_stopping_capability_established": False, "active_validation_required": True,
              "confirmation_steps": 4, "timely_steps": 24, "thresholds": list(THRESHOLDS),
              "validation_source_indices": list(range(35, 40)), "expected_episodes": deepcopy(episodes),
              "source_identity": deepcopy(split_identity), "split_identity": deepcopy(split_identity),
              "calibration_domain": "official_initial_state", "calibration_role": "normal_calibration",
              "calibration_members": deepcopy(members), "calibration_source_keys": [member["source_key"] for member in members],
              "ancestry_independence": "unproven", "head_identity_sha256": next(iter(heads)) if heads else None,
              "source_result_sha256": {name: canonical_hash(value) for name, value in indexed.items()},
              "limitations": ["Post-pilot protocol revision; the new five same-source shadows are calibration development, not independent generalization.",
                              "Unknown substitutions bound timing only; no physical label is imputed.",
                              "Shadow future policy states cannot prove counterfactual FINISH hold stability.",
                              "Independent normal active validation remains required."]}
    if sensitivity:
        result.update(schema_version="remaining-finish-sensitivity-cell-v1", diagnostic_threshold=result["selected_threshold"],
                      would_freeze_threshold=result["calibrated"], calibrated=False, selected_threshold=None,
                      candidate_stopping_behavior_observed=False, status="sensitivity_only" if not issues else "indeterminate")
    result["calibration_sha256"] = canonical_hash(result)
    return result


def calibrate_v2(episodes, results, *, evaluation_contract, thresholds=THRESHOLDS, timely_steps=24,
                 confirmation_steps=4, expected_validation_sources=None, split_identity=None, source_registry=None):
    if list(thresholds) != list(THRESHOLDS) or type(timely_steps) is not int or timely_steps != 24 or type(confirmation_steps) is not int or confirmation_steps != 4:
        raise ValueError("v2 uses the preregistered twenty thresholds, K4 and 24-step timing window")
    return _report(episodes, results, evaluation_contract=evaluation_contract, source_registry=source_registry,
                   split_identity=split_identity, expected_validation_sources=expected_validation_sources)


def sensitivity_table(episodes, results, *, evaluation_contract, source_registry, split_identity):
    """Two methods x two rules on the same new shadows; never active artifacts."""
    contract = _contract(evaluation_contract)
    cells = []
    for method in ("legacy", "current"):
        for rule in (LEGACY_RULE, NEW_RULE):
            cells.append(_report(episodes, results, evaluation_contract=contract, source_registry=source_registry,
                                 split_identity=split_identity, method=method, rule=rule, sensitivity=True))
    report = {"schema_version": SENSITIVITY_SCHEMA, "sensitivity_only": True, "active_eligible": False,
              "calibrated": False, "selected_threshold": None, "evaluation_contract": contract,
              "expected": 5, "thresholds": list(THRESHOLDS), "confirmation_steps": 4, "timely_steps": 24,
              "source_result_sha256": deepcopy(cells[0]["source_result_sha256"]),
              "source_identity": deepcopy(split_identity), "cells": cells,
              "notice": "All cells are derived sensitivity only, including v2+new; formal calibration is a separate artifact. No old pilot v2 truth is fabricated."}
    report["sensitivity_sha256"] = canonical_hash(report)
    return report
