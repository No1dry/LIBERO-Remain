"""Synthetic CPU pipeline, including the real capture, codec, cache and train entry.

No released checkpoint, simulator, real dataset or production model is loaded.
The shared fake has the released 8D proprio / fused 12C input shape; identity
quaternions below make the synthetic axis-angle conversion exactly zero.
"""
from copy import deepcopy
import hashlib

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="tiny CPU FINISH pipeline needs optional torch")
h5py = pytest.importorskip("h5py", reason="synthetic source-domain pipeline needs optional h5py")

from benchmark.remaining_goals.finish import data, data_commands as commands, model, oft, training
from benchmark.remaining_goals.finish.data_registry import source_identity
from benchmark.remaining_goals.finish.schema import input_sha256, validate_input_evidence
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from tests.finish_domain_helpers import FakeProvider, make_assets
from tests.test_remaining_finish_data_commands import runtime
from tests.test_remaining_finish_model import FakeBase


BASE = {"test_only": True, "checkpoint": "synthetic-no-model-files", "input_contract": "8D-12C-BF16"}


@pytest.fixture(autouse=True)
def one_cpu_thread():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def tree_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


class UnknownProvider(FakeProvider):
    def capture_hold_label(self, state, steps, model_xml=None):
        # One positive candidate per role remains unknown; it is not a negative.
        if int(state[0]) in {1005, 1035}:
            self.hold_calls.append((state.copy(), model_xml))
            return None
        return super().capture_hold_label(state, steps, model_xml)


@pytest.fixture
def pipeline_audit(tmp_path):
    config = make_assets(tmp_path / "assets")
    # Two sampled frames per training source and eight per validation source
    # retain the frozen stride8-plus-last rule and yield 32 distinct inputs.
    with h5py.File(config["hdf5_path"], "a") as source:
        for index in range(35, 40):
            group = source[f"data/demo_{index}"]
            del group["states"]
            group.create_dataset("states", data=np.array(
                [[1000 + index, frame / 56, frame] for frame in range(57)], dtype=np.float64))
    config["expected_assets"]["hdf5_sha256"] = hashlib.sha256(
        (tmp_path / "assets/demonstrations.hdf5").read_bytes()).hexdigest()
    provider, out = UnknownProvider(), tmp_path / "audit"
    audit = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert audit["status"] == "ready_for_feature_export", audit["issues"]
    assert provider.closed and len(audit["rows"]) == 100
    assert len([row for row in audit["rows"] if row["label"] is None]) == 2
    return out, audit


class RawObservationBase(FakeBase):
    """Only adapt the synthetic identity-quaternion observation to the fake base."""
    bad_proprio = False

    def predict(self, observation, instruction):
        assert set(observation) == {"agentview_image", "robot0_eye_in_hand_image",
                                    "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"}
        assert instruction == "put both objects in the basket"
        np.testing.assert_array_equal(observation["robot0_eef_quat"], [0., 0., 0., 1.])
        proprio = np.concatenate((observation["robot0_eef_pos"], np.zeros(3),
                                  observation["robot0_gripper_qpos"]))
        assert proprio.shape == (8,)
        if self.bad_proprio:
            proprio = proprio[:-1]  # Explicit reproduction of the old invalid fake, not a model fix.
        return super().predict({"image": observation["agentview_image"],
                                "wrist_image": observation["robot0_eye_in_hand_image"],
                                "proprio": proprio}, instruction)


