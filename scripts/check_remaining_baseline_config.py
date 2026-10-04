"""Check baseline metadata without importing a factory or loading a model.

The whole JSON object is passed unchanged by ``cli run --policy-config`` to
the user-supplied ``make_policy(config)``. This checker is deliberately not a
model adapter. Paths refer to ``--base-dir`` (the repository root by default).
Readiness verifies declared metadata and local evidence hashes, not the
scientific contents or success claims in those files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "remaining-goals-baseline-config-v1"
MODELS = {
    "openvla": "OpenVLA", "openvla_oft": "OpenVLA-OFT", "pi0": "pi0",
    "pi05": "pi0.5", "groot_n1_7": "GR00T N1.7", "univla": "UniVLA",
}
SUITES = {"libero_spatial", "libero_object", "libero_goal", "libero_10", "libero_90"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?\Z")
FACTORY = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*\Z")
PLACEHOLDERS = {"todo", "tbd", "unknown", "placeholder", "changeme", "null", "none", "n/a", "not_run"}


def check_config(config: dict, *, base_dir: Path = ROOT, config_path: Path | None = None) -> dict:
    """Return template, incomplete, or ready_configuration_only.

Null denotes an unfilled field; blank/placeholder strings are rejected. A
template never becomes ready just because its fields have been populated.
False ``is_template`` is necessary but not sufficient for readiness. Model
and adapter revisions must be immutable Git commit IDs. Local dependency and
regression evidence files must exist and match their recorded SHA-256.
Factories are checked syntactically, never imported or called. Consequently
readiness does not establish compatibility, physical validity, or model skill.
"""
    errors, missing, verified_files = [], [], []
    report = {
        "schema_version": "remaining-goals-baseline-readiness-v1",
        "status": "incomplete", "configuration_ready": False,
        "model_validation_claim": False, "evidence_content_assessed": False,
        "factory_imported": False, "policy_config_transport": "entire_json_object",
        "errors": errors, "missing_fields": missing, "verified_files": verified_files,
        "not_verified": ["factory availability or behavior", "checkpoint bytes or model identity",
                         "model environment availability", "regression report contents or success criteria",
                         "semantic validity or execution feasibility of the benchmark states"],
        "notice": "Configuration completeness only; no model, regression result, or dataset is certified.",
    }
    if not isinstance(config, dict):
        errors.append("configuration must be a JSON object")
        return report
    report["model_id"] = config.get("model_id")

    def value(path):
        item = config
        for key in path.split("."):
            if not isinstance(item, dict):
                errors.append(f"{path}: parent must be an object")
                return None
            item = item.get(key)
        return item

    def text_field(path):
        item = value(path)
        if item is None:
            missing.append(path)
            return None
        if not isinstance(item, str) or not item.strip() or item.strip().lower() in PLACEHOLDERS:
            errors.append(f"{path}: must be a nonempty, non-placeholder string")
            return None
        return item

    def digest_field(path):
        item = text_field(path)
        if item is not None and not SHA256.fullmatch(item):
            errors.append(f"{path}: must be a lowercase SHA-256 digest")
            return None
        return item

    def file_binding(path_key, hash_key):
        filename, expected = text_field(path_key), digest_field(hash_key)
        if filename is None or expected is None:
            return
        path = Path(filename)
        if not path.is_absolute():
            path = Path(base_dir) / path
        try:
            if not path.is_file():
                raise ValueError("file does not exist or is not a regular file")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("SHA-256 mismatch")
        except (OSError, ValueError) as error:
            errors.append(f"{path_key}: {error}")
            return
        verified_files.append({"field": path_key, "path": str(path.resolve()), "sha256": actual})

    if config.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    model = config.get("model_id")
    if not isinstance(model, str) or model not in MODELS:
        errors.append("model_id must identify one of the six registered baselines")
    elif config.get("display_name") != MODELS[model]:
        errors.append("display_name must match the registered model_id")
    if type(config.get("is_template")) is not bool:
        errors.append("is_template must be a JSON boolean")
    suite = text_field("suite")
    if suite is not None and suite not in SUITES:
        errors.append("suite must be an official supported LIBERO suite")
    policy_id = text_field("policy_id")
    if policy_id is not None and policy_id.lower() in {str(model).lower(), str(config.get("display_name")).lower()}:
        errors.append("policy_id must identify a checkpoint and method, not just a model family")
    factory = text_field("policy_factory")
    if factory is not None:
        if not FACTORY.fullmatch(factory):
            errors.append("policy_factory must use module:callable syntax")
        if factory.startswith("benchmark.remaining_goals.toy:") or factory.endswith(":DummyPolicy"):
            errors.append("policy_factory cannot be a toy or dummy baseline")
    text_field("checkpoint.uri")
    digest_field("checkpoint.artifact_manifest_sha256")
    for prefix in ("model_code", "adapter_code"):
        text_field(f"{prefix}.repository")
        revision = text_field(f"{prefix}.revision")
        if revision is not None and not REVISION.fullmatch(revision):
            errors.append(f"{prefix}.revision: use a full immutable Git commit, not a branch or tag")
    digest_field("adapter_code.source_sha256")

    cameras = value("observation.camera_keys")
    if cameras is None:
        missing.append("observation.camera_keys")
    elif (not isinstance(cameras, list) or not cameras
          or any(not isinstance(camera, str) or not camera.strip() for camera in cameras)
          or len(set(cameras)) != len(cameras)):
        errors.append("observation.camera_keys must be a nonempty unique string list")
    elif any(camera not in {"agentview_image", "robot0_eye_in_hand_image"} for camera in cameras):
        errors.append("observation.camera_keys contains a camera unavailable from the LIBERO bridge")
    for path in (
        "observation.image_preprocessing", "observation.proprio_preprocessing",
        "action.translation_mapping", "action.rotation_mapping", "action.gripper_mapping",
        "action.stop_behavior", "action.normalization.description", "execution.seed_scope",
        "runtime.python_executable", "runtime.python_version", "runtime.dependency_isolation",
        "evidence.official_00.review_summary", "evidence.new_protocol_00.review_summary",
    ):
        text_field(path)
    mode = text_field("action.normalization.mode")
    if mode is not None and mode not in {"dataset_statistics", "code_defined", "identity"}:
        errors.append("action.normalization.mode must be dataset_statistics, code_defined, or identity")
    if mode in {"dataset_statistics", "code_defined"}:
        text_field("action.normalization.key")
        text_field("action.normalization.reference")
        digest_field("action.normalization.reference_sha256")
    elif mode == "identity":
        text_field("action.normalization.identity_reason")
        if value("action.normalization.key") is not None:
            errors.append("identity normalization must use key=null and document identity_reason")
    elif mode is None:
        # Surface the unfilled contract even before a mode has been selected.
        missing.append("action.normalization.key_or_explicit_identity_reason")

    for key, minimum in (("max_chunk_steps", 1), ("random_seed", 0)):
        item = value(f"execution.{key}")
        if item is None:
            missing.append(f"execution.{key}")
        elif type(item) is not int or item < minimum:
            errors.append(f"execution.{key} must be an integer >= {minimum}")
    if not isinstance(config.get("adapter_options"), dict):
        errors.append("adapter_options must be an object, possibly empty")
    file_binding("runtime.environment_spec", "runtime.environment_spec_sha256")
    for name in ("official_00", "new_protocol_00"):
        file_binding(f"evidence.{name}.report_path", f"evidence.{name}.report_sha256")
    if not errors and config.get("is_template") is True:
        report["status"] = "template"
    elif not errors and not missing:
        report["status"] = "ready_configuration_only"
        report["configuration_ready"] = True
        report["cli_flags"] = {
            "--policy-factory": factory, "--policy-id": policy_id,
            "--policy-config": str(config_path) if config_path is not None else None,
            "--max-chunk-steps": config["execution"]["max_chunk_steps"],
        }
    return report


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON number {value}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="+", type=Path)
    parser.add_argument("--base-dir", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, help="write a new JSON report; never overwrite an existing file")
    args = parser.parse_args(argv)
    reports = []
    for path in args.configs:
        try:
            # Reject non-standard JSON NaN/Infinity rather than copying them to reports.
            config = json.loads(path.read_text(encoding="utf-8"),
                                parse_constant=_invalid_constant, object_pairs_hook=_json_object)
            result = check_config(config, base_dir=args.base_dir, config_path=path.resolve())
        except (OSError, ValueError) as error:
            result = check_config(None)
            result["errors"] = [f"cannot read configuration: {error}"]
        reports.append({"config_path": str(path), **result})
    payload = {"all_configurations_ready": all(item["configuration_ready"] for item in reports),
               "model_validation_claim": False, "reports": reports}
    output = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as file:
            file.write(output)
    print(output, end="")
    return 0 if payload["all_configurations_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
