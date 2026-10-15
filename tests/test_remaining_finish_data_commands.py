"""Inject fake isolated workers; never spawn a real policy or restore physics."""
import copy
import json

import numpy as np
import pytest

from benchmark.remaining_goals.finish import data, data_commands as commands
from tests.test_finish_runner import envelope
from tests.test_remaining_finish_data import Provider, FeaturePolicy, assets, audited, h5py


BASE = {"checkpoint_sha256": "a" * 64}


def runtime(tmp_path):
    return {"suite": "libero_10", "model_id": "openvla_oft", "policy_factory": "original:factory",
            "runtime": {"python_executable": str(tmp_path / "fake_python")},
            "adapter_options": {"suite": "libero_10", "repo_path": str(tmp_path / "repo"), "checkpoint": str(tmp_path / "weights")},
            "execution": {"random_seed": 7}}


class FakeFeatureWorker(FeaturePolicy):
    last = None
    def __init__(self, config):
        super().__init__()
        type(self).last = self
        self.config, self.closed = config, False
        self.provenance = {"policy_metadata": {"feature_version": data.FEATURE_VERSION,
            "base_identity": BASE, "base_identity_sha256": data.canonical_hash(BASE)}}

    def reset(self):
        pass

    def close(self):
        self.closed = True


def test_feature_command_single_worker_and_original_config_unchanged(audited, tmp_path, monkeypatch):
    audit_dir, audit, _ = audited
    monkeypatch.setattr(commands, "SubprocessPolicy", FakeFeatureWorker)
    config = runtime(tmp_path)
    before = copy.deepcopy(config)
    result = commands.feature_export_command(audit_dir, config, tmp_path / "export")
    assert result["status"] == "completed", result
    assert result["model_loads"] == 1 and result["completed_forwards"] == 70
    assert result["cache_path"] == "cache/cache.json" and FakeFeatureWorker.last.closed
    assert FakeFeatureWorker.last.config["policy_factory"].endswith(":make_feature_policy")
    assert config == before
    loaded = data.load_feature_cache(tmp_path / "export/cache")
    assert loaded["identities"]["data_identity"]["audit_sha256"] == audit["audit_sha256"]


@pytest.mark.parametrize("failure", [RuntimeError("fake prediction failure"), KeyboardInterrupt()])
def test_feature_failure_keeps_report_and_closes_worker(audited, tmp_path, monkeypatch, failure):
    class Broken(FakeFeatureWorker):
        def predict(self, obs, instruction):
            raise failure
    monkeypatch.setattr(commands, "SubprocessPolicy", Broken)
    out = tmp_path / "failed"
    result = commands.feature_export_command(audited[0], runtime(tmp_path), out)
    assert result["status"] == ("interrupted" if isinstance(failure, KeyboardInterrupt) else "error")
    assert Broken.last.closed and not result["completed"]
    assert (out / "feature_export.json").exists() and not (out / "cache/cache.json").exists()


class DistinctProvider(Provider):
    def restore_demonstration(self, state, model_xml=None):
        result = super().restore_demonstration(state, model_xml)
        result["observation"]["robot0_eef_pos"] = np.array([state[0], state[1], 0.])
        result["observation"]["agentview_image"][0, 0, 0] = int(state[1])
        return result


@pytest.fixture
def parity_data(assets, tmp_path):
    with h5py.File(assets["hdf5_path"], "a") as file:
        for index in range(35, 40):
            demo = file["data"][f"demo_{49-index:02d}"]
            del demo["states"]
            demo.create_dataset("states", data=np.array([[index, frame] for frame in range(8)], dtype=np.float64))
    assets["state_stride"] = 1
    path = tmp_path / "parity_audit"
    audit = data.audit_demonstrations(assets, provider_factory=lambda _: DistinctProvider(), out=path)
    assert audit["status"] == "ready_for_feature_export", audit["issues"]
    head = {"schema_version": "remaining-finish-head-v1", "identities": {
        "base_identity": BASE, "data_identity": {"audit_sha256": audit["audit_sha256"]},
        "split_identity": {"split": audit["split"]}}}
    head["artifact_sha256"] = data.canonical_hash(head)
    head_path = tmp_path / "head.json"
    head_path.write_text(json.dumps(head), encoding="utf-8")
    return path, audit, head_path, head