def worker_factory(instances, *, bad_proprio=False, parity_output=None):
    class CPUWorker:
        def __init__(self, config):
            self.base = RawObservationBase()
            self.base.bad_proprio = bad_proprio
            self.feature = oft.OFTFeaturePolicy.from_base(self.base, identity=BASE)
            self.evidence, self.closed = [], False
            self.before = model.module_state_sha256(oft._modules(self.base))
            if config["policy_factory"].endswith(":make_feature_policy"):
                self.policy = self.feature
                metadata = self.feature.metadata
            else:
                assert config["policy_factory"].endswith(":make_parity_policy")
                # Fixed selection and tolerances must exist before model creation.
                assert parity_output is not None and (parity_output / "inputs.json").is_file()
                assert data.read_json(parity_output / "parity.json")["tolerance"] == {"atol": 0., "rtol": 0.}
                head, artifact = model.load_head_artifact(config["finish"]["head_artifact"],
                                                          expected_base_identity=BASE)
                self.base.model.random = True
                self.policy = oft.ParityOFTPolicy.__new__(oft.ParityOFTPolicy)
                self.policy.shadow = oft.FinishOFTPolicy.from_feature_policy(
                    self.feature, head=head, artifact=artifact, threshold=config["finish"]["threshold"])
                metadata = {**self.policy.shadow.metadata, "purpose": "same-worker-action-parity",
                            "calls_per_input": {"original": 1, "shadow": 1}}
            self.provenance = {"policy_metadata": deepcopy(metadata), "test_only": True}
            instances.append(self)

        def reset(self):
            self.policy.reset()

        def predict(self, observation, instruction):
            result = self.policy.predict(observation, instruction)
            self.evidence.append(deepcopy(result.get("shadow", result)["input_evidence"]))
            return result

        def close(self):
            self.policy.close()
            self.closed = True

    return CPUWorker


def assert_typed_roundtrip(directory, row, captured):
    packed = load_observation_artifact(directory, row["input_artifact"])
    restored = {"schema_version": "remaining-finish-input-v1", **packed,
                "tensor_dtypes": row["input_tensor_dtypes"]}
    validate_input_evidence(restored)
    assert row["input_sha256"] == input_sha256(restored) == input_sha256(captured)
    assert restored["tensor_dtypes"] == captured["tensor_dtypes"]
    assert restored["tensor_dtypes"] == {"input_ids": "torch.int64", "attention_mask": "torch.bool",
                                        "pixel_values": "torch.bfloat16", "proprio": "numpy.float64"}
    tensors = restored["tensors"]
    assert tensors["proprio"].shape == (8,)
    assert tensors["pixel_values"].shape == (1, 12, 2, 2)
    assert tensors["pixel_values"].dtype == np.uint16
    assert tensors["attention_mask"].dtype == np.uint8
    for section in ("tensors", "crops"):
        for name, actual in restored[section].items():
            expected = captured[section][name]
            assert actual.dtype == expected.dtype and actual.shape == expected.shape
            assert actual.tobytes() == expected.tobytes()
    # The two per-image fused branches both survive the 12-channel concat.
    pixels = torch.from_numpy(tensors["pixel_values"].copy()).view(torch.bfloat16).float().numpy()
    for name, start in (("agentview", 0), ("wrist", 6)):
        crop = restored["crops"][name].transpose(2, 0, 1)[None].astype(np.float32)
        np.testing.assert_array_equal(pixels[:, start:start + 3], crop)
        np.testing.assert_array_equal(pixels[:, start + 3:start + 6], crop)


