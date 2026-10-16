"""Normal-validation first-crossing threshold search; no environment/model calls.

Shadow trajectories estimate candidate decisions, not counterfactual post-FINISH
physics. A saved threshold is not proof of ordinary active stopping capability.
"""
from __future__ import annotations

import copy
import math

from .data import canonical_hash, validate_split
from .schema import validate_finish_result

THRESHOLDS = tuple([i / 20 for i in range(1, 20)] + [0.99])


def _truth(frame):
    goals, released = frame.get("goals"), frame.get("released")
    if not isinstance(goals, list) or not goals or any(type(value) is not bool for value in goals):
        raise ValueError("calibration needs strict goal truth")
    if released is not None and type(released) is not bool:
        raise ValueError("release evidence must be bool or null")
    if not all(goals) or released is False:
        return False
    return True if released is True else None


def _inspect(result):
    validate_finish_result(result)
    if result.get("schema_version") != "remaining-finish-episode-v1" or result.get("protocol_version") != "remaining-finish-v1":
        raise ValueError("calibration requires finish-v1 episodes")
    if result.get("mode") != "shadow":
        raise ValueError("threshold calibration accepts only normal-validation shadow episodes")
    trace, queries = result.get("trace"), result.get("queries")
    horizon = result.get("configuration", {}).get("horizon")
    if type(horizon) is not int or horizon < 1:
        raise ValueError("invalid calibration horizon")
    retention = result["configuration"].get("retention_steps")
    if type(retention) is not int or retention < 1:
        raise ValueError("invalid calibration retention")
    if (not isinstance(trace, list) or len(trace) != horizon + retention + 1
            or any(not isinstance(frame, dict) or type(frame.get("step")) is not int or frame["step"] != i
                   for i, frame in enumerate(trace))):
        raise ValueError("completed shadow evidence needs the full physical window")
    truth = [_truth(frame) for frame in trace]
    if any(len(frame["goals"]) != len(trace[0]["goals"]) for frame in trace):
        raise ValueError("goal dimensions changed")
    if any(trace[0]["goals"]):
        raise ValueError("calibration accepts only normal00 initial states")
    if not isinstance(queries, list) or not queries:
        raise ValueError("shadow query evidence missing")
    previous = -1
    for index, query in enumerate(queries):
        step, probability = query.get("observation_step"), query.get("p")
        if (type(step) is not int or not previous < step <= horizon or query.get("sequence") != index + 1
                or type(query.get("sequence")) is not int):
            raise ValueError("queries must have unique ordered observation steps")
        if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("invalid finish probability")
        if query.get("applied_decision") != ("timeout" if step == horizon else "continue"):
            raise ValueError("shadow evidence applied a model FINISH")
        previous = step
    if queries[0]["observation_step"] != 0 or queries[-1]["observation_step"] != horizon:
        raise ValueError("shadow queries must cover t0 and the deadline")
    if result.get("finish_step") is not None or result.get("timeout_step") != horizon:
        raise ValueError("shadow did not end with a budget timeout")
    return truth, queries, horizon


def _first_stable(truth, horizon, confirmation_steps):
    # Offline reference only: these future policy frames do not certify an
    # active exit's hold. Candidate correctness is still its current state.
    for step in range(min(horizon + 1, len(truth) - confirmation_steps)):
        if all(value is True for value in truth[step:step + confirmation_steps + 1]):
            return step
    return None