class FakeParityWorker(FakeFeatureWorker):
    output = None
    mismatch = False
    fail_at = None
    repeat_inputs = False

    def __init__(self, config):
        assert (self.output / "inputs.json").is_file()
        pending = data.read_json(self.output / "parity.json")
        assert pending["tolerance"] == {"atol": 0., "rtol": 0.}
        super().__init__(config)
        self.head = data.read_json(config["finish"]["head_artifact"])
        self.provenance["policy_metadata"].update(purpose="same-worker-action-parity",
            calls_per_input={"original": 1, "shadow": 1})

    def predict(self, obs, instruction):
        self.calls += 1
        if self.calls == self.fail_at:
            raise KeyboardInterrupt()
        step = 0 if self.repeat_inputs else int(obs["robot0_eef_pos"][0]) * 8 + int(obs["robot0_eef_pos"][1])
        shadow = envelope(False, step)
        shadow["head_identity"]["artifact_sha256"] = self.head["artifact_sha256"]
        shadow["head_identity"]["base_identity_sha256"] = data.canonical_hash(BASE)
        original = shadow["candidate_actions"].copy()
        if self.mismatch:
            original[0, 0] += .1
        return {"schema_version": "remaining-finish-parity-pair-v1", "original_actions": original,
                "shadow": shadow, "rng_restored_in_model_worker": True}


def parity(monkeypatch, tmp_path, parity_data, worker=FakeParityWorker):
    out = tmp_path / "parity_out"
    worker.output = out
    monkeypatch.setattr(commands, "SubprocessPolicy", worker)
    result = commands.parity_command(parity_data[0], runtime(tmp_path), parity_data[2], out)
    return result, out


def test_parity_persists_fixed_inputs_before_worker_and_compares_all_actions(parity_data, tmp_path, monkeypatch):
    report, out = parity(monkeypatch, tmp_path, parity_data)
    assert report["status"] == "completed" and report["passed"], report
    assert report["completed"] == report["unique_model_inputs"] == 32
    assert FakeParityWorker.last.calls == 32 and FakeParityWorker.last.closed
    assert report["max_abs_error"] == 0 and all(pair["bit_exact"] for pair in report["pairs"])
    assert {pair["source_index"] for pair in report["pairs"]} == set(range(35, 40))
    assert (out / "pairs/0031.npz").is_file()
    with pytest.raises(FileExistsError):
        commands.parity_command(parity_data[0], runtime(tmp_path), parity_data[2], out)


def test_parity_does_not_raise_tolerance_or_replace_failed_inputs(parity_data, tmp_path, monkeypatch):
    class Mismatch(FakeParityWorker):
        mismatch = True
    report, _ = parity(monkeypatch, tmp_path, parity_data, Mismatch)
    assert report["status"] == "completed" and not report["passed"]
    assert report["completed"] == 32 and Mismatch.last.closed
    assert report["tolerance"] == {"atol": 0., "rtol": 0.}


def test_parity_interrupt_keeps_exact_partial_population(parity_data, tmp_path, monkeypatch):
    class Interrupted(FakeParityWorker):
        fail_at = 3
    report, out = parity(monkeypatch, tmp_path, parity_data, Interrupted)
    assert report["status"] == "interrupted" and report["expected"] == 32 and report["completed"] == 2
    assert not report["passed"] and Interrupted.last.closed and (out / "inputs.json").exists()


def test_parity_actual_identical_inputs_do_not_claim_32_distinct_checks(parity_data, tmp_path, monkeypatch):
    class Repeated(FakeParityWorker):
        repeat_inputs = True
    report, _ = parity(monkeypatch, tmp_path, parity_data, Repeated)
    assert report["status"] == "insufficient" and report["unique_model_inputs"] == 1
    assert not report["passed"] and report["completed"] == 32


def test_parity_insufficient_inputs_never_load_model(audited, tmp_path, monkeypatch):
    monkeypatch.setattr(commands, "SubprocessPolicy", lambda config: pytest.fail("no model when fewer than 32 inputs"))
    out = tmp_path / "insufficient"
    result = commands.parity_command(audited[0], runtime(tmp_path), "nonexistent_head", out)
    assert result["status"] == "insufficient" and result["model_loads"] == 0
    assert (out / "inputs.json").exists()


def test_runtime_python_symlink_not_resolved_and_config_identity_is_explicit(tmp_path):
    config = runtime(tmp_path)
    config["runtime"]["python_executable"] = ".venv/bin/python"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    actual = commands._config(path)
    assert actual["runtime"]["python_executable"] == str(tmp_path / ".venv/bin/python")
    config["suite"] = "libero_90"
    with pytest.raises(ValueError, match="LIBERO-10"):
        commands._config(config)