def test_real_consumers_accept_8d_12c_bf16_from_audit_through_train_and_32_parity(
        pipeline_audit, tmp_path, monkeypatch):
    audit_dir, audit = pipeline_audit
    original_audit = tree_bytes(audit_dir)
    unknown = {row["row_id"] for row in audit["rows"] if row["label"] is None}
    instances = []
    parity_out = tmp_path / "parity"
    monkeypatch.setattr(commands, "SubprocessPolicy", worker_factory(instances, parity_output=parity_out))
    exported = commands.feature_export_command(audit_dir, runtime(tmp_path), tmp_path / "features")
    assert exported["status"] == "completed", exported
    assert exported["model_loads"] == 1
    assert exported["expected_forwards"] == exported["completed_forwards"] == 98
    first = instances[0]
    assert first.closed and first.base.closed
    assert first.base.model.calls == first.base.action_head.calls == 98
    assert first.base.processor.calls == 196
    assert model.module_state_sha256(oft._modules(first.base)) == first.before
    model.assert_frozen(oft._modules(first.base))
    cache_dir = tmp_path / "features/cache"
    loaded = data.load_feature_cache(cache_dir, audit=audit, expected_base_identity=BASE,
        allowed_roles=["head_train", "head_validation"], expected_source_identity=source_identity(audit["registry"]))
    assert loaded["features"].shape == (98, 4) and loaded["features"].dtype == np.float32
    assert {row["role"] for row in loaded["rows"]} == {"head_train", "head_validation"}
    assert not unknown.intersection(row["row_id"] for row in loaded["rows"])
    audit_rows = {row["row_id"]: row for row in audit["rows"]}
    for row, label, captured in zip(loaded["rows"], loaded["labels"], first.evidence):
        source = audit_rows[row["row_id"]]
        assert row["domain"] == source["domain"] == "head_demonstration"
        for key in ("role", "source_key", "trajectory_id", "saved_state_index", "state_sha256",
                    "model_xml_sha256", "label"):
            assert row[key] == source[key]
        assert label == source["label"] and source["label"] is not None
        assert_typed_roundtrip(cache_dir, row, captured)
    assert len({row["input_sha256"] for row in loaded["rows"]}) == 98

    trained = training.train_from_cache(cache_dir, tmp_path / "tiny_training",
                                       config={"epochs": 1, "batch_size": 16, "device": "cpu"})
    assert trained["schema_version"] == "remaining-finish-head-v2"
    assert trained["identities"] == loaded["identities"]
    progress = trained["training"]
    assert progress["input_shapes"] == {"training": [59, 4], "validation": [39, 4]}
    assert progress["class_counts"] == {"training_positive": 29, "training_negative": 30,
                                        "validation_positive": 4, "validation_negative": 35}
    assert progress["pos_weight"] == pytest.approx(30 / 29)
    assert progress["feature_provenance"]["cache_sha256"] == loaded["manifest"]["cache_sha256"]
    assert progress["feature_provenance"]["role_counts"] == {"head_train": 59, "head_validation": 39}
    assert progress["best_epoch"] == 1

    parity = commands.parity_command(audit_dir, runtime(tmp_path), tmp_path / "tiny_training/head", parity_out)
    assert parity["status"] == "completed" and parity["passed"], parity
    assert parity["completed"] == parity["unique_model_inputs"] == 32
    assert parity["max_abs_error"] == 0 and all(row["bit_exact"] for row in parity["pairs"])
    assert parity["source_identity"] == loaded["identities"]["split_identity"]
    selection = data.read_json(parity_out / "inputs.json")
    assert len({row["row_id"] for row in selection["rows"]}) == 32
    assert {row["trajectory_id"] for row in selection["rows"]} == {f"demo_{i}" for i in range(35, 40)}
    assert not unknown.intersection(row["row_id"] for row in selection["rows"])
    assert all(row["role"] == "head_validation" for row in selection["rows"])
    second = instances[1]
    assert second.closed and second.base.closed
    assert second.base.model.calls == second.base.action_head.calls == 64
    assert second.base.processor.calls == 128
    for row, captured in zip(parity["pairs"], second.evidence):
        assert_typed_roundtrip(parity_out, row, captured)
    assert model.module_state_sha256(oft._modules(second.base)) == second.before
    assert tree_bytes(audit_dir) == original_audit


def test_invalid_legacy_7d_fails_after_one_forward_without_completed_cache_or_audit_mutation(
        pipeline_audit, tmp_path, monkeypatch):
    audit_dir, _ = pipeline_audit
    before = tree_bytes(audit_dir)
    instances = []
    monkeypatch.setattr(commands, "SubprocessPolicy", worker_factory(instances, bad_proprio=True))
    out = tmp_path / "failed_legacy_7d"
    report = commands.feature_export_command(audit_dir, runtime(tmp_path), out)
    assert report["status"] == "error" and report["completed"] is False
    assert report["model_loads"] == 1 and report["cache_path"] is None
    assert "proprio" in report["error"]["message"]
    assert not (out / "cache/cache.json").exists()
    worker = instances[0]
    assert worker.base.model.calls == worker.base.action_head.calls == 1
    assert worker.base.processor.calls == 2
    assert worker.closed and worker.base.closed
    assert "predict_action" not in vars(worker.base.model)
    assert "predict_action" not in vars(worker.base.action_head)
    assert not isinstance(worker.base.processor, oft._ProcessorCapture)
    assert tree_bytes(audit_dir) == before
    retained = tree_bytes(out)
    with pytest.raises(FileExistsError):
        commands.feature_export_command(audit_dir, runtime(tmp_path), out)
    assert len(instances) == 1 and tree_bytes(out) == retained
