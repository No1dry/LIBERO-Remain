"""Auditable normal-demonstration labels and read-only OFT feature caches.

Importing this module never creates an environment or loads a policy. Real
restoration, passive-hold labelling and feature extraction are explicit user
operations. Source numbers are never inferred from demonstration names.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import pickle
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
import zipfile

import numpy as np

from ..observation_artifact import load_observation_artifact, save_observation_artifact
from .schema import input_sha256, validate_input_evidence

AUDIT_SCHEMA = "remaining-finish-data-audit-v1"
DOMAIN_AUDIT_SCHEMA = "remaining-finish-data-audit-v2"
CACHE_SCHEMA = "remaining-finish-feature-cache-v1"
FEATURE_VERSION = "oft-l1-action56-mean-v1"
DEFAULT_SPLIT = {"train": list(range(5, 35)), "validation": list(range(35, 40)),
                 "normal_test": list(range(40, 50)), "remain_test": list(range(5))}
LABEL_CONTRACT = {"version": "current-state-passive-hold-v1", "confirmation_steps": 4,
                  "future_task_actions_allowed": False, "unknown_is_negative": False}
OBSERVATION_KEYS = {"agentview_image", "robot0_eye_in_hand_image", "robot0_eef_pos",
                    "robot0_eef_quat", "robot0_gripper_qpos", "robot0_joint_pos", "robot0_joint_vel"}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def state_sha256(state):
    """SHA256 of finite 1-D C-order little-endian float64 bytes, no NPY header."""
    array = np.asarray(state, dtype="<f8")
    if array.ndim != 1 or not array.size or not np.isfinite(array).all():
        raise ValueError("saved state must be a finite nonempty vector")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("artifact identities require a lowercase SHA256 digest")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _contained(base, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("artifact path must be a contained relative path")
    posix, win = PurePosixPath(relative.replace("\\", "/")), PureWindowsPath(relative)
    if win.drive or win.root or posix.is_absolute() or ".." in posix.parts or ":" in relative:
        raise ValueError("artifact path must be a contained relative path")
    base = Path(base).resolve()
    target = (base / Path(*posix.parts)).resolve()
    if not target.is_relative_to(base):
        raise ValueError("artifact path escapes root")
    return target


def validate_split(split=None, *, alternative_confirmation=None):
    """Validate whole-source ownership; changing the default needs an explicit record."""
    split = copy.deepcopy(DEFAULT_SPLIT if split is None else split)
    if not isinstance(split, dict) or set(split) != set(DEFAULT_SPLIT):
        raise ValueError("split must define train, validation, normal_test and remain_test")
    seen = set()
    for name, indices in split.items():
        if (not isinstance(indices, list) or not indices or
                any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices)):
            raise ValueError(f"invalid source indices for {name}")
        if seen.intersection(indices):
            raise ValueError("source appears in multiple splits")
        seen.update(indices)
    if split != DEFAULT_SPLIT:
        if not isinstance(alternative_confirmation, dict) or alternative_confirmation.get("confirmed") is not True:
            raise ValueError("alternative grouping needs explicit confirmation")
        for key in ("reviewer", "reason"):
            if not isinstance(alternative_confirmation.get(key), str) or not alternative_confirmation[key].strip():
                raise ValueError("alternative grouping needs reviewer and reason")
        if split["remain_test"] != DEFAULT_SPLIT["remain_test"]:
            raise ValueError("existing Remain sources 0..4 and every edited variant stay reserved")
    return split


def validate_group_rows(rows, split):
    """Detect same source, trajectory, or saved physical state across groups."""
    owners = {i: name for name, indices in split.items() for i in indices}
    seen, row_ids = {}, set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("row_id"), str) or not row["row_id"]:
            raise ValueError("row needs a nonempty identity")
        if row["row_id"] in row_ids:
            raise ValueError("duplicate row identity")
        row_ids.add(row["row_id"])
        if type(row.get("source_index")) is not int or owners.get(row["source_index"]) != row.get("split"):
            raise ValueError("source/split mismatch")
        if row.get("edited_variant", False) and row["split"] in {"train", "validation"}:
            raise ValueError("edited test variants cannot train or calibrate the head")
        for field in ("trajectory_id", "state_sha256"):
            identity = row.get(field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(f"row needs {field}")
            key = (field, identity)
            if key in seen and seen[key] != row["split"]:
                raise ValueError(f"cross-split leakage through {field}")
            seen[key] = row["split"]


def deterministic_alternative_split(available_source_indices):
    """Propose, never adopt, a reduced training set with unchanged pilot sizes.

    Keep 0..4 reserved, keep every available original validation/test member in
    its group, then fill missing normal-test and validation slots from the
    highest available *original training* indices. Never move held-out sources
    into training. Require five validation, ten normal-test and one train source;
    class coverage and collection mapping still need separate audit/confirmation.
    """
    available = sorted(set(available_source_indices))
    if any(type(value) is not int or value < 0 for value in available):
        raise ValueError("available source indices must be nonnegative integers")
    proposed = {name: [i for i in indices if i in available] for name, indices in DEFAULT_SPLIT.items()}
    reasons = []
    if proposed["remain_test"] != DEFAULT_SPLIT["remain_test"]:
        reasons.append("reserved_remain_source_mapping_incomplete")
    pool = proposed["train"][:]
    for name, size in (("normal_test", 10), ("validation", 5)):
        needed = size - len(proposed[name])
        if needed > 0:
            picked = pool[-needed:] if needed <= len(pool) else pool[:]
            proposed[name] = sorted(proposed[name] + picked)
            pool = [i for i in pool if i not in picked]
        if len(proposed[name]) != size:
            reasons.append(f"insufficient_{name}_sources")
    proposed["train"] = pool
    if not pool:
        reasons.append("no_training_sources_left")
    return {"status": "not_proposable" if reasons else "proposal_requires_confirmation",
            "rule": "preserve-heldout-fill-from-highest-original-training-v1",
            "available_source_indices": available, "proposed_split": None if reasons else proposed,
            "reasons": reasons, "automatically_applied": False,
            "class_coverage_verified": False,
            "next_action": "confirm provenance and class coverage, then explicitly approve this full source split; no automatic training"}


def _truth(frame):
    if not isinstance(frame, dict):
        raise ValueError("truth evidence must be an object")
    goals = frame.get("goals")
    released = frame.get("released")
    if not isinstance(goals, list) or not goals or any(type(v) is not bool for v in goals):
        raise ValueError("goal truth must be a nonempty strict bool list")
    if released is not None and type(released) is not bool:
        raise ValueError("release truth must be bool or null")
    return goals, released


def derive_label(current, hold_evidence=None, *, state_digest=None, confirmation_steps=4):
    """Recompute a label from current GT/release and an independent K-step hold.

    Current incomplete or demonstrably grasped states are negative. Current
    completion without release/stability evidence is unknown, never negative.
    A positive requires steps 0..K of passive hold from this exact saved state.
    Future demonstration actions, is_last and elapsed time are not evidence.
    """
    if type(confirmation_steps) is not int or confirmation_steps <= 0:
        raise ValueError("confirmation_steps must be positive")
    goals, released = _truth(current)
    if not all(goals):
        return {"label": 0, "reason": "current_goal_incomplete"}
    if released is False:
        return {"label": 0, "reason": "current_target_not_released"}
    if released is None or not isinstance(current.get("release_evidence"), dict) or not current["release_evidence"]:
        return {"label": None, "reason": "release_evidence_missing"}
    if hold_evidence is None:
        return {"label": None, "reason": "passive_hold_evidence_missing"}
    if (not isinstance(hold_evidence, dict) or not hold_evidence.get("hold_contract")
            or hold_evidence.get("source_state_sha256") != state_digest):
        return {"label": None, "reason": "passive_hold_identity_missing_or_mismatched"}
    trace = hold_evidence.get("trace")
    if (not isinstance(trace, list) or len(trace) != confirmation_steps + 1 or
            any(not isinstance(f, dict) or type(f.get("step")) is not int or f["step"] != i
                for i, f in enumerate(trace))):
        return {"label": None, "reason": "passive_hold_window_incomplete"}
    if _truth(trace[0]) != (goals, released):
        return {"label": None, "reason": "passive_hold_initial_truth_mismatch"}
    for frame in trace:
        frame_goals, frame_released = _truth(frame)
        if len(frame_goals) != len(goals):
            raise ValueError("passive hold changed goal dimension")
        if not all(frame_goals) or frame_released is False:
            return {"label": 0, "reason": "current_completion_unstable_under_hold"}
        if frame_released is None or not frame.get("release_evidence"):
            return {"label": None, "reason": "passive_hold_release_unknown"}
    return {"label": 1, "reason": "current_completion_released_and_passively_stable"}


def _legal_observation(observation):
    if not isinstance(observation, dict) or not set(observation).issubset(OBSERVATION_KEYS):
        raise ValueError("policy observation contains forbidden evaluator/metadata fields")
    required = {"agentview_image", "robot0_eye_in_hand_image", "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"}
    if not required.issubset(observation):
        raise ValueError("OFT observation lacks required cameras/proprio")
    for key, value in observation.items():
        array = np.asarray(value)
        if not array.size or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
            raise ValueError("policy observation must contain finite numeric arrays")
        if key.endswith("image") and (array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3):
            raise ValueError("policy cameras must be uint8 HxWx3")
        size = {"robot0_eef_pos": 3, "robot0_eef_quat": 4, "robot0_gripper_qpos": 2,
                "robot0_joint_pos": 7, "robot0_joint_vel": 7}.get(key)
        if size is not None and array.shape != (size,):
            raise ValueError(f"invalid policy proprio shape: {key}")
    return observation


def read_demonstrations(path):
    """Read actual LIBERO HDF5 saved states; no simulation and no demo-ID mapping."""
    import h5py
    result = []
    with h5py.File(path, "r") as source:
        if "data" not in source:
            raise ValueError("HDF5 has no data group")
        for name in sorted(source["data"]):
            group = source["data"][name]
            if not isinstance(group, h5py.Group) or "states" not in group:
                continue
            states = np.asarray(group["states"], dtype="<f8")
            if states.ndim != 2 or not states.size or not np.isfinite(states).all():
                raise ValueError(f"invalid saved states in {name}")
            xml = group.attrs.get("model_file", source["data"].attrs.get("model_file"))
            if isinstance(xml, bytes):
                xml = xml.decode("utf-8")
            if xml is not None and not isinstance(xml, str):
                raise ValueError("model_file must be XML text")
            result.append({"trajectory_id": name, "states": states, "model_xml": xml})
    if not result:
        raise ValueError("HDF5 contains no saved-state trajectories")
    return result


class _NumericStateUnpickler(pickle.Unpickler):
    """Legacy torch-saved NumPy arrays without permitting general pickle globals."""
    def find_class(self, module, name):
        import codecs
        allowed = {("numpy", "ndarray"): np.ndarray, ("numpy", "dtype"): np.dtype,
                   ("_codecs", "encode"): codecs.encode}
        for namespace in ("numpy.core.multiarray", "numpy._core.multiarray"):
            allowed[(namespace, "_reconstruct")] = np.core.multiarray._reconstruct
            allowed[(namespace, "scalar")] = np.core.multiarray.scalar
        if (module, name) not in allowed:
            raise pickle.UnpicklingError(f"forbidden initial-state pickle global: {module}.{name}")
        return allowed[(module, name)]


def _numeric_pickle_load(stream, **kwargs):
    return _NumericStateUnpickler(stream, **kwargs).load()


def read_initial_states(path):
    path = Path(path)
    if path.suffix == ".npy":
        data = np.load(path, allow_pickle=False)
    else:
        import torch
        try:
            data = torch.load(path, map_location="cpu", weights_only=True)
        except pickle.UnpicklingError:
            restricted = SimpleNamespace(__name__="remaining_numeric_state_pickle", Unpickler=_NumericStateUnpickler,
                                         load=_numeric_pickle_load)
            data = torch.load(path, map_location="cpu", weights_only=False, pickle_module=restricted)
        if hasattr(data, "detach"):
            data = data.detach().cpu().numpy()
    data = np.asarray(data, dtype="<f8")
    if data.ndim != 2 or not data.size or not np.isfinite(data).all():
        raise ValueError("official init states must be a finite 2-D array")
    return data


def audit_plan(config):
    """Pure config/file plan: never opens a dataset, restores state or loads weights."""
    if isinstance(config, dict) and ("data_profile" in config or "expected_assets" in config):
        from .data_profiles import ASSET_KEYS, validate_domain_config
        profile = validate_domain_config(config)
        return {"schema_version": "remaining-finish-data-plan-v2", "profile": profile,
            "profile_sha256": canonical_hash(profile), "expected_assets": copy.deepcopy(config["expected_assets"]),
            "files": {key: {"path": config[key], "exists": Path(config[key]).is_file()} for key in ASSET_KEYS},
            "state_stride": 8, "sampling_rule": "stride8-plus-last-saved-state-v1",
            "restoration_roles": ["head_train", "head_validation"], "label_contract": copy.deepcopy(LABEL_CONTRACT),
            "simulation_created": False, "weights_loaded": False, "labels_generated": 0,
            "ready_for_feature_export": False, "ancestry_independence": "unproven",
            "frames_and_hold_steps": "file registry determines sampled frames; at most four hold steps per complete/released frame",
            "source_mapping": "separate actual HDF trajectory and official init keys; no demo-to-init mapping"}
    if not isinstance(config, dict):
        raise ValueError("data audit config must be an object")
    for key in ("hdf5_path", "init_states_path", "bddl_path", "original_instruction"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"data audit needs {key}")
    split = validate_split(config.get("split"), alternative_confirmation=config.get("alternative_confirmation"))
    stride = config.get("state_stride", 8)
    if type(stride) is not int or stride < 1:
        raise ValueError("state_stride must be a positive integer")
    return {"schema_version": "remaining-finish-data-plan-v1", "split": split,
            "files": {key: {"path": config[key], "exists": Path(config[key]).is_file()}
                      for key in ("hdf5_path", "init_states_path", "bddl_path")},
            "state_stride": stride, "label_contract": copy.deepcopy(LABEL_CONTRACT),
            "simulation_created": False, "weights_loaded": False,
            "frames_and_hold_steps": "determined by audit; at most four hold steps per sampled complete/released frame",
            "source_mapping": "verified state match or explicitly confirmed collection provenance; never demo numbering"}


def _mapping(trajectories, initials, config, data_hash, init_hash):
    declarations = config.get("trajectory_source_map", {})
    if not isinstance(declarations, dict):
        raise ValueError("trajectory_source_map must be a dictionary")
    hashes = [state_sha256(value) for value in initials]
    mappings, issues, alternatives = [], [], []
    for trajectory in trajectories:
        name = trajectory["trajectory_id"]
        initial_hash = state_sha256(trajectory["states"][0])
        matches = [i for i, value in enumerate(hashes) if value == initial_hash]
        record = declarations.get(name)
        if type(record) is int:
            record = {"source_index": record, "method": "exact_state"}
        # Unique exact matches can establish mapping without trusting the demo name.
        if record is None and len(matches) == 1:
            record = {"source_index": matches[0], "method": "exact_state"}
        valid = isinstance(record, dict) and type(record.get("source_index")) is int
        index = record.get("source_index") if valid else None
        valid = valid and 0 <= index < len(initials)
        method = record.get("method") if valid else None
        if valid and method == "exact_state":
            valid = index in matches and len(matches) == 1
        elif valid and method == "collection_provenance":
            required = {"hdf5_sha256": data_hash, "init_states_sha256": init_hash,
                        "trajectory_id": name, "source_state_sha256": hashes[index],
                        "trajectory_initial_state_sha256": initial_hash, "manually_confirmed": True}
            valid = all(type(record.get(k)) is type(v) and record.get(k) == v for k, v in required.items())
            valid = valid and all(isinstance(record.get(k), str) and record[k].strip()
                                  for k in ("collection_record_source", "reviewer", "confirmation_reason"))
        else:
            valid = False
        if not valid:
            issues.append({"trajectory_id": name, "reason": "source_mapping_unverified"})
            alternatives.append({"trajectory_id": name, "exact_match_candidates": matches,
                                 "next_action": "confirm collection provenance or retain as unmapped; do not infer demo index"})
            continue
        if record.get("edited_variant", False):
            issues.append({"trajectory_id": name, "reason": "edited_trajectory_is_not_normal_demonstration"})
            continue
        mappings.append({"trajectory_id": name, "source_index": index, "method": method,
                         "source_state_sha256": hashes[index], "trajectory_initial_state_sha256": initial_hash,
                         "evidence": copy.deepcopy(record)})
    if set(declarations) - {t["trajectory_id"] for t in trajectories}:
        raise ValueError("source map refers to an unknown trajectory")
    return mappings, issues, alternatives


def audit_demonstrations(config, *, provider_factory=None, out=None):
    """User-run audit with an injectable real provider; unavailable evidence stays insufficient.

    provider.restore_demonstration(state, model_xml=...) returns observation,
    goals, released and release_evidence. capture_hold_label(state,K,model_xml)
    must branch from this state, preserve the saved current input, and return a
    source_state_sha256, hold_contract and independent step-0..K truth trace.
    """
    if isinstance(config, dict) and ("data_profile" in config or "expected_assets" in config):
        return _audit_domain_demonstrations(config, provider_factory=provider_factory, out=out)
    plan = audit_plan(config)
    destination = Path(out) if out is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": AUDIT_SCHEMA, "status": "insufficient", "plan": plan,
              "original_instruction": config["original_instruction"], "split": plan["split"],
              "alternative_confirmation": copy.deepcopy(config.get("alternative_confirmation")),
              "label_contract": copy.deepcopy(LABEL_CONTRACT), "trajectories": [], "rows": [],
              "issues": [], "alternatives": [], "assets": {},
              "provider_execution_requested": provider_factory is not None,
              "limitations": ["Source isolation applies to the new head, not the frozen SOG10 backbone.",
                              "Successful demonstrations do not establish failure/stall-negative coverage."]}
    provider = None
    try:
        missing = [key for key, item in plan["files"].items() if not item["exists"]]
        if missing:
            report["issues"].append({"reason": "missing_assets", "fields": missing})
        else:
            report["assets"] = {key: {"path": config[key], "sha256": _file_hash(config[key])}
                                for key in plan["files"]}
            trajectories = read_demonstrations(config["hdf5_path"])
            initials = read_initial_states(config["init_states_path"])
            # Inventory is evidence for investigating provenance, not permission
            # to identify a demonstration by its name or silently assign a source.
            report["source_inventory"] = {
                "state_hash_contract": "sha256-little-endian-float64-C-order-no-header-v1",
                "establishes_source_mapping": False,
                "official_initial_states": [{"source_index": index, "source_state_sha256": state_sha256(state)}
                                            for index, state in enumerate(initials)],
                "demonstrations": [{"trajectory_id": trajectory["trajectory_id"],
                    "trajectory_initial_state_sha256": state_sha256(trajectory["states"][0]),
                    "saved_states": len(trajectory["states"]),
                    "model_xml_sha256": hashlib.sha256((trajectory["model_xml"] or "").encode()).hexdigest()}
                    for trajectory in trajectories]}
            mappings, issues, alternatives = _mapping(trajectories, initials, config,
                report["assets"]["hdf5_path"]["sha256"], report["assets"]["init_states_path"]["sha256"])
            report["issues"].extend(issues)
            report["alternatives"].extend(alternatives)
            owners = {i: name for name, indices in plan["split"].items() for i in indices}
            covered = {item["source_index"] for item in mappings}
            absent = sorted(set(owners) - covered)
            if absent:
                report["issues"].append({"reason": "group_source_coverage_incomplete", "source_indices": absent})
                report["alternatives"].append(deterministic_alternative_split(covered))
            indexed = {t["trajectory_id"]: t for t in trajectories}
            for mapping in mappings:
                if mapping["source_index"] not in owners:
                    report["issues"].append({"reason": "source_outside_split", "source_index": mapping["source_index"]})
                    continue
                trajectory = indexed[mapping["trajectory_id"]]
                report["trajectories"].append({**mapping, "split": owners[mapping["source_index"]],
                    "saved_states": len(trajectory["states"]),
                    "model_xml_sha256": hashlib.sha256((trajectory["model_xml"] or "").encode()).hexdigest()})
            if not report["issues"]:
                if provider_factory is None or destination is None:
                    report["issues"].append({"reason": "restoration_provider_and_new_output_required"})
                else:
                    provider = provider_factory(config)
                    report["provider_identity"] = copy.deepcopy(getattr(provider, "metadata", {}))
                    for mapping in report["trajectories"]:
                        if mapping["split"] not in {"train", "validation"}:
                            continue
                        trajectory = indexed[mapping["trajectory_id"]]
                        indices = sorted(set(range(0, len(trajectory["states"]), plan["state_stride"])) |
                                         {len(trajectory["states"]) - 1})
                        for step in indices:
                            state = trajectory["states"][step].copy()
                            digest = state_sha256(state)
                            restored = provider.restore_demonstration(state.copy(), model_xml=trajectory["model_xml"])
                            observation = copy.deepcopy(_legal_observation(restored["observation"]))
                            current = {key: copy.deepcopy(restored.get(key)) for key in ("goals", "released", "release_evidence")}
                            _truth(current)
                            if step == 0 and any(current["goals"]):
                                raise ValueError("normal demonstration must begin at actual mask00")
                            row_index = len(report["rows"])
                            reference = save_observation_artifact(destination, f"observations/{row_index:08d}.npz", observation)
                            hold = None
                            if all(current["goals"]) and current["released"] is True:
                                hold = provider.capture_hold_label(state.copy(), 4, model_xml=trajectory["model_xml"])
                            row = {"row_id": f"{mapping['trajectory_id']}:{step}",
                                   "trajectory_id": mapping["trajectory_id"], "source_index": mapping["source_index"],
                                   "split": mapping["split"], "saved_state_index": step, "state_sha256": digest,
                                   "observation": reference, "current": current, "hold_evidence": hold,
                                   "original_instruction_sha256": hashlib.sha256(config["original_instruction"].encode()).hexdigest()}
                            row.update(derive_label(current, hold, state_digest=digest))
                            report["rows"].append(row)
                    validate_group_rows(report["rows"], plan["split"])
                    report["class_coverage"] = {split: {str(label): sum(row["split"] == split and row["label"] == label
                        for row in report["rows"]) for label in (0, 1, None)} for split in ("train", "validation")}
                    for split, counts in report["class_coverage"].items():
                        if not counts["0"] or not counts["1"]:
                            report["issues"].append({"reason": "label_class_coverage_insufficient", "split": split})
                    if not report["issues"]:
                        report["status"] = "ready_for_feature_export"
            for key, item in report["assets"].items():
                if _file_hash(config[key]) != item["sha256"]:
                    raise ValueError(f"source asset changed while auditing: {key}")
    except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as error:
        report["status"] = "insufficient"
        report["issues"].append({"reason": "audit_error", "type": type(error).__name__, "message": str(error)})
    except (KeyboardInterrupt, SystemExit) as error:
        report["status"] = "interrupted"
        report["issues"].append({"reason": "audit_interrupted", "type": type(error).__name__})
        raise
    finally:
        if provider is not None and callable(getattr(provider, "close", None)):
            try:
                provider.close()
            except Exception as error:
                report["status"] = "insufficient"
                report["issues"].append({"reason": "provider_close_error", "type": type(error).__name__, "message": str(error)})
        report["work_counts"] = {"current_observations": len(report["rows"]),
            "hold_branches": sum(row.get("hold_evidence") is not None for row in report["rows"]),
            "recorded_hold_steps": sum(max(0, len(row.get("hold_evidence", {}).get("trace", [])) - 1)
                                       for row in report["rows"] if row.get("hold_evidence") is not None),
            "eligible_feature_forwards": sum(row.get("label") is not None for row in report["rows"])}
        report["audit_sha256"] = canonical_hash(report)
        if destination is not None:
            _write(destination / "audit.json", report)
    return report


def validate_audit(audit, *, base_dir=None):
    if isinstance(audit, dict) and audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA:
        return _validate_domain_audit(audit, base_dir=base_dir)
    if not isinstance(audit, dict) or audit.get("schema_version") != AUDIT_SCHEMA:
        raise ValueError("unsupported data audit schema")
    if any(key in audit for key in ("profile", "registry", "source_identity")) or any(
            any(key in row for key in ("domain", "role", "source_key")) for row in audit.get("rows", [])):
        raise ValueError("legacy audit cannot contain two-domain identities")
    payload = {key: value for key, value in audit.items() if key != "audit_sha256"}
    if audit.get("audit_sha256") != canonical_hash(payload):
        raise ValueError("data audit hash mismatch")
    if audit.get("status") != "ready_for_feature_export" or audit.get("issues"):
        raise ValueError("data audit is insufficient")
    if audit.get("label_contract") != LABEL_CONTRACT:
        raise ValueError("unsupported label contract")
    split = validate_split(audit.get("split"), alternative_confirmation=audit.get("alternative_confirmation"))
    for key in ("hdf5_path", "init_states_path", "bddl_path"):
        _require_hash(audit["assets"][key]["sha256"])
    validate_group_rows(audit["rows"], split)
    trajectories = {item["trajectory_id"]: item for item in audit["trajectories"]}
    if len(trajectories) != len(audit["trajectories"]):
        raise ValueError("duplicate trajectory mapping")
    if {t["source_index"] for t in trajectories.values()} != {i for indices in split.values() for i in indices}:
        raise ValueError("audit lacks source coverage")
    for item in trajectories.values():
        _require_hash(item.get("source_state_sha256"))
        _require_hash(item.get("trajectory_initial_state_sha256"))
        method, evidence = item.get("method"), item.get("evidence", {})
        if method == "exact_state":
            if item.get("source_state_sha256") != item.get("trajectory_initial_state_sha256"):
                raise ValueError("exact source mapping evidence differs")
        elif method == "collection_provenance":
            required = {"hdf5_sha256": audit["assets"]["hdf5_path"]["sha256"],
                        "init_states_sha256": audit["assets"]["init_states_path"]["sha256"],
                        "trajectory_id": item["trajectory_id"], "source_index": item["source_index"],
                        "source_state_sha256": item["source_state_sha256"],
                        "trajectory_initial_state_sha256": item["trajectory_initial_state_sha256"],
                        "manually_confirmed": True}
            if any(type(evidence.get(k)) is not type(v) or evidence.get(k) != v for k, v in required.items()):
                raise ValueError("collection provenance identity differs")
            if any(not isinstance(evidence.get(k), str) or not evidence[k].strip()
                   for k in ("collection_record_source", "reviewer", "confirmation_reason")):
                raise ValueError("collection provenance lacks explicit confirmation")
        else:
            raise ValueError("unsupported source mapping evidence")
    for row in audit["rows"]:
        _require_hash(row["state_sha256"])
        mapping = trajectories.get(row["trajectory_id"])
        if not mapping or (mapping["source_index"], mapping["split"]) != (row["source_index"], row["split"]):
            raise ValueError("row/trajectory mapping differs")
        expected = derive_label(row["current"], row.get("hold_evidence"), state_digest=row["state_sha256"])
        if type(row.get("label")) is not type(expected["label"]) or row.get("label") != expected["label"] or row.get("reason") != expected["reason"]:
            raise ValueError("cached row label differs from evaluator/hold evidence")
        if row.get("original_instruction_sha256") != hashlib.sha256(audit["original_instruction"].encode()).hexdigest():
            raise ValueError("instruction identity differs")
        if base_dir is not None:
            _legal_observation(load_observation_artifact(base_dir, row["observation"]))
    for name in ("train", "validation"):
        if {row["label"] for row in audit["rows"] if row["split"] == name and row["label"] is not None} != {0, 1}:
            raise ValueError("audit lacks both label classes")
    return audit


def validate_domain_rows(rows, registry):
    """Check source ownership and direct state/observation duplicates, not ancestry."""
    from .data_profiles import HEAD_DOMAIN
    from .data_registry import validate_source_registry
    validate_source_registry(registry)
    if not isinstance(rows, list):
        raise ValueError("domain rows must be a list")
    records = {row["source_key"]: row for row in registry["head_registry"]["records"]}
    seen_ids, states, observations = set(), {}, {}
    for row in rows:
        if not isinstance(row, dict) or any(key in row for key in ("source_index", "split")):
            raise ValueError("domain rows cannot contain legacy source identities")
        source = records.get(row.get("source_key"))
        if (not source or row.get("domain") != HEAD_DOMAIN or row.get("role") not in {"head_train", "head_validation"}
                or source["role"] != row["role"] or source["trajectory_id"] != row.get("trajectory_id")
                or row.get("edited_variant", False) is not False):
            raise ValueError("head row has wrong source domain, role or edited evaluation provenance")
        step = row.get("saved_state_index")
        if (type(step) is not int or step not in source["sampled_frame_indices"]
                or row.get("state_sha256") != source["state_sha256s"][step]
                or row.get("model_xml_sha256") != source["model_xml_sha256"]):
            raise ValueError("head row frame/state/XML differs from registered HDF")
        expected_id = f"{source['source_key']}:frame:{step}"
        if row.get("row_id") != expected_id or expected_id in seen_ids:
            raise ValueError("duplicate or incorrect domain row identity")
        seen_ids.add(expected_id)
        digest = row["state_sha256"]
        if digest in states and states[digest] != row["role"]:
            raise ValueError("direct saved-state duplicate across head groups")
        states[digest] = row["role"]
        observation = row.get("observation")
        observation_hash = observation.get("observation_sha256") if isinstance(observation, dict) else row.get("raw_observation_sha256")
        _require_hash(observation_hash)
        if observation_hash in observations and observations[observation_hash] != row["role"]:
            raise ValueError("direct raw-observation duplicate across head groups")
        observations[observation_hash] = row["role"]
    return rows


def _domain_coverage(registry, rows):
    from .data_profiles import HEAD_DOMAIN, EVAL_DOMAIN
    head = {}
    for role, keys in registry["head_registry"]["groups"].items():
        selected = [row for row in rows if row["role"] == role]
        expected = sum(len(row["sampled_frame_indices"]) for row in registry["head_registry"]["records"] if row["role"] == role)
        head[role] = {"sources": len(keys), "expected_sampled_frames": expected,
            "audited_frames": len(selected), "labels": {str(label): sum(row["label"] == label for row in selected)
                for label in (0, 1, None)}}
    return {HEAD_DOMAIN: head, EVAL_DOMAIN: {role: {"sources": len(keys), "restored_frames": 0}
        for role, keys in registry["eval_registry"]["groups"].items()}}


def _domain_hold_steps(evidence):
    trace = evidence.get("trace") if isinstance(evidence, dict) else None
    return max(0, len(trace)-1) if isinstance(trace, list) else 0


def _audit_domain_demonstrations(config, *, provider_factory=None, out=None):
    from .data_profiles import HEAD_DOMAIN
    from .data_registry import build_source_registry, source_identity, validate_source_registry
    plan = audit_plan(config)
    destination = Path(out) if out is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": DOMAIN_AUDIT_SCHEMA, "status": "insufficient", "plan": plan,
        "profile": copy.deepcopy(plan["profile"]), "registry": None, "source_identity": None,
        "original_instruction": config["original_instruction"], "label_contract": copy.deepcopy(LABEL_CONTRACT),
        "rows": [], "issues": [], "assets": {}, "provider_execution_requested": provider_factory is not None,
        "ancestry_independence": "unproven", "provider_identity": {},
        "limitations": ["HDF/eval initial-state physical ancestry independence is unproven.",
            "Trajectory grouping applies to the new head, not the frozen SOG10 backbone.",
            "Successful demonstrations do not establish failure/stall-negative coverage."],
        "work_counts": {"restore_attempts": 0, "hold_attempts": 0}}
    provider = None
    try:
        registry = build_source_registry(config)
        report.update(registry=registry, source_identity=source_identity(registry), assets=copy.deepcopy(registry["assets"]))
        if destination is not None:
            _write(destination / "registry.json", registry)
        if provider_factory is None or destination is None:
            report["issues"].append({"reason": "file_only_registry_not_physical_audit"})
        else:
            indexed = {item["trajectory_id"]: item for item in read_demonstrations(config["hdf5_path"])}
            validate_source_registry(registry, verify_files=True)
            provider = provider_factory(config)
            provider_identity = copy.deepcopy(getattr(provider, "metadata", {}))
            canonical_hash(provider_identity)
            report["provider_identity"] = provider_identity
            for source in registry["head_registry"]["records"]:
                if source["role"] not in {"head_train", "head_validation"}:
                    continue
                trajectory = indexed[source["trajectory_id"]]
                for step in source["sampled_frame_indices"]:
                    state = trajectory["states"][step].copy()
                    digest = state_sha256(state)
                    if digest != source["state_sha256s"][step]:
                        raise ValueError("HDF frame changed after source registration")
                    report["work_counts"]["restore_attempts"] += 1
                    restored = provider.restore_demonstration(state.copy(), model_xml=trajectory["model_xml"])
                    observation = copy.deepcopy(_legal_observation(restored["observation"]))
                    current = {key: copy.deepcopy(restored.get(key)) for key in ("goals", "released", "release_evidence")}
                    canonical_hash(current)
                    _truth(current)
                    if step == 0 and any(current["goals"]):
                        raise ValueError("normal HDF demonstration must begin at actual mask00")
                    # Save the actual current input before any independently restored hold branch.
                    reference = save_observation_artifact(destination, f"observations/{len(report['rows']):08d}.npz", observation)
                    row = {"row_id": f"{source['source_key']}:frame:{step}", "domain": HEAD_DOMAIN,
                        "role": source["role"], "source_key": source["source_key"], "trajectory_id": source["trajectory_id"],
                        "saved_state_index": step, "state_sha256": digest, "model_xml_sha256": source["model_xml_sha256"],
                        "observation": reference, "current": current, "hold_evidence": None,
                        "original_instruction_sha256": hashlib.sha256(config["original_instruction"].encode()).hexdigest()}
                    row.update(derive_label(current, None, state_digest=digest))
                    report["rows"].append(row)
                    if all(current["goals"]) and current["released"] is True:
                        report["work_counts"]["hold_attempts"] += 1
                        hold = provider.capture_hold_label(state.copy(), 4, model_xml=trajectory["model_xml"])
                        if hold is not None and not isinstance(hold, dict):
                            raise ValueError("passive hold provider must return a JSON object or unknown None")
                        canonical_hash(hold)
                        row["hold_evidence"] = copy.deepcopy(hold)
                    row.update(derive_label(current, row["hold_evidence"], state_digest=digest))
            validate_domain_rows(report["rows"], registry)
            report["class_coverage"] = {role: {str(label): sum(row["role"] == role and row["label"] == label
                for row in report["rows"]) for label in (0, 1, None)} for role in ("head_train", "head_validation")}
            for role, counts in report["class_coverage"].items():
                if not counts["0"] or not counts["1"]:
                    report["issues"].append({"reason": "label_class_coverage_insufficient", "role": role})
            if not report["issues"]:
                report["status"] = "ready_for_feature_export"
        validate_source_registry(registry, verify_files=True)
    except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as error:
        report["status"] = "insufficient"
        report["issues"].append({"reason": "audit_error", "type": type(error).__name__, "message": str(error)})
    except (KeyboardInterrupt, SystemExit) as error:
        report["status"] = "interrupted"
        report["issues"].append({"reason": "audit_interrupted", "type": type(error).__name__})
        raise
    finally:
        if provider is not None and callable(getattr(provider, "close", None)):
            try:
                provider.close()
            except Exception as error:
                report["status"] = "insufficient"
                report["issues"].append({"reason": "provider_close_error", "type": type(error).__name__, "message": str(error)})
        report["work_counts"].update(current_observations=len(report["rows"]),
            hold_branches=sum(row["hold_evidence"] is not None for row in report["rows"]),
            recorded_hold_steps=sum(_domain_hold_steps(row["hold_evidence"]) for row in report["rows"]),
            eligible_feature_forwards=sum(row["label"] is not None for row in report["rows"]))
        if report["registry"] is not None:
            try:
                validate_source_registry(report["registry"], verify_files=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                report["status"] = "insufficient"
                report["issues"].append({"reason": "source_asset_changed", "type": type(error).__name__, "message": str(error)})
            report["coverage"] = _domain_coverage(report["registry"], report["rows"])
        report["audit_sha256"] = canonical_hash(report)
        if destination is not None:
            _write(destination / "audit.json", report)
    return report


def _validate_domain_audit(audit, *, base_dir=None):
    from .data_registry import validate_source_registry, source_identity
    from .data_profiles import validate_profile
    if any(key in audit for key in ("split", "alternative_confirmation", "trajectories", "trajectory_source_map")):
        raise ValueError("two-domain audit cannot mix legacy source mappings")
    if audit.get("audit_sha256") != canonical_hash({k: v for k, v in audit.items() if k != "audit_sha256"}):
        raise ValueError("two-domain audit hash mismatch")
    if audit.get("status") != "ready_for_feature_export" or audit.get("issues"):
        raise ValueError("two-domain data audit is insufficient")
    if audit.get("label_contract") != LABEL_CONTRACT or audit.get("ancestry_independence") != "unproven":
        raise ValueError("two-domain label/ancestry contract differs")
    # New training/export paths require the declared source files still to exist
    # with their actual registered bytes, not merely a self-consistent old JSON.
    registry = validate_source_registry(audit.get("registry"), verify_files=True)
    if (validate_profile(audit.get("profile")) != registry["profile"] or audit.get("assets") != registry["assets"]
            or audit.get("source_identity") != source_identity(registry)):
        raise ValueError("audit source-domain binding differs from registry")
    if audit.get("provider_execution_requested") is not True:
        raise ValueError("file-only registry cannot be used for feature export")
    rows = validate_domain_rows(audit.get("rows"), registry)
    expected_ids = {f"{source['source_key']}:frame:{step}" for source in registry["head_registry"]["records"]
                    for step in source["sampled_frame_indices"]}
    if {row["row_id"] for row in rows} != expected_ids:
        raise ValueError("audit omits declared head sampled frames")
    if not isinstance(audit.get("original_instruction"), str) or not audit["original_instruction"].strip():
        raise ValueError("audit lacks original instruction")
    for row in rows:
        expected = derive_label(row["current"], row.get("hold_evidence"), state_digest=row["state_sha256"])
        if (type(row.get("label")) is not type(expected["label"]) or row["label"] != expected["label"]
                or row.get("reason") != expected["reason"]):
            raise ValueError("cached domain label differs from physical evaluator/hold evidence")
        if row["saved_state_index"] == 0 and any(row["current"]["goals"]):
            raise ValueError("normal HDF first frame is not mask00")
        if row.get("original_instruction_sha256") != hashlib.sha256(audit["original_instruction"].encode()).hexdigest():
            raise ValueError("original instruction identity differs")
        if base_dir is not None:
            _legal_observation(load_observation_artifact(base_dir, row["observation"]))
    expected_coverage = _domain_coverage(registry, rows)
    if audit.get("coverage") != expected_coverage:
        raise ValueError("domain audit coverage differs from its rows")
    for role in ("head_train", "head_validation"):
        counts = expected_coverage["head_demonstration"][role]["labels"]
        if not counts["0"] or not counts["1"] or audit.get("class_coverage", {}).get(role) != counts:
            raise ValueError("domain audit lacks both known label classes or accurate class counts")
    expected_work = {"restore_attempts": len(rows),
        "hold_attempts": sum(all(row["current"]["goals"]) and row["current"]["released"] is True for row in rows),
        "current_observations": len(rows), "hold_branches": sum(row["hold_evidence"] is not None for row in rows),
        "recorded_hold_steps": sum(_domain_hold_steps(row["hold_evidence"]) for row in rows),
        "eligible_feature_forwards": sum(row["label"] is not None for row in rows)}
    if audit.get("work_counts") != expected_work:
        raise ValueError("physical audit work counts differ from its evidence")
    return audit


def _identities(audit, base_identity):
    if not isinstance(base_identity, dict) or not base_identity:
        raise ValueError("base checkpoint/code identity is required")
    if audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA:
        from .data_registry import source_identity
        registry = audit["registry"]
        return {"base_identity": copy.deepcopy(base_identity),
                "data_identity": {"audit_sha256": audit["audit_sha256"], "assets": copy.deepcopy(audit["assets"]),
                                  "profile_sha256": registry["profile_sha256"],
                                  "registry_sha256": registry["registry_sha256"]},
                "split_identity": source_identity(registry),
                "label_contract": copy.deepcopy(LABEL_CONTRACT)}
    return {"base_identity": copy.deepcopy(base_identity),
            "data_identity": {"audit_sha256": audit["audit_sha256"], "assets": audit["assets"]},
            "split_identity": {"split": audit["split"], "sha256": canonical_hash(audit["split"]),
                               "alternative_confirmation": audit.get("alternative_confirmation")},
            "label_contract": copy.deepcopy(LABEL_CONTRACT)}


DOMAIN_CACHE_SCHEMA = "remaining-finish-feature-cache-v2"


def validate_head_identities(value):
    """Check head metadata without importing torch, loading weights or restoring physics."""
    fields = {"base_identity", "data_identity", "split_identity", "label_contract"}
    if (not isinstance(value, dict) or set(value) != fields
            or any(not isinstance(item, dict) or not item for item in value.values())):
        raise ValueError("head identities require nonempty base/data/split/label-contract objects")
    canonical_hash(value)
    split, dataset = value["split_identity"], value["data_identity"]
    markers = {"schema_version", "profile", "profile_sha256", "registry_sha256", "head_registry_sha256",
               "eval_registry_sha256", "groups", "ancestry_independence"}
    if set(split).intersection(markers) or set(dataset).intersection({"profile_sha256", "registry_sha256"}):
        from .data_registry import validate_source_identity
        validate_source_identity(split)
        if set(dataset) != {"audit_sha256", "assets", "profile_sha256", "registry_sha256"}:
            raise ValueError("domain head data identity is incomplete or mixed with legacy fields")
        _require_hash(dataset["audit_sha256"])
        for key in ("profile_sha256", "registry_sha256"):
            if dataset[key] != split[key]:
                raise ValueError("head data/source-domain identity differs")
        assets = dataset["assets"]
        if (not isinstance(assets, dict) or set(assets) != {"hdf5_path", "init_states_path", "bddl_path"}
                or any(not isinstance(asset, dict) for asset in assets.values())):
            raise ValueError("domain head asset identity is incomplete")
        expected_assets = {key: assets[field].get("sha256") for key, field in (
            ("hdf5_sha256", "hdf5_path"), ("init_states_sha256", "init_states_path"), ("bddl_sha256", "bddl_path"))}
        if expected_assets != split["assets"] or value["label_contract"] != LABEL_CONTRACT:
            raise ValueError("head source assets or physical label contract differs")
    return copy.deepcopy(value)


def _feature_row(row, audit):
    if audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA:
        return row.get("domain") == "head_demonstration" and row.get("role") in {"head_train", "head_validation"}
    return row.get("split") in {"train", "validation"}


def _feature_identity_fields(audit):
    if audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA:
        return ("domain", "role", "source_key", "trajectory_id", "saved_state_index", "state_sha256",
                "model_xml_sha256", "label")
    return ("source_index", "trajectory_id", "state_sha256", "split", "label")


def _validate_feature_rows(rows, audit):
    if audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA:
        validate_domain_rows(rows, audit["registry"])
    else:
        validate_group_rows(rows, audit["split"])


def _input_evidence(base_dir, row):
    arrays = load_observation_artifact(base_dir, row["input_artifact"])
    value = {"schema_version": "remaining-finish-input-v1", **arrays,
             "tensor_dtypes": row["input_tensor_dtypes"]}
    validate_input_evidence(value)
    if row.get("input_sha256") != input_sha256(value):
        raise ValueError("feature input hash mismatch")
    return value


def save_feature_cache(out, features, *, rows, audit, base_identity, feature_version=FEATURE_VERSION):
    """Write a typed NPZ and signed metadata; rows must already carry input evidence.

    Caller creates/copies observation artifacts in the *new* output directory.
    No labels supplied by a model or cache are accepted without audit recomputation.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    validate_audit(audit, base_dir=out)
    if feature_version != FEATURE_VERSION:
        raise ValueError("unsupported feature version")
    features = np.asarray(features)
    if features.dtype != np.float32 or features.ndim != 2 or not all(features.shape) or not np.isfinite(features).all():
        raise ValueError("features must be finite nonempty NxD float32")
    if len(rows) != len(features):
        raise ValueError("feature row count differs")
    audit_rows = {row["row_id"]: row for row in audit["rows"]}
    labels = []
    for row in rows:
        source = audit_rows.get(row.get("row_id"))
        if not source or source["label"] is None or not _feature_row(source, audit):
            raise ValueError("feature rows require audited train/validation labels")
        for key in _feature_identity_fields(audit):
            if type(row.get(key)) is not type(source[key]) or row.get(key) != source[key]:
                raise ValueError("feature row identity differs from audited row")
        _input_evidence(out, row)
        if row.get("raw_observation_sha256") != source["observation"]["observation_sha256"]:
            raise ValueError("raw observation identity differs")
        labels.append(source["label"])
    _validate_feature_rows(rows, audit)
    if {r["row_id"] for r in rows} != {r["row_id"] for r in audit["rows"]
            if r["label"] is not None and _feature_row(r, audit)}:
        raise ValueError("feature export omitted an eligible audited row")
    with (out / "features.npz").open("xb") as stream:
        np.savez_compressed(stream, features=features, labels=np.asarray(labels, dtype=np.uint8))
    schema = DOMAIN_CACHE_SCHEMA if audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA else CACHE_SCHEMA
    manifest = {"schema_version": schema, "feature_version": feature_version, "rows": copy.deepcopy(rows),
                "shape": list(features.shape), "dtype": "float32", "features_path": "features.npz",
                "features_sha256": _file_hash(out / "features.npz"), "audit": copy.deepcopy(audit),
                "identities": _identities(audit, base_identity)}
    manifest["cache_sha256"] = canonical_hash(manifest)
    _write(out / "cache.json", manifest)
    return manifest


