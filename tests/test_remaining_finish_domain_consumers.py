"""Two-domain artifact/consumer contracts using synthetic files and fake workers."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("h5py", reason="synthetic FINISH HDF fixtures require optional h5py")
from benchmark.remaining_goals.finish import data, data_commands as commands
from benchmark.remaining_goals.finish.data_registry import source_identity
from tests.finish_domain_helpers import make_audit
from tests.test_remaining_finish_data import input_evidence
from tests.test_remaining_finish_data_commands import runtime
from tests.test_finish_runner import envelope

BASE = {"checkpoint_sha256": "a" * 64}


class FeatureWorker:
    last = None

    def __init__(self, config=None):
        type(self).last = self
        self.calls, self.closed = 0, False
        self.provenance = {"policy_metadata": {"feature_version": data.FEATURE_VERSION,
            "base_identity": deepcopy(BASE), "base_identity_sha256": data.canonical_hash(BASE)}}

    def predict(self, obs, instruction):
        assert set(obs) <= data.OBSERVATION_KEYS
        assert instruction == "put both objects in the basket"
        self.calls += 1
        evidence = input_evidence()
        evidence["tensors"]["proprio"][0, :3] = obs["robot0_eef_pos"]
        return {"features": np.asarray(obs["robot0_eef_pos"], dtype=np.float32), "input_evidence": evidence}

    def reset(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def domain_cache(tmp_path):
    audit_dir, audit, _ = make_audit(tmp_path / "dataset")
    out = tmp_path / "cache"
    worker = FeatureWorker()
    manifest = data.export_features(audit_dir, worker, out, base_identity=BASE)
    assert worker.calls == 70
    return out, manifest


def rewrite_manifest(directory, manifest):
    manifest["cache_sha256"] = data.canonical_hash({key: value for key, value in manifest.items() if key != "cache_sha256"})
    (directory / "cache.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_domain_cache_roundtrip_binds_actual_keys_and_preserves_all_known_rows(domain_cache):
    path, manifest = domain_cache
    identity = source_identity(manifest["audit"]["registry"])
    loaded = data.load_feature_cache(path, allowed_roles=["head_train", "head_validation"], expected_source_identity=identity)
    assert manifest["schema_version"] == data.DOMAIN_CACHE_SCHEMA
    assert loaded["identities"]["split_identity"] == identity
    assert identity["ancestry_independence"] == "unproven"
    assert loaded["features"].shape == (70, 3)
    assert {row["role"] for row in loaded["rows"]} == {"head_train", "head_validation"}
    assert all(row["domain"] == "head_demonstration" and row["source_key"].startswith("hdf:") for row in loaded["rows"])
    assert all("source_index" not in row and "split" not in row for row in loaded["rows"])
    hdf35 = next(row["source_key"] for row in loaded["rows"] if row["trajectory_id"] == "demo_35")
    assert hdf35 not in identity["groups"]["official_initial_state"]["normal_calibration"]
    with pytest.raises(ValueError, match="mixed"):
        data.load_feature_cache(path, allowed_splits=["train", "validation"])
    with pytest.raises(ValueError, match="source identity"):
        data.load_feature_cache(path, expected_source_identity={"old": True})


@pytest.mark.parametrize("change", ["domain", "role", "source_key", "trajectory_id", "saved_state_index",
                                   "model_xml_sha256", "label", "source_index", "split"])
def test_cache_rejects_rehashed_row_reassignment_or_legacy_fields(domain_cache, change):
    path, manifest = domain_cache
    row = manifest["rows"][0]
    if change == "domain":
        row[change] = "official_initial_state"
    elif change == "role":
        row[change] = "normal_calibration"
    elif change == "source_key":
        row[change] = f"init:{manifest['audit']['assets']['init_states_path']['sha256']}:35"
    elif change == "trajectory_id":
        row[change] = "demo_40"
    elif change in {"saved_state_index", "source_index"}:
        row[change] = 35
    elif change == "split":
        row[change] = "validation"
    elif change == "model_xml_sha256":
        row[change] = "f" * 64
    else:
        row[change] = 1 - row[change]
    rewrite_manifest(path, manifest)
    with pytest.raises(ValueError):
        data.load_feature_cache(path)


@pytest.mark.parametrize("field", ["profile_sha256", "registry_sha256"])
def test_cache_rejects_detached_profile_or_registry_identity(domain_cache, field):
    path, manifest = domain_cache
    manifest["identities"]["data_identity"][field] = "f" * 64
    rewrite_manifest(path, manifest)
    with pytest.raises(ValueError, match="identity"):
        data.load_feature_cache(path)


def test_v2_audit_cannot_be_relabelled_as_legacy_cache(domain_cache):
    path, manifest = domain_cache
    manifest["schema_version"] = data.CACHE_SCHEMA
    rewrite_manifest(path, manifest)
    with pytest.raises(ValueError, match="versions"):
        data.load_feature_cache(path)


@pytest.mark.parametrize("asset", ["hdf5_path", "init_states_path", "bddl_path"])
def test_cache_refuses_actual_source_replaced_at_same_path(domain_cache, asset):
    directory, manifest = domain_cache
    Path(manifest["audit"]["assets"][asset]["path"]).write_bytes(b"replaced real source bytes, same filename")
    with pytest.raises(ValueError, match="changed|binding|asset"):
        data.load_feature_cache(directory)


def test_feature_command_reports_new_source_identity_and_only_head_roles(tmp_path, monkeypatch):
    directory, audit, _ = make_audit(tmp_path / "dataset")
    monkeypatch.setattr(commands, "SubprocessPolicy", FeatureWorker)
    result = commands.feature_export_command(directory, runtime(tmp_path), tmp_path / "export")
    assert result["status"] == "completed", result
    assert result["schema_version"] == "remaining-finish-feature-export-command-v2"
    assert result["expected_forwards"] == result["completed_forwards"] == 70
    assert result["source_identity"] == source_identity(audit["registry"])
    assert FeatureWorker.last.closed


def fake_head(path, audit):
    identities = data._identities(audit, BASE)
    head = {"schema_version": "remaining-finish-head-v2", "identities": identities,
            "identity_sha256": {key: data.canonical_hash(value) for key, value in identities.items()}}
    head["artifact_sha256"] = data.canonical_hash(head)
    path.write_text(json.dumps(head), encoding="utf-8")
    return head


class ParityWorker(FeatureWorker):
    repeated_inputs = False
    failure_at = None

    def __init__(self, config):
        super().__init__(config)
        self.head = data.read_json(config["finish"]["head_artifact"])
        self.provenance["policy_metadata"].update(purpose="same-worker-action-parity",
                                                  calls_per_input={"original": 1, "shadow": 1})

    def predict(self, obs, instruction):
        assert set(obs) <= data.OBSERVATION_KEYS
        self.calls += 1
        if self.calls == self.failure_at:
            raise KeyboardInterrupt()
        identity = 0 if self.repeated_inputs else int(obs["robot0_eef_pos"][0]) * 100 + int(obs["robot0_eef_pos"][2])
        shadow = envelope(False, identity)
        shadow["head_identity"]["artifact_sha256"] = self.head["artifact_sha256"]
        shadow["head_identity"]["base_identity_sha256"] = data.canonical_hash(BASE)
        return {"schema_version": "remaining-finish-parity-pair-v1", "rng_restored_in_model_worker": True,
                "original_actions": shadow["candidate_actions"].copy(), "shadow": shadow}


@pytest.fixture
def parity_domain_data(tmp_path):
    directory, audit, _ = make_audit(tmp_path / "dataset", frames=50)
    head_path = tmp_path / "head.json"
    fake_head(head_path, audit)
    return directory, audit, head_path


def test_parity_32_inputs_are_only_hdf_head_validation(parity_domain_data, tmp_path, monkeypatch):
    directory, audit, head = parity_domain_data
    monkeypatch.setattr(commands, "SubprocessPolicy", ParityWorker)
    result = commands.parity_command(directory, runtime(tmp_path), head, tmp_path / "parity")
    assert result["status"] == "completed" and result["passed"], result
    assert result["schema_version"] == "remaining-finish-parity-command-v2"
    assert result["completed"] == result["unique_model_inputs"] == ParityWorker.last.calls == 32
    assert ParityWorker.last.closed
    assert all(row["domain"] == "head_demonstration" and row["role"] == "head_validation" for row in result["pairs"])
    assert {row["trajectory_id"] for row in result["pairs"]} == {f"demo_{i}" for i in range(35, 40)}
    assert all("source_index" not in row and "split" not in row for row in result["pairs"])
    selected = data.read_json(tmp_path / "parity/inputs.json")
    assert selected["source_identity"] == source_identity(audit["registry"])
    assert selected["role"] == "head_validation"


def test_parity_does_not_borrow_train_or_calibration_inputs_when_head_validation_insufficient(tmp_path, monkeypatch):
    directory, _, _ = make_audit(tmp_path / "dataset")
    monkeypatch.setattr(commands, "SubprocessPolicy", lambda config: pytest.fail("insufficient selection must not load worker"))
    result = commands.parity_command(directory, runtime(tmp_path), "unused-head", tmp_path / "parity")
    assert result["status"] == "insufficient" and result["selected"] == 10
    assert result["model_loads"] == 0 and not result["passed"]


@pytest.mark.parametrize("change", ["legacy", "eval_registry", "data_profile", "label_contract"])
def test_parity_rejects_mixed_or_changed_head_binding_before_worker(parity_domain_data, tmp_path, monkeypatch, change):
    directory, _, path = parity_domain_data
    head = data.read_json(path)
    if change == "legacy":
        head["schema_version"] = "remaining-finish-head-v1"
    elif change == "eval_registry":
        head["identities"]["split_identity"]["eval_registry_sha256"] = "f" * 64
    elif change == "data_profile":
        head["identities"]["data_identity"]["profile_sha256"] = "f" * 64
    else:
        head["identities"]["label_contract"]["confirmation_steps"] = 1
    head["identity_sha256"] = {key: data.canonical_hash(value) for key, value in head["identities"].items()}
    head["artifact_sha256"] = data.canonical_hash({key: value for key, value in head.items() if key != "artifact_sha256"})
    path.write_text(json.dumps(head), encoding="utf-8")
    monkeypatch.setattr(commands, "SubprocessPolicy", lambda config: pytest.fail("bad identity must not load worker"))
    result = commands.parity_command(directory, runtime(tmp_path), path, tmp_path / "parity")
    assert result["status"] == "error" and result["model_loads"] == 0 and not result["passed"]


@pytest.mark.parametrize("mode", ["repeat", "interrupt"])
def test_domain_parity_retains_unique_input_and_close_contract(parity_domain_data, tmp_path, monkeypatch, mode):
    class Changed(ParityWorker):
        repeated_inputs = mode == "repeat"
        failure_at = 3 if mode == "interrupt" else None
    monkeypatch.setattr(commands, "SubprocessPolicy", Changed)
    result = commands.parity_command(parity_domain_data[0], runtime(tmp_path), parity_domain_data[2], tmp_path / "parity")
    assert result["status"] == ("insufficient" if mode == "repeat" else "interrupted")
    assert Changed.last.closed and not result["passed"]
    assert result["unique_model_inputs"] == 1 if mode == "repeat" else result["completed"] == 2
