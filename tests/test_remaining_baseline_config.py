"""Metadata readiness must not become a claim that six VLAs were validated."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.check_remaining_baseline_config import MODELS, check_config, main


CONFIGS = Path(__file__).resolve().parents[1] / "configs" / "remaining_goals"


@pytest.fixture
def populated(tmp_path):
    config = json.loads((CONFIGS / "openvla.json").read_text(encoding="utf-8"))
    config.update(is_template=False, policy_id="local-checkpoint-commit123-baseline",
                  policy_factory="not_installed_test_adapter:make_policy", suite="libero_10")
    config["checkpoint"] = {"uri": "local/weights", "artifact_manifest_sha256": "a" * 64}
    config["model_code"] = {"repository": "local/model-repository", "revision": "b" * 40}
    config["adapter_code"] = {"repository": "local/adapter-repository", "revision": "c" * 40,
                              "source_sha256": "d" * 64}
    config["observation"] = {"camera_keys": ["agentview_image"],
                              "image_preprocessing": "Test metadata: preserve input orientation.",
                              "proprio_preprocessing": "Test checkpoint does not consume proprioception."}
    config["action"] = {
        "translation_mapping": "Test metadata: xyz are already decoded.",
        "rotation_mapping": "Test metadata: rotation deltas are already decoded.",
        "gripper_mapping": "Test metadata: decoder owns the gripper mapping.",
        "stop_behavior": "Test baseline does not emit explicit STOP.",
        "normalization": {"mode": "dataset_statistics", "key": "test_suite_key",
                          "reference": "weights/dataset_statistics.json", "reference_sha256": "e" * 64,
                          "description": "Test metadata for dataset statistics.", "identity_reason": None},
    }
    config["execution"] = {"max_chunk_steps": 8, "random_seed": 0,
                           "seed_scope": "Test wrapper seeds its model process."}
    config["runtime"].update(python_executable="/test/environment/bin/python", python_version="3.10",
                             dependency_isolation="Dedicated test metadata environment.")
    lock = tmp_path / "environment.lock"
    lock.write_text("test dependency lock", encoding="utf-8")
    config["runtime"].update(environment_spec=lock.name,
                             environment_spec_sha256=hashlib.sha256(lock.read_bytes()).hexdigest())
    for name in ("official_00", "new_protocol_00"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"test_fixture": name, "is_model_evidence": False}), encoding="utf-8")
        config["evidence"][name] = {"report_path": path.name,
                                    "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "review_summary": f"Synthetic {name} metadata for checker tests only."}
    return config


def test_all_six_templates_are_explicitly_unready():
    assert {path.stem for path in CONFIGS.glob("*.json")} == set(MODELS)
    for path in CONFIGS.glob("*.json"):
        config = json.loads(path.read_text(encoding="utf-8"))
        result = check_config(config)
        assert result["status"] == "template"
        assert result["errors"] == []
        assert "policy_factory" in result["missing_fields"]
        assert "execution.max_chunk_steps" in result["missing_fields"]
        assert config["checkpoint"]["uri"] is None
        assert not result["configuration_ready"]
        assert not result["model_validation_claim"]


def test_complete_metadata_does_not_import_factory_or_certify_model(populated, tmp_path):
    result = check_config(populated, base_dir=tmp_path, config_path=tmp_path / "config.json")
    assert result["status"] == "ready_configuration_only"
    assert result["errors"] == result["missing_fields"] == []
    assert len(result["verified_files"]) == 3
    assert result["factory_imported"] is result["model_validation_claim"] is False
    assert result["evidence_content_assessed"] is False
    assert result["cli_flags"]["--max-chunk-steps"] == 8
    assert result["policy_config_transport"] == "entire_json_object"
    populated["is_template"] = True
    assert check_config(populated, base_dir=tmp_path)["status"] == "template"


@pytest.mark.parametrize("path,value", [
    ("model_id", "unknown_model"), ("display_name", "Wrong Model"),
    ("policy_factory", "benchmark.remaining_goals.toy:make_policy"),
    ("policy_factory", "factory_without_module"), ("policy_id", "openvla"),
    ("suite", "unregistered_suite"), ("model_code.revision", "main"),
    ("adapter_code.revision", "latest"), ("observation.camera_keys", []),
    ("observation.camera_keys", ["privileged_camera"]),
    ("observation.camera_keys", ["agentview_image", "agentview_image"]),
    ("observation.image_preprocessing", " "), ("action.gripper_mapping", "TODO"),
    ("action.rotation_mapping", None), ("action.normalization.key", None),
    ("execution.max_chunk_steps", True), ("execution.random_seed", False),
    ("execution.random_seed", -1), ("adapter_options", []),
])
def test_unfilled_or_wrong_contract_never_ready(populated, tmp_path, path, value):
    fields = path.split(".")
    target = populated
    for field in fields[:-1]:
        target = target[field]
    target[fields[-1]] = value
    result = check_config(populated, base_dir=tmp_path)
    assert result["status"] == "incomplete"
    assert not result["configuration_ready"]


def test_missing_or_changed_regression_evidence_is_visible(populated, tmp_path):
    (tmp_path / "official_00.json").unlink()
    (tmp_path / "new_protocol_00.json").write_text("changed", encoding="utf-8")
    result = check_config(populated, base_dir=tmp_path)
    assert result["status"] == "incomplete"
    assert any("official_00.report_path" in error and "does not exist" in error for error in result["errors"])
    assert any("new_protocol_00.report_path" in error and "mismatch" in error for error in result["errors"])


def test_identity_normalization_requires_explicit_explanation(populated, tmp_path):
    normalization = populated["action"]["normalization"]
    normalization.update(mode="identity", key=None, reference=None, reference_sha256=None)
    assert check_config(populated, base_dir=tmp_path)["status"] == "incomplete"
    normalization["identity_reason"] = "Test decoder already returns the simulator action units."
    assert check_config(populated, base_dir=tmp_path)["status"] == "ready_configuration_only"


def test_cli_outputs_machine_readable_unready_report(tmp_path, capsys):
    output = tmp_path / "readiness.json"
    assert main([str(CONFIGS / "pi0.json"), "--out", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report == json.loads(capsys.readouterr().out)
    assert not report["all_configurations_ready"]
    assert report["reports"][0]["status"] == "template"
    with pytest.raises(FileExistsError):
        main([str(CONFIGS / "pi0.json"), "--out", str(output)])


def test_cli_ready_uses_exact_config_path_and_does_not_mutate(populated, tmp_path, capsys):
    config_path = tmp_path / "filled.json"
    original = json.dumps(populated)
    config_path.write_text(original, encoding="utf-8")
    assert main([str(config_path), "--base-dir", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["reports"][0]["cli_flags"]["--policy-config"] == str(config_path.resolve())
    assert config_path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("contents", ["[]", "{broken", '{"model_id": NaN}',
                                      '{"model_id": "openvla", "model_id": "pi0"}'])
def test_bad_json_is_reported_without_claiming_readiness(tmp_path, capsys, contents):
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    assert main([str(path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reports"][0]["status"] == "incomplete"
    assert report["reports"][0]["errors"]
