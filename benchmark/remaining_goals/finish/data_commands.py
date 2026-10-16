"""Explicit user-run feature/parity stages using one isolated model worker.

This module intentionally does not import torch or the heavy OFT adapter.
Commands never restore a physical environment, train a head, or chain into eval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from ..isolated_policy import SubprocessPolicy
from ..observation_artifact import load_observation_artifact, save_observation_artifact
from .data import (DOMAIN_AUDIT_SCHEMA, FEATURE_VERSION, _contained, _legal_observation, _identities, _feature_row,
                   _feature_identity_fields, canonical_hash,
                   export_features, read_json, validate_audit)
from .schema import input_sha256, validate_policy_result


def _write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _config(value):
    if isinstance(value, (str, Path)):
        path = Path(value).absolute()
        config = read_json(path)
        base = path.parent
    else:
        config = copy.deepcopy(value)
        base = Path.cwd()
    if not isinstance(config, dict):
        raise ValueError("runtime config must be a JSON object")
    for block, keys in (("runtime", ("python_executable",)),
                        ("adapter_options", ("repo_path", "checkpoint"))):
        if not isinstance(config.get(block), dict):
            raise ValueError(f"runtime config lacks {block}")
        for key in keys:
            raw = config[block].get(key)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError(f"runtime config needs {block}.{key}")
            path = Path(raw).expanduser()
            # abspath, not resolve: resolving a venv Python symlink loses its environment.
            config[block][key] = os.path.abspath(path if path.is_absolute() else base / path)
    if config.get("suite") != "libero_10" or config.get("adapter_options", {}).get("suite") != "libero_10":
        raise ValueError("this FINISH data stage is limited to the original LIBERO-10 OFT")
    if config.get("execution", {}).get("random_seed") != 7:
        raise ValueError("FINISH data/parity protocol requires seed 7")
    return config


def _worker_identity(policy):
    provenance = copy.deepcopy(policy.provenance)
    metadata = provenance.get("policy_metadata")
    if not isinstance(metadata, dict) or metadata.get("feature_version") != FEATURE_VERSION:
        raise ValueError("model worker did not identify the required feature interface")
    identity = metadata.get("base_identity")
    if not isinstance(identity, dict) or not identity:
        raise ValueError("model worker lacks actual base checkpoint/code identity")
    if metadata.get("base_identity_sha256") != canonical_hash(identity):
        raise ValueError("model worker base identity digest differs")
    return provenance, metadata, identity


def feature_export_command(audit_dir, runtime_config, out):
    """Export a new cache, preserving partial output and closing on all exits.

    Returns a JSON report; interrupted/error/insufficient stages do not contain a
    completed cache claim. The caller converts this status to its CLI exit code.
    """
    audit_dir, out = Path(audit_dir), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    path = out / "feature_export.json"
    report = {"schema_version": "remaining-finish-feature-export-command-v1", "status": "planned",
              "cache_path": None, "model_loads": 0, "completed": False, "error": None}
    policy = None
    try:
        audit = validate_audit(read_json(audit_dir / "audit.json"), base_dir=audit_dir)
        config = _config(runtime_config)
        config["policy_factory"] = "benchmark.remaining_goals.finish.oft:make_feature_policy"
        config.pop("finish", None)
        report.update(audit_sha256=audit["audit_sha256"], runtime_config_sha256=canonical_hash(config),
                      expected_forwards=sum(row["label"] is not None and _feature_row(row, audit)
                                            for row in audit["rows"]))
        if audit["schema_version"] == DOMAIN_AUDIT_SCHEMA:
            from .data_registry import source_identity
            report.update(schema_version="remaining-finish-feature-export-command-v2",
                          source_identity=source_identity(audit["registry"]))
        _write(path, report)
        policy = SubprocessPolicy(config)
        report["model_loads"] = 1
        provenance, _, identity = _worker_identity(policy)
        report.update(status="running", policy_provenance=provenance)
        _write(path, report)
        policy.reset()
        cache = export_features(audit_dir, policy, out / "cache", base_identity=identity)
        report.update(status="completed", completed=True, cache_path="cache/cache.json",
                      cache_sha256=cache["cache_sha256"], completed_forwards=len(cache["rows"]))
    except BaseException as error:
        report.update(status="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "error",
                      error={"type": type(error).__name__, "message": str(error)})
    finally:
        if policy is not None:
            try:
                policy.close()
            except Exception as error:
                report.update(status="error", completed=False,
                              close_error={"type": type(error).__name__, "message": str(error)})
        report["report_sha256"] = canonical_hash(report)
        _write(path, report)
    return report


def _validation_selection(audit):
    """Deterministic round-robin sources, unique state and raw-observation hashes."""
    grouped = {}
    domain = audit.get("schema_version") == DOMAIN_AUDIT_SCHEMA
    for row in audit["rows"]:
        if domain:
            if row.get("domain") == "head_demonstration" and row.get("role") == "head_validation":
                grouped.setdefault(row["source_key"], []).append(row)
        elif row["split"] == "validation":
            grouped.setdefault(row["source_index"], []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: (r["trajectory_id"], r["saved_state_index"], r["row_id"]))
    ordered, used_states, used_observations = [], set(), set()
    index = 0
    while any(index < len(rows) for rows in grouped.values()) and len(ordered) < 32:
        for source in sorted(grouped):
            rows = grouped[source]
            if index >= len(rows):
                continue
            row = rows[index]
            digest = row["observation"]["observation_sha256"]
            if row["state_sha256"] in used_states or digest in used_observations:
                continue
            ordered.append(copy.deepcopy(row))
            used_states.add(row["state_sha256"])
            used_observations.add(digest)
            if len(ordered) == 32:
                break
        index += 1
    return ordered


def _head_manifest(path):
    path = Path(path)
    path = path / "head.json" if path.is_dir() else path
    manifest = read_json(path)
    if manifest.get("artifact_sha256") != canonical_hash({k: v for k, v in manifest.items() if k != "artifact_sha256"}):
        raise ValueError("head artifact identity mismatch")
    return path, manifest


def parity_command(audit_dir, runtime_config, head_artifact, out, atol=0, rtol=0):
    """Compare 32 fixed validation inputs through an original/shadow paired worker.

    Tolerances and input identities are persisted before the model worker starts.
    Each input uses exactly one original and one shadow forward inside that
    worker, where Python/NumPy/Torch/CUDA RNG can actually be restored. This is
    action parity only, not physical stopping or independent model quality.
    """
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in (atol, rtol)):
        raise ValueError("parity tolerances must be predeclared finite nonnegative numbers")
    audit_dir, out = Path(audit_dir), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    path = out / "parity.json"
    report = {"schema_version": "remaining-finish-parity-command-v1", "status": "planned", "passed": False,
              "expected": 32, "completed": 0, "model_loads": 0, "calls_per_input": {"original": 1, "shadow": 1},
              "tolerance": {"atol": float(atol), "rtol": float(rtol)}, "pairs": [], "error": None}
    policy = None
    try:
        audit = validate_audit(read_json(audit_dir / "audit.json"), base_dir=audit_dir)
        rows = _validation_selection(audit)
        selection = {"schema_version": "remaining-finish-parity-selection-v1", "audit_sha256": audit["audit_sha256"],
                     "rule": "source-round-robin-trajectory-step-unique-state-and-raw-observation-v1",
                     "rows": rows, "instruction": audit["original_instruction"], "tolerance": report["tolerance"]}
        domain = audit["schema_version"] == DOMAIN_AUDIT_SCHEMA
        if domain:
            from .data_registry import source_identity
            source = source_identity(audit["registry"])
            selection.update(schema_version="remaining-finish-parity-selection-v2",
                             rule="head-validation-source-key-round-robin-unique-state-and-raw-observation-v2",
                             domain="head_demonstration", role="head_validation", source_identity=source)
            report.update(schema_version="remaining-finish-parity-command-v2", source_identity=copy.deepcopy(source))
        selection["selection_sha256"] = canonical_hash(selection)
        _write(out / "inputs.json", selection)
        report.update(selection_sha256=selection["selection_sha256"], selected=len(rows), audit_sha256=audit["audit_sha256"])
        _write(path, report)
        if len(rows) != 32:
            report.update(status="insufficient", error={"type": "InsufficientValidationInputs",
                          "message": "fewer than 32 distinct audited validation observations; no test borrowing or replacement"})
        else:
            config = _config(runtime_config)
            head_path, head = _head_manifest(head_artifact)
            identities = head.get("identities", {})
            if domain:
                expected = _identities(audit, identities.get("base_identity"))
                if (head.get("schema_version") != "remaining-finish-head-v2" or identities != expected
                        or head.get("identity_sha256") != {key: canonical_hash(value) for key, value in expected.items()}):
                    raise ValueError("parity head/audit source-domain identities differ")
            else:
                if head.get("schema_version") != "remaining-finish-head-v1":
                    raise ValueError("legacy parity cannot use a new source-domain head")
                if identities.get("data_identity", {}).get("audit_sha256") != audit["audit_sha256"]:
                    raise ValueError("parity validation inputs differ from the head's frozen data audit")
                if identities.get("split_identity", {}).get("split") != audit["split"]:
                    raise ValueError("parity validation split differs from the head's frozen split")
            config["policy_factory"] = "benchmark.remaining_goals.finish.oft:make_parity_policy"
            config["finish"] = {"head_artifact": str(head_path.absolute()), "threshold": 0.5,
                                "threshold_identity": {"purpose": "action-parity-only-not-calibration"}}
            report.update(runtime_config_sha256=canonical_hash(config), head_artifact_sha256=head["artifact_sha256"])
            _write(path, report)
            policy = SubprocessPolicy(config)
            report["model_loads"] = 1
            provenance, metadata, base_identity = _worker_identity(policy)
            if metadata.get("purpose") != "same-worker-action-parity" or metadata.get("calls_per_input") != {"original": 1, "shadow": 1}:
                raise ValueError("parity worker did not declare the original/shadow RNG-paired contract")
            if base_identity != identities.get("base_identity"):
                raise ValueError("parity worker loaded a different base artifact")
            report.update(status="running", policy_provenance=provenance)
            _write(path, report)
            policy.reset()
            for index, row in enumerate(rows):
                observation = _legal_observation(load_observation_artifact(audit_dir, row["observation"]))
                reference = save_observation_artifact(out, f"observations/{index:04d}.npz", observation)
                pair = policy.predict(observation, audit["original_instruction"])
                if pair.get("schema_version") != "remaining-finish-parity-pair-v1" or pair.get("rng_restored_in_model_worker") is not True:
                    raise ValueError("parity pair lacks the in-worker RNG restoration guarantee")
                original = np.asarray(pair["original_actions"])
                shadow = np.asarray(pair["shadow"]["candidate_actions"])
                validated = validate_policy_result(pair["shadow"])
                if (original.shape != (8, 7) or original.dtype.kind not in "fiu" or not np.isfinite(original).all()):
                    raise ValueError("original parity actions must be finite decoded 8x7")
                if validated["head_identity"]["artifact_sha256"] != head["artifact_sha256"]:
                    raise ValueError("parity query used a different head")
                if validated["head_identity"]["base_identity_sha256"] != canonical_hash(base_identity):
                    raise ValueError("parity query used a different base")
                error = np.abs(original.astype(np.float64) - shadow.astype(np.float64))
                matches = bool(np.allclose(original, shadow, atol=atol, rtol=rtol, equal_nan=False))
                pair_path = f"pairs/{index:04d}.npz"
                target = _contained(out, pair_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    np.savez_compressed(stream, original_actions=original, shadow_actions=shadow)
                actual = validated["input_evidence"]
                actual_reference = save_observation_artifact(out, f"inputs/{index:04d}.npz",
                                                             {key: actual[key] for key in ("tensors", "crops")})
                row_identity = {"row_id": row["row_id"], "source_index": row["source_index"]} if not domain else {
                    key: copy.deepcopy(row[key]) for key in ("row_id", *_feature_identity_fields(audit))}
                report["pairs"].append({**row_identity,
                    "observation": reference, "input_artifact": actual_reference,
                    "input_tensor_dtypes": actual["tensor_dtypes"], "input_sha256": input_sha256(actual),
                    "actions_path": pair_path, "actions_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "max_abs_error": float(error.max()), "bit_exact": bool(original.dtype == shadow.dtype and original.tobytes() == shadow.tobytes()),
                    "within_predeclared_tolerance": matches})
                report["completed"] = len(report["pairs"])
                _write(path, report)
            unique = len({pair["input_sha256"] for pair in report["pairs"]})
            report.update(status="completed" if unique == 32 else "insufficient", unique_model_inputs=unique,
                          passed=unique == 32 and all(pair["within_predeclared_tolerance"] for pair in report["pairs"]),
                          max_abs_error=max(pair["max_abs_error"] for pair in report["pairs"]))
            if unique != 32:
                report["error"] = {"type": "RepeatedModelInputs", "message": "fixed observations yielded fewer than 32 distinct actual model inputs; no adaptive replacement"}
    except BaseException as error:
        report.update(status="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "error", passed=False,
                      error={"type": type(error).__name__, "message": str(error)})
    finally:
        if policy is not None:
            try:
                policy.close()
            except Exception as error:
                report.update(status="error", passed=False,
                              close_error={"type": type(error).__name__, "message": str(error)})
        report["report_sha256"] = canonical_hash(report)
        _write(path, report)
    return report