def calibrate_threshold(episodes, results, *, thresholds=THRESHOLDS, timely_steps=24,
                        confirmation_steps=4, expected_validation_sources=None, split_identity=None,
                        source_registry=None, evaluation_contract=None):
    """Search first p>=threshold on a fixed expected normal-validation population.

    With source_registry, each episode explicitly carries its official-init
    eval_source member and initial_state_index; only normal_calibration is
    accepted. HDF head_validation is a separate source domain. Legacy callers
    retain episode_id/source_index/split='validation' and the old split contract.
    Unknown physical truth or incomplete/missing evidence prevents a calibrated
    declaration, even when excluding it would improve the threshold. No timely
    crossing means stopping capability remains unestablished. Active independent
    testing remains required for every threshold, including a good shadow one.
    """
    if evaluation_contract is not None:
        from .calibration_v2 import calibrate_v2
        return calibrate_v2(episodes, results, thresholds=thresholds, timely_steps=timely_steps,
                            confirmation_steps=confirmation_steps, expected_validation_sources=expected_validation_sources,
                            split_identity=split_identity, source_registry=source_registry,
                            evaluation_contract=evaluation_contract)
    if not isinstance(episodes, list) or not episodes or not isinstance(results, list):
        raise ValueError("calibration needs expected episodes and result lists")
    if any(isinstance(result, dict) and (result.get("schema_version") == "remaining-finish-episode-v2"
               or "evaluation_contract" in result) for result in results):
        raise ValueError("v2 calibration results require an explicit matching evaluation_contract")
    if type(timely_steps) is not int or timely_steps < 0 or type(confirmation_steps) is not int or confirmation_steps < 1:
        raise ValueError("invalid calibration timing contract")
    thresholds = list(thresholds)
    if (not thresholds or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 1 for v in thresholds)
            or len(set(thresholds)) != len(thresholds)):
        raise ValueError("threshold candidates must be unique finite probabilities")
    two_domains = source_registry is not None or (isinstance(split_identity, dict)
                   and split_identity.get("schema_version") == "remaining-finish-source-domains-identity-v2")
    members = None
    if two_domains:
        from .data_registry import validate_source_registry, registry_members, source_identity, validate_source_identity
        from .data_profiles import EVAL_DOMAIN
        if source_registry is None or split_identity is None:
            raise ValueError("two-domain calibration requires its registry and frozen source identity")
        validate_source_registry(source_registry, verify_files=False)
        validate_source_identity(split_identity)
        if split_identity != source_identity(source_registry):
            raise ValueError("calibration registry differs from the head's two-domain identity")
        members = registry_members(source_registry, EVAL_DOMAIN, "normal_calibration")
        expected_sources = [item["initial_state_index"] for item in members]
        if expected_validation_sources is not None and list(expected_validation_sources) != expected_sources:
            raise ValueError("calibration must use registered official-init normal_calibration members")
    else:
        expected_sources = list(range(35, 40)) if expected_validation_sources is None else list(expected_validation_sources)
    if not two_domains and split_identity is not None:
        split = validate_split(split_identity.get("split"),
                               alternative_confirmation=split_identity.get("alternative_confirmation"))
        if split_identity.get("sha256") != canonical_hash(split) or expected_sources != split["validation"]:
            raise ValueError("calibration source group differs from the frozen head-data split")
    elif not two_domains and expected_sources != list(range(35, 40)):
        raise ValueError("alternate validation sources require the confirmed frozen split identity")
    if (not expected_sources or any(type(v) is not int or v < 5 for v in expected_sources)
            or len(set(expected_sources)) != len(expected_sources)):
        raise ValueError("invalid validation source ownership")
    expected = {}
    for episode in episodes:
        identity = episode.get("episode_id")
        if not isinstance(identity, str) or not identity or identity in expected:
            raise ValueError("expected episode identities must be unique")
        if two_domains:
            member = episode.get("eval_source")
            if (not isinstance(member, dict) or member not in members
                    or episode.get("initial_state_index") != member["initial_state_index"]
                    or type(episode.get("initial_state_index")) is not int
                    or "source_index" in episode or "split" in episode):
                raise ValueError("calibration source must be a registered official-init normal_calibration member, not a head trajectory")
        elif episode.get("split") != "validation" or type(episode.get("source_index")) is not int:
            raise ValueError("calibration source must be explicitly normal-validation")
        if episode.get("edited_variant", False) or episode.get("instruction_mode", "original") != "original":
            raise ValueError("edited/oracle test data cannot calibrate thresholds")
        expected[identity] = episode
    index_field = "initial_state_index" if two_domains else "source_index"
    if sorted(e[index_field] for e in episodes) != sorted(expected_sources):
        raise ValueError("calibration expected episodes do not match the frozen validation source group")
    indexed = {}
    for result in results:
        if not isinstance(result, dict) or result.get("episode_id") not in expected or result["episode_id"] in indexed:
            raise ValueError("duplicate or unknown calibration result identity")
        indexed[result["episode_id"]] = result
    head_identities = {canonical_hash(query.get("head_identity")) for result in results
                       if result.get("status") == "completed" for query in result.get("queries", [])}
    if len(head_identities) > 1:
        raise ValueError("calibration cannot pool different head/base artifacts")
    prepared, issues, completed, errors, missing, unknown = {}, [], 0, 0, 0, 0
    for identity, episode in expected.items():
        result = indexed.get(identity)
        if result is None:
            missing += 1
            issues.append({"episode_id": identity, "reason": "missing"})
            continue
        if result.get("status") != "completed":
            errors += 1
            issues.append({"episode_id": identity, "reason": "technical_error", "status": result.get("status")})
            continue
        try:
            for key in (("initial_state_index", "eval_source") if two_domains else ("source_index", "split")):
                if key in result and (type(result[key]) is not type(episode[key]) or result[key] != episode[key]):
                    raise ValueError("result source identity conflicts with expected episode")
            truth, queries, horizon = _inspect(result)
            completed += 1
            tau = _first_stable(truth, horizon, confirmation_steps)
            if any(value is None for value in truth):
                unknown += 1
                issues.append({"episode_id": identity, "reason": "unknown_release_truth"})
            prepared[identity] = (truth, queries, tau)
        except (ValueError, TypeError, KeyError) as error:
            errors += 1
            issues.append({"episode_id": identity, "reason": "invalid_evidence", "message": str(error)})
    candidates = []
    for threshold in thresholds:
        counts = {"premature": 0, "correct": 0, "timely": 0, "not_triggered": 0,
                  "unknown_first_hit": 0, "without_stable_reference": 0}
        details = []
        for identity, (truth, queries, tau) in prepared.items():
            first = next((query for query in queries if query["p"] >= threshold), None)
            step = first["observation_step"] if first else None
            correct = truth[step] if step is not None else None
            timely = correct is True and tau is not None and 0 <= step - tau <= timely_steps
            if first is None:
                counts["not_triggered"] += 1
            elif correct is None:
                counts["unknown_first_hit"] += 1
            elif correct is False:
                counts["premature"] += 1
            else:
                counts["correct"] += 1
            counts["timely"] += int(timely)
            counts["without_stable_reference"] += int(tau is None)
            details.append({"episode_id": identity, "first_crossing_step": step, "tau": tau,
                            "current_state_correct": correct, "timely": timely,
                            "delay_steps": step - tau if correct is True and tau is not None else None})
        candidates.append({"threshold": threshold, **counts, "expected": len(expected),
                           "timely_rate": counts["timely"] / len(expected), "episodes": details})
    feasible = [item for item in candidates if item["premature"] == 0 and item["unknown_first_hit"] == 0]
    chosen = max(feasible, key=lambda item: (item["timely"], item["threshold"])) if feasible else None
    evidence_valid = not issues
    useful = chosen is not None and chosen["timely"] > 0
    calibrated = evidence_valid and useful
    report = {"schema_version": "remaining-finish-calibration-v2" if two_domains else "remaining-finish-calibration-v1", "expected": len(expected),
              "completed": completed, "errors": errors, "missing": missing, "unknown": unknown,
              "coverage": completed / len(expected), "threshold_search_completed": True,
              "validation_evidence_valid": evidence_valid, "calibrated": calibrated,
              "candidate_stopping_behavior_observed": calibrated, "ordinary_stopping_capability_established": False,
              "active_validation_required": True, "selected_threshold": chosen["threshold"] if chosen else None,
              "status": "candidate_threshold_frozen" if calibrated else "capability_not_established",
              "reason": ("independent_normal_active_test_required" if calibrated else
                         "validation_evidence_incomplete_or_unknown" if not evidence_valid else
                         "no_timely_finish" if chosen else "no_zero_premature_candidate"),
              "timely_steps": timely_steps, "confirmation_steps": confirmation_steps,
              "validation_source_indices": expected_sources, "expected_episodes": copy.deepcopy(episodes),
              "split_identity": copy.deepcopy(split_identity),
              "source_result_sha256": {key: canonical_hash(value) for key, value in indexed.items()},
              "issues": issues, "candidates": candidates,
              "limitations": ["Shadow future actions do not prove counterfactual post-FINISH hold stability.",
                              "Zero observed premature exits in a small pilot is not a population guarantee.",
                              "A threshold artifact does not establish independent normal active stopping capability."]}
    if two_domains:
        report.update(source_identity=copy.deepcopy(split_identity), calibration_domain=EVAL_DOMAIN,
                      calibration_role="normal_calibration", calibration_members=copy.deepcopy(members),
                      calibration_source_keys=[item["source_key"] for item in members],
                      ancestry_independence="unproven")
        report["limitations"].append("HDF head-validation trajectories and official-init normal-calibration states are distinct source domains; physical ancestry independence is unproven.")
    report["calibration_sha256"] = canonical_hash(report)
    return report
