"""File-only acceptance of one fixed official source and its immutable archive.

No native simulator, policy, model, or source producer is imported here. Normal00
accepts the original trace-zero evidence only; selected10 retains construction
and independent formal replay windows. Original aggregate reports are untouched.
"""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import re

import numpy as np

from . import source_acceptance as legacy
from ..schema import manifest_hash, validate_manifest, verify_state_file
from ..task_catalog import COMMON_TEN_TASKS, TASKS
from ..validation import _array_hash

NORMAL_SCHEMA = "remaining-headless-normal00-source-acceptance-v1"
SELECTED_SCHEMA = "remaining-headless-selected10-source-acceptance-v1"
SELECTED_TASKS = ("frypan_stove9", "cabinet_close_top_bowl")
HOLD = [0., 0., 0., 0., 0., 0., -1.]
VERSIONS = {"normal00-control": "remaining-headless-normal00-control-v1",
            "selected-mask10": "remaining-headless-goal-endpoint-v1"}


class MissingSourceError(FileNotFoundError):
    """A selected candidate or required evidence file has not been supplied."""


class FailedSourceError(ValueError):
    """Selected original evidence explicitly records a failed acceptance."""


def _guard(operation):
    try:
        return operation()
    except MissingSourceError:
        raise
    except FileNotFoundError as error:
        raise MissingSourceError(str(error)) from error
    except (KeyError, IndexError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError(f"source evidence is malformed: {type(error).__name__}: {error}") from error


def _identity(task, index, protocol):
    allowed = SELECTED_TASKS if protocol == "selected-mask10" else COMMON_TEN_TASKS
    if protocol not in VERSIONS or task not in allowed or type(index) is not int or index not in range(10):
        raise ValueError("source protocol/task/fixed official index identity mismatch")


def _episode(manifest, task, index, mask):
    identifier = f"{task}_s{index:03d}_{''.join(str(int(b)) for b in mask)}"
    entries = manifest.get("episodes")
    if not isinstance(entries, list): raise ValueError("source manifest episodes missing")
    matches = [e for e in entries if isinstance(e, dict) and (e.get("episode_id") == identifier or
        (e.get("task_id") == task and e.get("initial_state_index") == index and e.get("initial_mask") == mask))]
    if not matches: raise MissingSourceError(f"selected episode missing: {identifier}")
    if len(matches) != 1: raise ValueError("selected episode duplicated")
    e = matches[0]
    catalog = TASKS[task]
    instruction = re.split(r"SCENE\d+_", catalog["name"], maxsplit=1)[1].replace("_", " ")
    if (e.get("episode_id") != identifier or e.get("task_id") != task or e.get("suite") != catalog["suite"]
            or e.get("task_name") != catalog["name"] or e.get("goal_specs") != catalog["goals"]
            or e.get("instruction") != instruction
            or e.get("initial_mask") != mask or any(type(b) is not bool for b in e["initial_mask"])
            or type(e.get("initial_state_index")) is not int or e["initial_state_index"] != index
            or type(e.get("seed")) is not int or e["seed"] != index
            or e.get("source_id") != f"{task}_official_{index}" or e.get("horizon") != 520
            or e.get("retention_steps") != 150 or e.get("construction", {}).get("legal") is not False
            or not legacy._digest(e.get("bddl_sha256")) or not legacy._digest(e.get("model_xml_sha256"))):
        raise ValueError("selected source task/instruction/goal/order/index identity mismatch")
    view = {**manifest, "episodes": [e]}
    view.pop("content_hash", None)
    validate_manifest(view, check_files=False, require_complete_masks=False, allow_unreviewed=True)
    return e


def _observation_binding(observation, comparison):
    """Hash the typed returned artifact; do not invent a second fresh artifact.

    Fresh RGB differences exist only as recorded diagnostics in old audits.
    Reconstruct returned non-RGB bytes/camera geometry and bind those diagnostics
    to the saved artifact without claiming a new independent refresh comparison.
    """
    non_rgb = hashlib.sha256()
    cameras = {}
    def walk(value, path):
        if isinstance(value, dict):
            for key in sorted(value): walk(value[key], f"{path}.{key}")
            return
        array = np.asarray(value)
        named = path.startswith("observation.images.") or path in (
            "observation.agentview_image", "observation.robot0_eye_in_hand_image")
        if named and array.dtype == np.uint8 and array.ndim == 3 and array.shape[-1] == 3:
            cameras[path] = {"total_pixels": int(array.shape[0] * array.shape[1])}
        else:
            non_rgb.update(path.encode("utf-8"))
            non_rgb.update(str(array.shape).encode("ascii"))
            non_rgb.update(array.dtype.str.encode("ascii"))
            non_rgb.update(array.tobytes(order="C"))
    walk(observation, "observation")
    if comparison.get("returned_non_rgb_sha256") != non_rgb.hexdigest():
        raise ValueError("initial typed observation non-RGB digest differs from trace")
    legacy._passing_observation_comparison(comparison, initial=True, camera_reference=cameras)


def _candidate(task, index, manifest_path, *, normal=False):
    protocol = "normal00-control" if normal else "selected-mask10"
    _identity(task, index, protocol)
    mp = Path(manifest_path).resolve()
    files = legacy._Files(mp, mp)
    raw = files.read("manifest", mp.name)
    manifest = legacy._json(raw)
    if manifest.get("content_hash") != manifest_hash(manifest) or manifest.get("environment", {}).get("name") != "libero":
        raise ValueError("source manifest content/environment identity mismatch")
    e = _episode(manifest, task, index, [False, False] if normal else [True, False])
    state_raw = files.read("manifest", e["state_path"], e["state_sha256"])
    verify_state_file(e, mp.parent)
    state = np.load(io.BytesIO(state_raw), allow_pickle=False)
    audit = legacy._json(files.read("manifest", e["construction"]["technical_audit"]))
    if not normal and (audit.get("technical_acceptance") is False or audit.get("static_acceptance") is False
                       or audit.get("dynamic_stability") is False):
        raise FailedSourceError("selected construction explicitly failed")
    trace = audit.get("trace")
    if not isinstance(trace, list) or not trace: raise MissingSourceError("initial audit trace missing")
    if normal and (audit.get("static_acceptance") is False
                   or any(value is False for value in trace[0].get("checks", {}).values())):
        raise FailedSourceError("normal00 initial checks explicitly failed")
    comparison = trace[0].get("observation_check", {})
    initial_hash = comparison.get("returned_sha256")
    if not legacy._digest(initial_hash): raise ValueError("initial observation digest missing")
    if e.get("initial_observation") is None: raise MissingSourceError("typed initial observation missing")
    observation = files.observation("manifest", ".", e["initial_observation"], initial_hash)
    _observation_binding(observation, comparison)
    construction = legacy._audit(audit, e, state, steps=0 if normal else audit.get("requested_steps"),
                                 initial_hash=initial_hash, initial_only=normal, fixed=True)
    result = {"manifest": manifest, "episode": e, "construction": construction,
        "selected_files": files.finish(), "source_manifest_sha256": legacy._sha(raw),
        "source_content_hash": manifest["content_hash"]}
    return result, files, audit, state


def inspect_candidate(task, index, manifest_path):
    """Return manifest, episode, construction, selected_files and original hashes.

    Construction is validated for >=150 steps with the frozen physical rules.
    No replay is required/read. MissingSourceError denotes absent evidence,
    FailedSourceError an explicit failure, ValueError malformed/binding evidence.
    """
    return _guard(lambda: _candidate(task, index, manifest_path)[0])


def _initialization(files, origin, candidate, state):
    if not origin.get("initialization"): raise MissingSourceError("normal00 initialization report missing")
    path = Path(origin["initialization"]).resolve()
    files.roots["initialization"] = path.parent
    if not legacy._digest(origin.get("initialization_sha256")):
        raise ValueError("initialization report SHA256 required")
    report = legacy._json(files.read("initialization", path.name, origin["initialization_sha256"]))
    e, manifest = candidate["episode"], candidate["manifest"]
    groups = report.get("groups")
    if not isinstance(groups, list): raise ValueError("initialization source groups missing")
    matches = [g for g in groups if isinstance(g, dict) and g.get("task_id") == e["task_id"]
               and type(g.get("initial_state_index")) is int and g["initial_state_index"] == e["initial_state_index"]]
    if len(matches) != 1: raise ValueError("initialization must bind exactly one matching source group")
    group = matches[0]
    if report.get("environment") != manifest["environment"] or report.get("hold_action") != HOLD:
        raise ValueError("initialization environment/hold mismatch")
    if group.get("base_state_array_sha256") != _array_hash(state):
        raise ValueError("initialization base state digest mismatch")
    steps = report.get("settle_steps")
    if type(steps) is not int: raise ValueError("explicit initialization settle_steps required")
    if report.get("kind") == "real_libero_candidate_construction":
        if (steps != 80 or report.get("task_catalog", {}).get(e["task_id"]) != TASKS[e["task_id"]]
                or group.get("suite") != e["suite"] or group.get("task_name") != e["task_name"]
                or group.get("reset_model_xml_sha256") != e["model_xml_sha256"]):
            raise ValueError("original initialization provenance mismatch")
        kind = "settled_base"
    elif report.get("kind") == "normal00_initialization_v1":
        kind = report.get("initialization_kind")
        if (report.get("protocol") != "normal00-control" or (kind, steps) not in (("settled_base", 80), ("raw_official", 0))
                or group.get("episode_id") != e["episode_id"] or group.get("state_sha256") != e["state_sha256"]
                or group.get("initial_observation_sha256") != e["initial_observation"]["sha256"]):
            raise ValueError("normal00 initialization provenance mismatch")
    else:
        raise ValueError("unsupported initialization report kind")
    return {"kind": kind, "settle_steps": steps, "report_kind": report["kind"],
            "report_sha256": origin["initialization_sha256"], "group": deepcopy(group)}


def _resolve(protocol, task, index, origin):
    _identity(task, index, protocol)
    if not isinstance(origin, dict) or not origin.get("manifest"):
        raise MissingSourceError("source manifest missing")
    for key in ("manifest_sha256", "content_hash"):
        if not legacy._digest(origin.get(key)): raise ValueError(f"source origin needs {key}")
    candidate, files, audit, state = _candidate(task, index, origin["manifest"], normal=protocol == "normal00-control")
    if (candidate["source_manifest_sha256"] != origin["manifest_sha256"]
            or candidate["source_content_hash"] != origin["content_hash"]):
        raise ValueError("original manifest hash binding mismatch")
    e = candidate["episode"]
    selection = {"task_id": task, "mask": e["initial_mask"], "indices": [index], "episode_ids": [e["episode_id"]]}
    snapshots = {"manifest": Path(origin["manifest"]).name}
    if protocol == "selected-mask10":
        if not origin.get("candidate_replay"): raise MissingSourceError("independent replay missing")
        if not legacy._digest(origin.get("replay_sha256")): raise ValueError("source replay SHA256 required")
        rp = Path(origin["candidate_replay"])
        replay_raw = rp.read_bytes()
        if legacy._sha(replay_raw) != origin["replay_sha256"]: raise ValueError("original replay hash binding mismatch")
        report = legacy._json(replay_raw)
        if (report.get("kind") != "candidate_formal_adapter_replay"
                or report.get("source_manifest_sha256") != origin["manifest_sha256"]
                or report.get("source_content_hash") != origin["content_hash"]
                or report.get("policy_called") is not False or report.get("release_authorized") is not False
                or not isinstance(report.get("episodes"), list)):
            raise ValueError("independent replay original-source binding mismatch")
        for row in report.get("episodes", []):
            if isinstance(row, dict) and row.get("episode_id") == e["episode_id"] and row.get("technical_acceptance") is False:
                raise FailedSourceError("selected replay explicitly failed")
        repeats = report.get("repeats")
        rows = [r for r in report.get("episodes", []) if isinstance(r, dict) and r.get("episode_id") == e["episode_id"]]
        if type(repeats) is int and repeats >= 2:
            keys = [r.get("repetition") for r in rows]
            if all(type(k) is int for k in keys) and len(keys) == len(set(keys)) and set(keys) < set(range(repeats)):
                raise MissingSourceError("selected independent replay repetitions missing")
        manifest, raw, replay_bytes, evidence = legacy._load_mask10_source(task, origin["manifest"], rp,
                                                                          indices=[index], fixed=True)
        if raw != Path(origin["manifest"]).read_bytes() or legacy._sha(raw) != origin["manifest_sha256"] or replay_bytes != replay_raw:
            raise ValueError("source changed during scoped validation")
        evidence.update(schema_version=SELECTED_SCHEMA, status="ready", acceptance_scope="selected10")
        snapshots["replay"] = rp.name
    else:
        initialization = _initialization(files, origin, candidate, state)
        evidence = {"schema_version": NORMAL_SCHEMA, "status": "ready", "acceptance_scope": "initial00",
            "selection": selection, "selection_sha256": legacy._canonical(selection),
            "selected_episode_ids": [e["episode_id"]], "source_manifest_sha256": origin["manifest_sha256"],
            "source_content_hash": origin["content_hash"], "selected_files": files.finish(),
            "episodes": [{"episode_id": e["episode_id"], "state_sha256": e["state_sha256"],
                          "construction": candidate["construction"], "replays": []}],
            "initialization": initialization, "dynamic_stability": None,
            "original_audit_diagnostic": {k: deepcopy(audit.get(k)) for k in
                ("technical_acceptance", "static_acceptance", "dynamic_stability", "requested_steps", "completed_steps", "checks", "error")},
            "limitations": ["Initial-only technical scope; no additional hold or independent replay required.",
                "Fresh-observation correspondence uses original recorded state-bound checks; typed returned artifact hashes and geometry are revalidated, not a new refresh.",
                "Original full audit and aggregate failures are retained byte-for-byte."]}
        snapshots["initialization"] = Path(origin["initialization"]).name
    evidence.pop("evidence_sha256", None)
    evidence["evidence_sha256"] = legacy._canonical(evidence)
    episode = deepcopy(e)
    episode.update(evaluation_track="primary" if e["suite"] == "libero_10" else "extension",
                   development_source=task == "basket" and index < 5, policy_seed=7)
    result = {"protocol": protocol, "protocol_version": VERSIONS[protocol], "task_id": task, "suite": e["suite"],
        "status": "ready", "episodes": [episode], "manifest": candidate["manifest"], "source": deepcopy(origin),
        "source_acceptance": evidence, "source_snapshot_files": snapshots,
        "environment_config": {"manifest_dir": str(Path(origin["manifest"]).resolve().parent),
            "environment": candidate["manifest"]["environment"], "image_size": 256, "control_freq": 20}}
    result["source_plan_sha256"] = legacy._canonical(result)
    return result


def resolve_source(protocol, task, index, origin):
    """Resolve one hash-bound origin to a ready single-episode source plan."""
    return _guard(lambda: _resolve(protocol, task, index, origin))


def _plan_identity(plan):
    if not isinstance(plan, dict) or plan.get("source_plan_sha256") != legacy._canonical(
            {k: v for k, v in plan.items() if k != "source_plan_sha256"}):
        raise ValueError("source plan hash mismatch")
    if len(plan.get("episodes", [])) != 1: raise ValueError("single source plan required")


def _roots(directory):
    base = Path(directory).resolve()
    return {key: legacy._contained(base, f"source/{key}_files") for key in ("manifest", "replay", "initialization")}


def archive_source(directory, plan):
    """Copy original selected bytes exclusively; return the archived manifest root."""
    _plan_identity(plan)
    source = plan["source"]
    origins = {"manifest": Path(source["manifest"]).resolve().parent}
    for key, field in (("replay", "candidate_replay"), ("initialization", "initialization")):
        if field in source: origins[key] = Path(source[field]).resolve().parent
    roots = _roots(directory)
    for item in plan["source_acceptance"]["selected_files"]:
        name = legacy._safe_name(item["path"])
        raw = legacy._contained(origins[item["root"]], name).read_bytes()
        if legacy._sha(raw) != item["sha256"]: raise ValueError("source changed before archive")
        target = legacy._contained(roots[item["root"]], name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(raw)
    validate_snapshot(directory, plan)
    return roots["manifest"]


def validate_snapshot(directory, plan):
    """Re-run acceptance solely against contained archived original dependencies."""
    _plan_identity(plan)
    roots = _roots(directory)
    required = {"manifest", "initialization" if plan["protocol"] == "normal00-control" else "replay"}
    if set(plan.get("source_snapshot_files", {})) != required:
        raise ValueError("snapshot must supply every protocol-specific archived report")
    origin = deepcopy(plan["source"])
    for key, field in (("manifest", "manifest"), ("replay", "candidate_replay"), ("initialization", "initialization")):
        if key in plan["source_snapshot_files"]:
            origin[field] = str(legacy._contained(roots[key], legacy._safe_name(plan["source_snapshot_files"][key])))
    for item in plan["source_acceptance"]["selected_files"]:
        path = legacy._contained(roots[item["root"]], legacy._safe_name(item["path"]))
        if legacy._sha(path.read_bytes()) != item["sha256"]: raise ValueError("archived selected file hash mismatch")
    episode = plan["episodes"][0]
    actual = resolve_source(plan["protocol"], plan["task_id"], episode["initial_state_index"], origin)
    # Source location metadata stays original; semantic/evidence bytes must match.
    actual["source"] = deepcopy(plan["source"])
    actual["environment_config"]["manifest_dir"] = plan["environment_config"]["manifest_dir"]
    actual.pop("source_plan_sha256")
    if actual != {k: v for k, v in plan.items() if k != "source_plan_sha256"}:
        raise ValueError("archived source acceptance differs from plan")
    return roots["manifest"]