def load_feature_cache(path, *, audit=None, expected_base_identity=None, allowed_splits=None, allowed_roles=None,
                       expected_source_identity=None):
    path = Path(path)
    path = path / "cache.json" if path.is_dir() else path
    manifest = read_json(path)
    if manifest.get("schema_version") not in {CACHE_SCHEMA, DOMAIN_CACHE_SCHEMA} or manifest.get("feature_version") != FEATURE_VERSION:
        raise ValueError("unsupported feature cache schema/version")
    if manifest.get("cache_sha256") != canonical_hash({k: v for k, v in manifest.items() if k != "cache_sha256"}):
        raise ValueError("feature cache manifest hash mismatch")
    embedded = validate_audit(manifest["audit"], base_dir=path.parent)
    domain_cache = manifest["schema_version"] == DOMAIN_CACHE_SCHEMA
    if domain_cache != (embedded["schema_version"] == DOMAIN_AUDIT_SCHEMA):
        raise ValueError("feature cache/audit source-domain versions differ")
    if (domain_cache and allowed_splits is not None) or (not domain_cache and allowed_roles is not None):
        raise ValueError("new source-domain roles and legacy splits cannot be mixed")
    if audit is not None and canonical_hash(embedded) != canonical_hash(audit):
        raise ValueError("feature cache belongs to another data audit")
    identity = manifest["identities"]
    if identity != _identities(embedded, identity.get("base_identity")):
        raise ValueError("feature identity differs from audit")
    if expected_base_identity is not None and identity["base_identity"] != expected_base_identity:
        raise ValueError("feature cache base identity mismatch")
    if expected_source_identity is not None and identity["split_identity"] != expected_source_identity:
        raise ValueError("feature cache source identity mismatch")
    raw = _contained(path.parent, manifest["features_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["features_sha256"]:
        raise ValueError("feature NPZ hash mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (sorted(item.filename for item in members) != ["features.npy", "labels.npy"]
                or sum(item.file_size for item in members) > 2 * 1024 ** 3):
            raise ValueError("unexpected or oversized feature NPZ members")
    with np.load(io.BytesIO(raw), allow_pickle=False) as packed:
        if set(packed.files) != {"features", "labels"}:
            raise ValueError("unexpected fields in feature cache")
        features, labels = packed["features"].copy(), packed["labels"].copy()
    if (features.dtype != np.float32 or features.ndim != 2 or not all(features.shape)
            or not np.isfinite(features).all() or list(features.shape) != manifest["shape"]
            or labels.dtype != np.uint8 or labels.shape != (len(features),) or not np.isin(labels, [0, 1]).all()):
        raise ValueError("invalid feature dimensions/dtype/finite values or labels")
    rows = manifest["rows"]
    if len(rows) != len(features):
        raise ValueError("feature metadata count differs")
    _validate_feature_rows(rows, embedded)
    sources = {row["row_id"]: row for row in embedded["rows"]}
    for row, label in zip(rows, labels.tolist()):
        source = sources.get(row["row_id"])
        if not source or source["label"] is None or not _feature_row(source, embedded):
            raise ValueError("feature row is not an audited training/validation state")
        for key in _feature_identity_fields(embedded):
            if type(row.get(key)) is not type(source[key]) or row.get(key) != source[key]:
                raise ValueError("feature row source/label changed")
        if (label != source["label"] or (allowed_splits is not None and row["split"] not in allowed_splits)
                or (allowed_roles is not None and row["role"] not in allowed_roles)):
            raise ValueError("feature label or allowed split mismatch")
        _input_evidence(path.parent, row)
        if row.get("raw_observation_sha256") != source["observation"]["observation_sha256"]:
            raise ValueError("raw observation identity differs")
    if {r["row_id"] for r in rows} != {r["row_id"] for r in embedded["rows"]
            if r["label"] is not None and _feature_row(r, embedded)}:
        raise ValueError("feature cache omitted an eligible audited row")
    return {"features": features, "labels": labels, "rows": rows, "identities": identity, "manifest": manifest}


def export_features(audit_dir, policy, out, *, base_identity):
    """User-run export using one forward per known train/validation input.

    policy.predict_features receives only the saved legal observation and original
    instruction. Caller owns policy lifetime (including subprocess cleanup).
    """
    audit_dir, out = Path(audit_dir), Path(out)
    audit = validate_audit(read_json(audit_dir / "audit.json"), base_dir=audit_dir)
    out.mkdir(parents=True, exist_ok=False)
    copied = copy.deepcopy(audit)
    for row in copied["rows"]:
        reference = row["observation"]
        load_observation_artifact(audit_dir, reference)
        raw = _contained(audit_dir, reference["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("audit observation changed during export")
        destination = _contained(out, reference["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
    rows, features = [], []
    for source in copied["rows"]:
        if source["label"] is None or not _feature_row(source, copied):
            continue
        observation = _legal_observation(load_observation_artifact(out, source["observation"]))
        predict = getattr(policy, "predict_features", None) or policy.predict
        result = predict(observation, copied["original_instruction"])
        feature = np.asarray(result["features"])
        if feature.ndim == 2 and feature.shape[0] == 1:
            feature = feature[0]
        if feature.dtype != np.float32 or feature.ndim != 1 or not feature.size or not np.isfinite(feature).all():
            raise ValueError("policy returned invalid read-only pooled features")
        evidence = validate_input_evidence(result["input_evidence"])
        inputs = {key: evidence[key] for key in ("tensors", "crops")}
        reference = save_observation_artifact(out, f"inputs/{len(rows):08d}.npz", inputs)
        row = {key: copy.deepcopy(source[key]) for key in ("row_id", *_feature_identity_fields(copied))}
        row.update(input_artifact=reference, input_sha256=input_sha256(evidence),
                   input_tensor_dtypes=evidence["tensor_dtypes"],
                   raw_observation_sha256=source["observation"]["observation_sha256"])
        rows.append(row)
        features.append(feature.copy())
    if not features:
        raise ValueError("no labelled training/validation features")
    return save_feature_cache(out, np.stack(features), rows=rows, audit=copied, base_identity=base_identity)
