"""Read-only, explicitly scoped acceptance of the ten mask10 source states.

This is not a paired-bank release validator. Original full reports stay intact;
only selected state, construction and independent replay files are opened.
No simulator, model, construction or replay is invoked by this module.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath

import numpy as np

from ..schema import manifest_hash, validate_manifest, verify_state_file
from ..task_catalog import COMMON_TEN_TASKS, TASKS
from ..observation_artifact import load_observation_artifact
from ..package_audit import _contained, _safe_name, _passing_observation_comparison
from ..validation import (_array_hash, _vector, _limit, _contact_pairs, compare_observations,
                          RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_RULE)

SCHEMA = "remaining-headless-mask10-source-acceptance-v1"
SCOPE = "mask10"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _json(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError("duplicate source JSON key")
            out[key] = value
        return out
    def invalid(value):
        raise ValueError("nonfinite source JSON value")
    result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict): raise ValueError("source JSON must be an object")
    return result


class _Files:
    def __init__(self, manifest, replay):
        self.roots = {"manifest": manifest.parent.resolve(), "replay": replay.parent.resolve()}
        self.files = {}

    def read(self, root, relative, expected=None):
        name = _safe_name(relative.replace("\\", "/"))
        path = _contained(self.roots[root], name)
        raw = path.read_bytes()
        digest = _sha(raw)
        key = (root, name)
        if expected is not None and digest != expected:
            raise ValueError(f"selected {root} file hash mismatch: {name}")
        if key in self.files and self.files[key] != digest:
            raise ValueError(f"selected source changed during validation: {name}")
        self.files[key] = digest
        return raw

    def observation(self, root, base, reference, expected_digest):
        if not isinstance(reference, dict): raise ValueError("selected observation artifact is missing")
        relative = (PurePosixPath(base) / _safe_name(reference["path"])).as_posix()
        self.read(root, relative, reference.get("sha256"))
        observation = load_observation_artifact(self.roots[root] / base, reference,
                                                expected_digest=expected_digest)
        self.read(root, relative, reference.get("sha256"))
        return observation

    def finish(self):
        for (root, name), digest in list(self.files.items()):
            self.read(root, name, digest)
        return [{"root": root, "path": name, "sha256": digest}
                for (root, name), digest in sorted(self.files.items())]


def _same_array(left, right):
    return np.asarray(left, dtype="<f8").tobytes() == np.asarray(right, dtype="<f8").tobytes()


def _audit(audit, episode, state, *, steps, initial_hash):
    """Recompute saved numerical checks; dynamic RGB has recorded bounds only.

    Initial RGB is independently compared from two typed artifacts by the caller.
    Full dynamic images were never stored by the original audit; do not claim to
    re-render or independently reconstruct their pixels here.
    """
    if (audit.get("schema_version") != "remaining-goals-validation-v1"
            or audit.get("episode_id") != episode["episode_id"]
            or audit.get("initial_mask") != [True, False]
            or type(audit.get("requested_steps")) is not int or audit["requested_steps"] != steps
            or steps < 150 or type(audit.get("completed_steps")) is not int
            or audit["completed_steps"] != steps or audit.get("error") is not None
            or audit.get("technical_acceptance") is not True or audit.get("static_acceptance") is not True
            or audit.get("dynamic_stability") is not True
            or audit.get("observation_audit_rule") != RGB_QUANTIZATION_RULE
            or audit.get("refresh_nonstepping_checked") is not True
            or audit.get("reference_robot_qpos") != episode.get("reference_robot_qpos")):
        raise ValueError("selected audit identity/window/limits or acceptance is invalid")
    limits = audit.get("limits", {})
    for key in ("position_tolerance", "velocity_tolerance", "robot_position_tolerance",
                "penetration_tolerance", "observation_tolerance"):
        _limit(limits.get(key), key)
    if any(limits.get(key) != value for key, value in RGB_QUANTIZATION_AUDIT.items()):
        raise ValueError("selected audit changed the existing fixed RGB rule")
    hold = _vector(audit.get("hold_action"), "hold_action", 7).tolist()
    ignored = _contact_pairs(audit.get("ignored_contact_pairs"))
    trace = audit.get("trace")
    if not isinstance(trace, list) or len(trace) != steps + 1:
        raise ValueError("selected audit window is incomplete")
    reference = _vector(episode.get("reference_robot_qpos"), "reference_robot_qpos")
    first_robot = first_positions = velocity_size = None
    initial_comparison = trace[0].get("observation_check", {})
    for index, row in enumerate(trace):
        if (type(row.get("step")) is not int or row["step"] != index or row.get("goals") != [True, False]
                or any(type(bit) is not bool for bit in row["goals"])
                or row.get("action") != (None if index == 0 else hold)):
            raise ValueError("selected audit trace order/mask/action mismatch")
        current = _vector(row.get("state"), "state", len(state))
        velocity = _vector(row.get("qvel"), "qvel", velocity_size)
        if velocity_size is None: velocity_size = len(velocity)
        robot = _vector(row.get("robot_qpos"), "robot_qpos", len(reference))
        if row.get("state_sha256") != _array_hash(current): raise ValueError("selected audit state digest mismatch")
        if index == 0 and not _same_array(current, state): raise ValueError("selected audit initial state differs")
        positions = row.get("object_positions")
        if not isinstance(positions, dict) or not positions: raise ValueError("selected audit lacks monitored positions")
        positions = {name: _vector(value, "object position", 3) for name, value in positions.items()}
        if first_robot is None: first_robot, first_positions = robot, positions
        if positions.keys() != first_positions.keys(): raise ValueError("selected audit monitored inventory changed")
        drift = {name: float(np.linalg.norm(value - first_positions[name])) for name, value in positions.items()}
        robot_drift, reference_error = float(np.max(np.abs(robot - first_robot))), float(np.max(np.abs(robot - reference)))
        speed = float(np.max(np.abs(velocity)))
        contacts = row.get("penetrations")
        if not isinstance(contacts, list): raise ValueError("selected audit needs explicit penetrations")
        for contact in contacts:
            if (not isinstance(contact, dict) or type(contact.get("ignored")) is not bool
                    or any(not isinstance(contact.get(k), str) or not contact[k] for k in ("geom1", "geom2"))
                    or type(contact.get("depth")) not in (int, float) or not np.isfinite(contact["depth"])
                    or contact["depth"] < 0):
                raise ValueError("selected audit penetration evidence invalid")
            if contact["ignored"] != (tuple(sorted((contact["geom1"], contact["geom2"]))) in ignored):
                raise ValueError("selected audit hidden/inconsistent ignored contact")
        penetration = max((c["depth"] for c in contacts), default=0.)
        checked_penetration = max((c["depth"] for c in contacts if not c["ignored"]), default=0.)
        numeric = {"object_position_drift": drift, "max_abs_velocity": speed,
                   "max_abs_robot_drift": robot_drift, "max_abs_reference_robot_error": reference_error,
                   "max_raw_penetration": penetration, "max_checked_penetration": checked_penetration}
        if any(row.get(key) != value for key, value in numeric.items()):
            raise ValueError("selected audit cached numerical diagnostics differ from raw trace")
        comparison = row.get("observation_check")
        _passing_observation_comparison(comparison, initial=index == 0,
            returned_hash=initial_hash if index == 0 else None,
            float_tolerance=limits["observation_tolerance"], camera_reference=initial_comparison.get("image_diagnostics"))
        checks = {"finite_state_and_velocity": True, "predicate_mask_matches": True,
            "object_positions_stable": max(drift.values()) <= limits["position_tolerance"],
            "velocities_below_limit": speed <= limits["velocity_tolerance"],
            "robot_pose_stable": robot_drift <= limits["robot_position_tolerance"],
            "reference_robot_pose_matches": reference_error <= limits["robot_position_tolerance"],
            "contact_penetration_within_limit": checked_penetration <= limits["penetration_tolerance"],
            "observation_matches_fresh": True, "initial_non_rgb_bit_exact": True,
            "refresh_did_not_step": True, "rgb_allowance_state_verified": True}
        if (row.get("checks") != checks or any(type(v) is not bool for v in row["checks"].values())
                or not all(checks.values())):
            raise ValueError("selected audit physical checks failed or disagree with raw trace")
    expected = {**checks, "validation_window_complete": True, "snapshot_contract_valid": True}
    if audit.get("checks") != expected or any(type(v) is not bool for v in audit["checks"].values()):
        raise ValueError("selected audit aggregate differs from complete checks")
    return {"steps": steps, "initial_state_array_sha256": _array_hash(state),
            "initial_observation_sha256": initial_hash, "technical_acceptance": True,
            "limits": deepcopy(limits), "hold_action": hold,
            "ignored_contact_pairs": deepcopy(audit["ignored_contact_pairs"])}


def _load_mask10_source(task, manifest_path, replay_path):
    """Return original manifest, both original byte strings and scoped evidence."""
    if task not in COMMON_TEN_TASKS: raise ValueError("unknown headless ten-task identity")
    manifest_path, replay_path = Path(manifest_path).resolve(), Path(replay_path).resolve()
    files = _Files(manifest_path, replay_path)
    raw = files.read("manifest", manifest_path.name)
    replay_raw = files.read("replay", replay_path.name)
    manifest, report = _json(raw), _json(replay_raw)
    if (manifest.get("content_hash") != manifest_hash(manifest)
            or manifest.get("environment", {}).get("name") != "libero"):
        raise ValueError("source manifest content/environment identity mismatch")
    entries = manifest.get("episodes")
    if not isinstance(entries, list): raise ValueError("source manifest episodes missing")
    expected_ids = [f"{task}_s{index:03d}_10" for index in range(10)]
    selected = []
    for index, identifier in enumerate(expected_ids):
        matches = [e for e in entries if isinstance(e, dict) and e.get("episode_id") == identifier]
        if len(matches) != 1: raise ValueError("all ten unique mask10 official sources 0..9 are required")
        episode = matches[0]
        if (episode.get("task_id") != task or episode.get("suite") != TASKS[task]["suite"]
                or episode.get("task_name") != TASKS[task]["name"] or episode.get("goal_specs") != TASKS[task]["goals"]
                or episode.get("initial_mask") != [True, False] or episode.get("initial_state_index") != index
                or episode.get("seed") != index or episode.get("source_id") != f"{task}_official_{index}"
                or episode.get("horizon") != 520 or episode.get("retention_steps") != 150
                or episode.get("construction", {}).get("legal") is not False
                or not _digest(episode.get("bddl_sha256")) or not _digest(episode.get("model_xml_sha256"))):
            raise ValueError("selected source task/goal/order/index identity mismatch")
        selected.append(episode)
    view = {**manifest, "episodes": selected}
    view.pop("content_hash", None)
    validate_manifest(view, base_dir=manifest_path.parent, check_files=False,
                      require_complete_masks=False, allow_unreviewed=True)
    if (report.get("kind") != "candidate_formal_adapter_replay"
            or report.get("source_content_hash") != manifest["content_hash"]
            or report.get("source_manifest_sha256") != _sha(raw)
            or report.get("policy_called") is not False or report.get("release_authorized") is not False
            or type(report.get("steps")) is not int or report["steps"] < 150
            or type(report.get("repeats")) is not int or report["repeats"] < 2
            or not isinstance(report.get("episodes"), list)):
        raise ValueError("independent replay source/steps/repeats identity mismatch")
    rows = [r for r in report["episodes"] if isinstance(r, dict) and r.get("episode_id") in expected_ids]
    expected_keys = {(identifier, repeat) for identifier in expected_ids for repeat in range(report["repeats"])}
    keys = [(r.get("episode_id"), r.get("repetition")) for r in rows]
    if (any(type(r.get("repetition")) is not int for r in rows) or len(keys) != len(set(keys))
            or set(keys) != expected_keys):
        raise ValueError("selected replay evidence missing, duplicated or unfinished")
    accepted = []
    for episode in selected:
        identifier = episode["episode_id"]
        verify_state_file(episode, manifest_path.parent)
        state = np.load(io.BytesIO(files.read("manifest", episode["state_path"], episode["state_sha256"])), allow_pickle=False)
        construction = _json(files.read("manifest", episode["construction"]["technical_audit"]))
        initial_hash = construction.get("trace", [{}])[0].get("observation_check", {}).get("returned_sha256")
        if not _digest(initial_hash): raise ValueError("selected construction initial observation digest missing")
        frozen = files.observation("manifest", ".", episode.get("initial_observation"), initial_hash)
        construction_result = _audit(construction, episode, state,
            steps=construction.get("requested_steps"), initial_hash=initial_hash)
        replay_results = []
        for row in sorted((r for r in rows if r["episode_id"] == identifier), key=lambda r: r["repetition"]):
            if (row.get("technical_acceptance") is not True or row.get("initial_mask") != [True, False]
                    or row.get("source_legal") is not False or row.get("error") is not None):
                raise ValueError("selected mask10 replay explicitly failed")
            audit_path = _safe_name(row["audit_path"])
            audit = _json(files.read("replay", audit_path))
            reset = row.get("reset_checks")
            if (not isinstance(reset, dict) or set(reset) != {"saved_state_exact", "initial_mask_exact", "construction_observation_matches", "initial_non_rgb_exact"}
                    or any(v is not True for v in reset.values()) or audit.get("formal_reset_checks") != reset
                    or audit.get("expected_reset_model_xml_sha256") != episode["model_xml_sha256"]
                    or not _digest(audit.get("post_restore_model_xml_sha256"))):
                raise ValueError("selected replay formal reset/XML evidence mismatch")
            comparison = audit.get("reset_observation_comparison")
            if not isinstance(comparison, dict): raise ValueError("selected replay reset comparison missing")
            actual = files.observation("replay", PurePosixPath(audit_path).parent.as_posix(),
                audit.get("reset_initial_observation"), comparison.get("returned_sha256"))
            recomputed = compare_observations(actual, frozen, atol=0, require_non_rgb_exact=True,
                refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
            if recomputed != comparison: raise ValueError("selected reset pixel/proprio comparison differs from artifacts")
            _passing_observation_comparison(comparison, initial=True, reference_hash=initial_hash)
            result = _audit(audit, episode, state, steps=report["steps"], initial_hash=comparison["returned_sha256"])
            if (row.get("checks") != audit["checks"] or audit["trace"][0]["observation_check"]["returned_non_rgb_sha256"] != comparison["returned_non_rgb_sha256"]):
                raise ValueError("selected replay report or initial non-RGB binding differs")
            replay_results.append({"repetition": row["repetition"], "audit_path": audit_path, **result})
        accepted.append({"episode_id": identifier, "state_sha256": episode["state_sha256"],
                         "construction": construction_result, "replays": replay_results})
    unselected = [r for r in report["episodes"] if not isinstance(r, dict) or r.get("episode_id") not in expected_ids]
    selection = {"task_id": task, "mask": [True, False], "indices": list(range(10)), "episode_ids": expected_ids}
    evidence = {"schema_version": SCHEMA, "status": "mask10_ready", "acceptance_scope": SCOPE,
        "selection": selection, "selection_sha256": _canonical(selection), "selected_episode_ids": expected_ids,
        "source_manifest_sha256": _sha(raw), "source_content_hash": manifest["content_hash"],
        "source_replay_sha256": _sha(replay_raw), "selected_files": files.finish(), "episodes": accepted,
        "global_report_diagnostic": {key: deepcopy(report.get(key)) for key in ("technical_acceptance", "error")},
        "unselected_record_count": len(unselected), "unselected_failures": [deepcopy(r) for r in unselected
            if isinstance(r, dict) and r.get("technical_acceptance") is False],
        "limitations": ["Mask10-only technical acceptance; no paired-bank/global release claim.",
            "Dynamic RGB is checked against recorded fixed-bound diagnostics; only saved initial pixel arrays are recomputed.",
            "Original full reports and failures are retained byte-for-byte; no unselected audit/state is required."]}
    evidence["evidence_sha256"] = _canonical(evidence)
    return manifest, raw, replay_raw, evidence


def load_mask10_source(task, manifest_path, replay_path):
    """Reject incomplete/malformed selected evidence as a task-local error."""
    try:
        return _load_mask10_source(task, manifest_path, replay_path)
    except (KeyError, IndexError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError(f"selected mask10 source evidence is incomplete or malformed: {type(error).__name__}: {error}") from error


def validate_mask10_snapshot(task, manifest_path, replay_path, evidence):
    """Validate an archived complete report plus only its selected dependencies.

    Paths resolve against the two archived report directories, never original
    source locations. Callers copy ``selected_files`` preserving those relative
    paths; this reader never writes or rewrites any input.
    """
    if (not isinstance(evidence, dict) or evidence.get("schema_version") != SCHEMA
            or evidence.get("evidence_sha256") != _canonical({k: v for k, v in evidence.items() if k != "evidence_sha256"})):
        raise ValueError("mask10 scoped snapshot evidence identity mismatch")
    manifest, raw, replay_raw, actual = load_mask10_source(task, manifest_path, replay_path)
    if actual != evidence: raise ValueError("mask10 scoped snapshot differs from archived evidence")
    return manifest, raw, replay_raw, actual
