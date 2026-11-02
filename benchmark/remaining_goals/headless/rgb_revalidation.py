"""Explicit v6 acceptance of bound recorded evidence; never creates native work.

Original audits and failed flags are immutable. This reader validates complete
recorded diagnostics, not fresh pixels that were never stored.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math

import numpy as np

from . import source_acceptance as legacy
from ..validation import (V6_PROFILE, RGB_QUANTIZATION_RULE, observation_profile_config,
                          _vector, _array_hash, _contact_pairs)

SCHEMA = "remaining-source-rgb-recorded-revalidation-v6"
LIMITATION = ("Recorded diagnostics revalidated; no new native steps and no recomputation of unsaved fresh RGB pixels. "
              "Original failed flags, source files and hashes remain unchanged. Not renderer calibration or policy invariance.")


def audit_profile(audit):
    profile = audit.get("observation_profile")
    config = observation_profile_config(profile)
    if audit.get("observation_audit_rule") != config["rule"]:
        raise ValueError("audit profile/rule identity mismatch")
    if any(audit.get("limits", {}).get(k) != v for k, v in config["limits"].items()):
        raise ValueError("audit profile/limits identity mismatch")
    return profile


def comparison(check, *, initial=False, returned_hash=None, reference_hash=None,
               float_tolerance=1e-8, camera_reference=None, profile=None, revalidate=False):
    """Verify original result consistency, then the explicit v6 interpretation."""
    if profile not in (None, RGB_QUANTIZATION_RULE["rule_id"], V6_PROFILE):
        raise ValueError("unknown observation profile")
    if not isinstance(check,dict) or check.get("observation_profile") != profile:
        raise ValueError("comparison observation profile differs from its audit")
    v6 = profile == V6_PROFILE
    if not v6 and not revalidate:
        legacy._passing_observation_comparison(check, initial=initial, returned_hash=returned_hash,
            reference_hash=reference_hash, float_tolerance=float_tolerance, camera_reference=camera_reference)
        return True
    if (not isinstance(check, dict) or check.get("errors") != []
            or check.get("rgb_allowance_state_verified") is not True
            or type(check.get("matches")) is not bool
            or any(not legacy._digest(check.get(k)) for k in ("returned_sha256", "fresh_sha256",
                "returned_non_rgb_sha256", "fresh_non_rgb_sha256"))
            or check.get("bit_exact") is not (check["returned_sha256"] == check["fresh_sha256"])
            or type(check.get("non_rgb_bit_exact")) is not bool
            or check["non_rgb_bit_exact"] != (check["returned_non_rgb_sha256"] == check["fresh_non_rgb_sha256"])
            or initial and check["non_rgb_bit_exact"] is not True
            or returned_hash is not None and check["returned_sha256"] != returned_hash
            or reference_hash is not None and check["fresh_sha256"] != reference_hash
            or v6 and check.get("observation_profile") != V6_PROFILE):
        raise ValueError("observation state/hash/non-RGB/profile binding invalid")
    cameras = check.get("image_diagnostics")
    if not isinstance(cameras, dict) or not cameras:
        raise ValueError("per-camera diagnostics missing")
    if camera_reference is not None and (cameras.keys() != camera_reference.keys() or any(
            cameras[n].get("total_pixels") != camera_reference[n].get("total_pixels") for n in cameras)):
        raise ValueError("camera inventory/geometry differs from initial artifact")
    if v6 and camera_reference is not None:
        for name,item in cameras.items():
            reference=camera_reference[name]
            fields = ("shape","dtype","returned_sha256") if initial else ("shape","dtype")
            if any(k in reference and item.get(k)!=reference[k] for k in fields):
                raise ValueError("camera shape/dtype/returned hash differs from typed initial artifact")
    original_mismatches, allowance, maximum, any_changed = [], False, 0, False
    for name, item in cameras.items():
        if (not isinstance(name, str) or not (name.startswith("observation.images.") or name in (
                "observation.agentview_image", "observation.robot0_eye_in_hand_image"))
                or not isinstance(item, dict)
                or any(type(item.get(k)) is not int for k in ("changed_pixels", "total_pixels", "max_abs_error"))):
            raise ValueError("invalid named camera evidence")
        count, area, error = item["changed_pixels"], item["total_pixels"], item["max_abs_error"]
        cap = None if v6 else max(1, area // 10000)
        original_allowance = 0 < count and error <= 1 and (v6 or count <= cap)
        if (area < 1 or not 0 <= count <= area or not 0 <= error <= 1
                or (count == 0) != (error == 0) or item.get("changed_fraction") != count / area
                or item.get("bit_exact") is not (count == 0)
                or item.get("max_changed_pixels") != cap
                or item.get("max_changed_fraction") != (None if v6 else .0001)
                or item.get("bounded_allowance_used") is not original_allowance):
            raise ValueError("RGB evidence invalid or channel difference exceeds one")
        if v6:
            shape = item.get("shape")
            if (not isinstance(shape, list) or len(shape) != 3 or shape[2] != 3
                    or any(type(x) is not int or x < 1 for x in shape) or shape[0] * shape[1] != area
                    or item.get("dtype") != "uint8"
                    or any(not legacy._digest(item.get(k)) for k in ("returned_sha256", "fresh_sha256"))
                    or (item["returned_sha256"] == item["fresh_sha256"]) != (count == 0)):
                raise ValueError("v6 camera dtype/shape/hash binding invalid")
        if count and not original_allowance:
            original_mismatches.append(name)
        allowance |= original_allowance
        any_changed |= count > 0
        maximum = max(maximum, error)
    error = check.get("max_abs_error")
    if (type(error) not in (int, float) or not math.isfinite(error) or error < maximum
            or error > max(maximum, 0 if initial else float_tolerance)
            or check.get("bounded_allowance_used") is not allowance
            or (initial and check["bit_exact"] is not (not any_changed))
            or check.get("mismatched_fields") != sorted(original_mismatches)
            or check["matches"] is not (not original_mismatches)):
        raise ValueError("original comparison result contradicts recorded RGB/non-RGB evidence")
    return True


def audit_v6(audit, episode, state, *, steps, initial_hash, initial_only=False, fixed=False):
    """Recheck full physical traces and original result consistency under v6."""
    profile = audit_profile(audit)
    # New v6 normal00 sources keep their existing initial-only reader scope.
    # This does not authorize deriving/regrading old00: derive_source remains
    # nine-mask10 only and legacy v4 initial-only dispatch stays unchanged.
    if initial_only and (profile != V6_PROFILE or steps != 0):
        raise ValueError("v6 initial-only reading requires a native v6 zero-step scope")
    mask = [False, False] if initial_only else [True, False]
    if (audit.get("schema_version") != "remaining-goals-validation-v1"
            or audit.get("episode_id") != episode["episode_id"] or audit.get("initial_mask") != mask
            or type(steps) is not int or audit.get("reference_robot_qpos") != episode.get("reference_robot_qpos")):
        raise ValueError("v6 audit identity/state evidence required")
    if not initial_only and (steps < 150 or audit.get("requested_steps") != steps
            or audit.get("completed_steps") != steps or audit.get("error") is not None
            or audit.get("refresh_nonstepping_checked") is not True):
        raise ValueError("v6 complete audit window/identity/state evidence required")
    trace = audit.get("trace")
    if initial_only:
        if not isinstance(trace,list) or not trace:
            raise ValueError("v6 initial-only trace missing")
        trace = trace[:1]
    if not isinstance(trace, list) or len(trace) != steps + 1:
        raise ValueError("v6 complete audit window required")
    limits = audit.get("limits", {})
    expected_limits = {"position_tolerance": .005, "velocity_tolerance": .01,
        "robot_position_tolerance": .002, "penetration_tolerance": .002, "observation_tolerance": 1e-8}
    if any(limits.get(k) != v for k, v in expected_limits.items()):
        raise ValueError("fixed physical/non-RGB limits changed")
    hold = _vector(audit.get("hold_action"), "hold", 7).tolist()
    ignored = _contact_pairs(audit.get("ignored_contact_pairs"))
    if hold != [0., 0., 0., 0., 0., 0., -1.] or ignored:
        raise ValueError("fixed hold/contact rule changed")
    semantics = episode.get("task_semantics")
    if semantics is not None:
        from ..nine_catalog import validate_episode_semantics, validate_goal_facts, initial_constraints_match
        semantics = validate_episode_semantics(episode)
        if audit.get("task_semantics") != semantics:
            raise ValueError("audit semantic identity differs")
    reference = _vector(episode.get("reference_robot_qpos"), "reference robot")
    first_robot = first_positions = velocity_size = None
    original_checks = []
    for index, row in enumerate(trace):
        if (type(row.get("step")) is not int or row["step"] != index or row.get("goals") != mask
                or any(type(b) is not bool for b in row["goals"])
                or row.get("action") != (None if index == 0 else hold)):
            raise ValueError("audit row order/mask/action mismatch")
        current = _vector(row.get("state"), "state", len(state))
        velocity = _vector(row.get("qvel"), "velocity", velocity_size)
        velocity_size = len(velocity)
        robot = _vector(row.get("robot_qpos"), "robot", len(reference))
        if row.get("state_sha256") != _array_hash(current) or index == 0 and not legacy._same_array(current, state):
            raise ValueError("audit state digest/initial binding mismatch")
        positions = row.get("object_positions")
        if not isinstance(positions, dict) or not positions:
            raise ValueError("audit monitored positions missing")
        positions = {k: _vector(v, "position", 3) for k, v in positions.items()}
        if first_robot is None:
            first_robot, first_positions = robot, positions
        if positions.keys() != first_positions.keys():
            raise ValueError("monitored position inventory changed")
        drift = {k: float(np.linalg.norm(v - first_positions[k])) for k, v in positions.items()}
        robot_drift, reference_error = float(np.max(np.abs(robot-first_robot))), float(np.max(np.abs(robot-reference)))
        speed = float(np.max(np.abs(velocity)))
        contacts = row.get("penetrations")
        if not isinstance(contacts, list):
            raise ValueError("penetration evidence missing")
        for c in contacts:
            if (not isinstance(c, dict) or c.get("ignored") is not False
                    or any(not isinstance(c.get(k), str) or not c[k] for k in ("geom1", "geom2"))
                    or type(c.get("depth")) not in (int, float) or not math.isfinite(c["depth"]) or c["depth"] < 0):
                raise ValueError("invalid penetration evidence")
        penetration = max((c["depth"] for c in contacts), default=0.)
        numeric = {"object_position_drift": drift, "max_abs_velocity": speed,
            "max_abs_robot_drift": robot_drift, "max_abs_reference_robot_error": reference_error,
            "max_raw_penetration": penetration, "max_checked_penetration": penetration}
        if any(row.get(k) != v for k, v in numeric.items()):
            raise ValueError("cached physical diagnostics disagree with raw trace")
        check = row.get("observation_check")
        comparison(check, initial=index == 0, returned_hash=initial_hash if index == 0 else None,
            camera_reference=trace[0].get("observation_check", {}).get("image_diagnostics"), profile=profile, revalidate=True)
        expected = {"finite_state_and_velocity": True, "predicate_mask_matches": True,
            "object_positions_stable": max(drift.values()) <= .005, "velocities_below_limit": speed <= .01,
            "robot_pose_stable": robot_drift <= .002, "reference_robot_pose_matches": reference_error <= .002,
            "contact_penetration_within_limit": penetration <= .002,
            "observation_matches_fresh": check["matches"], "initial_non_rgb_bit_exact": True,
            "refresh_did_not_step": True, "rgb_allowance_state_verified": True}
        if semantics is not None:
            validate_goal_facts(row, semantics)
            expected["initial_constraints_match"] = initial_constraints_match(row)
        if (row.get("checks") != expected or any(type(v) is not bool for v in row["checks"].values())
                or any(not v for k, v in expected.items() if k != "observation_matches_fresh")):
            raise ValueError("physical/state/semantic checks failed or inconsistent")
        original_checks.append(expected)
    aggregate = {k: all(r[k] for r in original_checks) for k in original_checks[0]}
    aggregate.update(validation_window_complete=True, snapshot_contract_valid=True)
    accepted = all(aggregate.values())
    if audit.get("static_acceptance") is not all(original_checks[0].values()):
        raise ValueError("original static result contradicts initial trace")
    if not initial_only and (audit.get("checks") != aggregate or any(type(v) is not bool for v in audit["checks"].values())
            or audit.get("technical_acceptance") is not accepted or audit.get("dynamic_stability") is not accepted
            or audit.get("static_acceptance") is not all(original_checks[0].values())):
        raise ValueError("original aggregate result contradicts original complete trace")
    return {"steps": steps, "initial_state_array_sha256": _array_hash(state),
        "initial_observation_sha256": initial_hash, "technical_acceptance": True,
        "limits": {**deepcopy(limits), **observation_profile_config(V6_PROFILE)["limits"]},
        "hold_action": hold, "ignored_contact_pairs": [], "observation_profile": V6_PROFILE,
        "original_observation_profile": profile or RGB_QUANTIZATION_RULE["rule_id"],
        "original_technical_acceptance": audit["technical_acceptance"],
        "recorded_diagnostics_revalidated": True, "new_native_steps": 0}


def _origin_identity(origin, *, replay=False):
    path = Path(origin["manifest"])
    if not path.is_file():
        raise FileNotFoundError("source manifest missing")
    if not legacy._digest(origin.get("manifest_sha256")) or legacy._sha(path.read_bytes()) != origin["manifest_sha256"]:
        raise ValueError("original manifest SHA binding invalid")
    manifest = legacy._json(path.read_bytes())
    if origin.get("content_hash") != manifest.get("content_hash"):
        raise ValueError("original manifest content hash differs")
    if replay:
        path = Path(origin["candidate_replay"])
        if not legacy._digest(origin.get("replay_sha256")) or legacy._sha(path.read_bytes()) != origin["replay_sha256"]:
            raise ValueError("original replay SHA binding invalid")


def _partial_replay(candidate, origin):
    """Verify existing replay pieces without treating an empty window as done."""
    from pathlib import PurePosixPath
    from ..validation import compare_observations
    from .scoped_sources import _observation_binding
    _origin_identity(origin, replay=True)
    mp, rp = Path(origin["manifest"]).resolve(), Path(origin["candidate_replay"]).resolve()
    files = legacy._Files(mp, rp)
    report = legacy._json(files.read("replay", rp.name, origin["replay_sha256"]))
    replay_config = observation_profile_config(report.get("observation_profile"))
    if report.get("observation_profile") == V6_PROFILE and (report.get("observation_audit_rule") != replay_config["rule"]
            or report.get("observation_audit_limits") != replay_config["limits"]):
        raise ValueError("partial replay profile/rule/limits mismatch")
    e = candidate["episode"]
    if (report.get("kind") != "candidate_formal_adapter_replay" or report.get("protocol") != "nine-mask10"
            or report.get("source_manifest_sha256") != origin["manifest_sha256"]
            or report.get("source_content_hash") != origin["content_hash"]
            or report.get("policy_called") is not False or report.get("release_authorized") is not False
            or report.get("steps") != 150 or report.get("repeats") != 2):
        raise ValueError("partial replay identity/contract differs")
    rows = report.get("episodes")
    if not isinstance(rows,list) or any(not isinstance(r,dict) or r.get("episode_id") != e["episode_id"] for r in rows):
        raise ValueError("partial replay source rows invalid")
    keys = [r.get("repetition") for r in rows]
    if any(type(k) is not int or k not in (0,1) for k in keys) or len(set(keys)) != len(keys):
        raise ValueError("partial replay repetitions invalid")
    state = np.load(mp.parent / e["state_path"], allow_pickle=False)
    frozen = files.observation("manifest", ".", e["initial_observation"], e["initial_observation"]["observation_sha256"])
    completed, incomplete, seen = [], [], set()
    for row in rows:
        if row.get("initial_mask") != [True,False] or row.get("source_legal") is not False:
            raise ValueError("partial replay mask/legality declaration differs")
        path = legacy._safe_name(row["audit_path"])
        if path in seen:
            raise ValueError("replay windows reuse the same audit")
        seen.add(path)
        audit = legacy._json(files.read("replay", path))
        profile = audit_profile(audit)
        if profile != report.get("observation_profile"):
            raise ValueError("partial replay report/audit profile mismatch")
        reset = audit.get("formal_reset_checks")
        if (not isinstance(reset,dict) or set(reset) != {"saved_state_exact","initial_mask_exact","construction_observation_matches","initial_non_rgb_exact"}
                or any(reset.get(k) is not True for k in ("saved_state_exact","initial_mask_exact","initial_non_rgb_exact"))
                or row.get("reset_checks") != reset or audit.get("expected_reset_model_xml_sha256") != e["model_xml_sha256"]
                or not legacy._digest(audit.get("post_restore_model_xml_sha256"))):
            raise ValueError("partial replay reset/state/XML binding invalid")
        check = audit.get("reset_observation_comparison")
        actual = files.observation("replay", PurePosixPath(path).parent.as_posix(), audit.get("reset_initial_observation"),
                                   check.get("returned_sha256") if isinstance(check,dict) else None)
        options = {"observation_profile":profile} if profile else observation_profile_config()["limits"]
        original = compare_observations(actual,frozen,atol=0,require_non_rgb_exact=True,
                                        refresh_state_unchanged=True,**options)
        if original != check or reset["construction_observation_matches"] is not check["matches"]:
            raise ValueError("partial reset original typed pixels/result disagree")
        comparison(check,initial=True,reference_hash=e["initial_observation"]["observation_sha256"],profile=profile,revalidate=True)
        if audit.get("trace") == [] and audit.get("completed_steps") == 0:
            if (audit.get("technical_acceptance") is not False or audit.get("error") is None
                    or row.get("technical_acceptance") is not False or row.get("error") != audit.get("error")):
                raise ValueError("empty replay must retain its original failure")
            incomplete.append(row["repetition"])
            continue
        result = audit_v6(audit,e,state,steps=150,initial_hash=check["returned_sha256"],fixed=True)
        if row.get("error") is not None:
            raise ValueError("completed replay row retains an error")
        _observation_binding(actual,audit["trace"][0]["observation_check"],profile=profile,revalidate=True)
        if row.get("checks") != audit.get("checks") or row.get("technical_acceptance") is not audit.get("technical_acceptance"):
            raise ValueError("partial replay original report/audit disagreement")
        completed.append({"repetition":row["repetition"],"result":result,"audit_sha256":legacy._sha((rp.parent/path).read_bytes())})
    incomplete.extend(sorted({0,1}-set(keys)))
    return {"completed_replays":completed,"missing_repetitions":sorted(incomplete),
            "original_replay_sha256":origin["replay_sha256"],"selected_files":files.finish()}


def _certificate(task,index,origin,candidate,scope,source_evidence=None):
    result = {"schema_version":SCHEMA,"observation_profile":V6_PROFILE,"protocol":"nine-mask10",
        "task_id":task,"initial_state_index":index,"scope":scope,
        "source_manifest_sha256":origin["manifest_sha256"],"source_content_hash":origin["content_hash"],
        "construction_evidence":candidate["construction"],"construction_files":candidate["selected_files"],
        "recorded_diagnostics_revalidated":True,"new_native_steps":0,"raw_rgb_recomputed":False,
        "limitation":LIMITATION}
    if scope == "source":
        result.update(source_replay_sha256=origin["replay_sha256"],source_evidence=source_evidence)
    result["certificate_sha256"] = legacy._canonical(result)
    return result


def _read_certificate(task,index,manifest_path,certificate_path,protocol):
    from .scoped_sources import _candidate
    if protocol != "nine-mask10":
        raise ValueError("v6 recorded source certificate requires nine-mask10")
    path = Path(certificate_path)
    cert = legacy._json(path.read_bytes())
    if (cert.get("schema_version") != SCHEMA or cert.get("observation_profile") != V6_PROFILE
            or cert.get("protocol") != protocol or cert.get("task_id") != task or cert.get("initial_state_index") != index
            or type(cert.get("initial_state_index")) is not int
            or cert.get("scope") not in ("construction","source") or cert.get("recorded_diagnostics_revalidated") is not True
            or type(cert.get("new_native_steps")) is not int or cert["new_native_steps"] != 0
            or cert.get("raw_rgb_recomputed") is not False or cert.get("limitation") != LIMITATION
            or cert.get("certificate_sha256") != legacy._canonical({k:v for k,v in cert.items() if k!="certificate_sha256"})):
        raise ValueError("invalid or modified explicit v6 certificate")
    candidate = _candidate(task,index,manifest_path,protocol=protocol,revalidate_profile=V6_PROFILE)[0]
    if (cert.get("source_manifest_sha256") != candidate["source_manifest_sha256"]
            or cert.get("source_content_hash") != candidate["source_content_hash"]
            or cert.get("construction_evidence") != candidate["construction"]
            or cert.get("construction_files") != candidate["selected_files"]):
        raise ValueError("certificate original construction dependencies/results differ")
    return cert,candidate


def inspect_certified_candidate(task,index,manifest_path,certificate_path,*,protocol):
    return _read_certificate(task,index,manifest_path,certificate_path,protocol)[1]


def verify_certificate(task,index,origin,*,protocol):
    _origin_identity(origin,replay=True)
    cert,_ = _read_certificate(task,index,origin["manifest"],origin["rgb_certificate"],protocol)
    cert_sha = legacy._sha(Path(origin["rgb_certificate"]).read_bytes())
    if not legacy._digest(origin.get("rgb_certificate_sha256")) or origin["rgb_certificate_sha256"] != cert_sha:
        raise ValueError("certificate raw byte hash mismatch")
    if cert["scope"] == "source":
        if cert["source_replay_sha256"] != origin["replay_sha256"]:
            raise ValueError("complete certificate is bound to a different original replay")
        actual = legacy._load_mask10_source(task,origin["manifest"],origin["candidate_replay"],
            indices=[index],fixed=True,protocol=protocol,revalidate_profile=V6_PROFILE)[3]
        if cert.get("source_evidence") != actual:
            raise ValueError("certificate source dependencies/results differ")
    else:
        report = legacy._json(Path(origin["candidate_replay"]).read_bytes())
        if (report.get("observation_profile") != V6_PROFILE or report.get("rgb_certificate_sha256") != cert_sha):
            raise ValueError("construction certificate requires a new explicit v6 replay bound to this certificate")
    return cert


def derive_source(task,index,origin,output,protocol="nine-mask10"):
    """Write a separate recorded-evidence result, never overwrite old artifacts."""
    from .scoped_sources import _candidate,_identity,MissingSourceError
    _identity(task,index,protocol)
    if protocol != "nine-mask10":
        raise ValueError("v6 derivation requires nine-mask10")
    output = Path(output).resolve()
    original = deepcopy(origin) if isinstance(origin,dict) else {}
    for key in ("manifest","candidate_replay","rgb_certificate"):
        if original.get(key):
            root = Path(original[key]).resolve().parent
            if output == root or root in output.parents or output in root.parents:
                raise ValueError("derivation output overlaps original evidence")
    if output.exists():
        raise FileExistsError(output)
    result = {"task_id":task,"initial_state_index":index,"observation_profile":V6_PROFILE,
        "status":"blocked","origin":deepcopy(original),"original_origin":deepcopy(original),
        "required_native_steps":0,"new_native_steps":0,"reason":None,"recorded_diagnostics_revalidated":False,
        "report_path":str(output/"derivation_report.json"),"limitation":LIMITATION}
    cert = candidate = None
    try:
        if not original.get("manifest"):
            raise MissingSourceError("original source did not export a manifest")
        _origin_identity(original)
        candidate = _candidate(task,index,original["manifest"],protocol=protocol,revalidate_profile=V6_PROFILE)[0]
        if not original.get("candidate_replay") or not Path(original["candidate_replay"]).is_file():
            progress = {"completed_replays":[],"missing_repetitions":[0,1]}
        else:
            progress = _partial_replay(candidate,original)
        result["replay_progress"] = progress
        if progress["missing_repetitions"]:
            cert = _certificate(task,index,original,candidate,"construction")
            result.update(status="needs_replay",required_native_steps=300,
                reason="Construction retained; existing paired replay entry requires two independent 150-step repeats. No rebuild.")
        else:
            evidence = legacy._load_mask10_source(task,original["manifest"],original["candidate_replay"],
                indices=[index],fixed=True,protocol=protocol,revalidate_profile=V6_PROFILE)[3]
            cert = _certificate(task,index,original,candidate,"source",evidence)
            result.update(status="ready",reason="Complete original construction and both replay windows revalidated from recorded diagnostics.")
        result["recorded_diagnostics_revalidated"] = True
    except (FileNotFoundError,MissingSourceError) as error:
        if candidate is None:
            result.update(status="needs_build",required_native_steps=None,reason=str(error))
        else:
            cert = _certificate(task,index,original,candidate,"construction")
            result.update(status="needs_replay",required_native_steps=300,reason=str(error),recorded_diagnostics_revalidated=True)
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError) as error:
        result.update(status="blocked",reason=f"{type(error).__name__}: {error}")
    output.mkdir(parents=True,exist_ok=False)
    if cert:
        path = output/"certificate.json"
        path.write_text(json.dumps(cert,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
        result["origin"].update(rgb_certificate=str(path),rgb_certificate_sha256=legacy._sha(path.read_bytes()))
        result["certificate"] = str(path)
    result["result_sha256"] = legacy._canonical(result)
    (output/"derivation_report.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task",required=True)
    parser.add_argument("--index",type=int,required=True)
    parser.add_argument("--origin",type=Path,required=True,help="JSON containing a single bound origin")
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    result=derive_source(args.task,args.index,legacy._json(args.origin.read_bytes()),args.out)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result["status"]=="ready" else 2


if __name__=="__main__":
    raise SystemExit(main())
