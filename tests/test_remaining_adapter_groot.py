"""Contract tests with a fake official API; no weights or GPU inference."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import groot


def modalities(horizon=3):
    return {
        "video": {"modality_keys": ["image", "wrist_image"], "delta_indices": [0]},
        "state": {"modality_keys": list(groot.AXES), "delta_indices": [0]},
        "action": {"modality_keys": list(groot.AXES), "delta_indices": list(range(horizon))},
        "language": {"modality_keys": [groot.LANGUAGE_KEY], "delta_indices": [0]},
    }


class FakePolicy:
    def __init__(self):
        self.inputs = []
        self.reset_count = 0
        self.closed = False
        self.modalities = {key: SimpleNamespace(**value) for key, value in modalities().items()}
        self.actions = {key: np.full((1, 3, 1), (i + 1) / 10, np.float32)
                        for i, key in enumerate(groot.AXES)}
        self.actions["gripper"][0, :, 0] = [0.0, 0.5, 1.0]

    def get_modality_config(self):
        return self.modalities

    def get_action(self, obs):
        self.inputs.append(obs)
        return self.actions, {"not_a_stop": True}

    def reset(self):
        self.reset_count += 1

    def close(self):
        self.closed = True


@pytest.fixture
def configured(tmp_path, monkeypatch):
    checkpoint = tmp_path / "libero_10"
    checkpoint.mkdir()
    documents = {
        "config.json": {"model_type": "Gr00tN1d7", "architectures": ["Gr00tN1d7"]},
        "processor_config.json": {"processor_class": "Gr00tN1d7Processor", "processor_kwargs": {
            "modality_configs": {"libero_sim": modalities()}}},
        "statistics.json": {"libero_sim": {}}, "embodiment_id.json": {"libero_sim": 0},
    }
    for name, body in documents.items():
        (checkpoint / name).write_text(json.dumps(body), encoding="utf-8")
    (checkpoint / "model.safetensors").write_bytes(b"fake fixture; GPU loader is mocked")
    config = {"model_id": "groot_n1_7", "suite": "libero_10", "adapter_options": {
        "suite": "libero_10", "checkpoint_suite": "libero_10", "checkpoint": str(checkpoint),
        "repo_path": str(tmp_path / "repo"), "repo_revision": groot.OFFICIAL_REVISION, "device": "cuda:7"}}
    fake = FakePolicy()
    calls = []
    monkeypatch.setattr(groot, "_load_policy", lambda *args: calls.append(args) or fake)
    return config, fake, calls, checkpoint


def observation():
    image = np.zeros((256, 256, 3), np.uint8)
    image[0, 0] = [1, 2, 3]
    image[-1, -1] = [4, 5, 6]
    return {"agentview_image": image, "robot0_eye_in_hand_image": image + 10,
            "robot0_eef_pos": np.array([.1, -.2, .3]),
            "robot0_eef_quat": np.array([0., 0., 2 ** -.5, 2 ** -.5]),
            "robot0_gripper_qpos": np.array([.04, -.04])}


def test_model_worker_contract_and_official_coordinate_mapping(configured):
    config, fake, calls, _ = configured
    policy = groot.make_policy(config)
    obs = observation()
    original = deepcopy(obs)
    # A poison evaluator field must never be inspected or forwarded.
    obs["initial_mask"] = object()
    policy.reset()
    actions = policy.predict(obs, "put both objects in the basket")
    assert calls[0][1] == groot.OFFICIAL_REVISION and calls[0][-1] == "cuda:7"
    assert fake.reset_count == 1
    actual = fake.inputs[0]
    assert set(actual) == {"video", "state", "language"}
    assert actual["video"]["image"].shape == (1, 1, 256, 256, 3)
    np.testing.assert_array_equal(actual["video"]["image"][0, 0, 0, 0], [4, 5, 6])
    np.testing.assert_array_equal(actual["video"]["wrist_image"][0, 0, 0, 0], [14, 15, 16])
    assert actual["state"]["gripper"].shape == (1, 1, 2)
    assert all(value.dtype == np.float32 for value in actual["state"].values())
    assert actual["state"]["yaw"][0, 0, 0] == pytest.approx(np.pi / 2)
    assert actual["language"] == {groot.LANGUAGE_KEY: [["put both objects in the basket"]]}
    assert actions.shape == (3, 7)
    np.testing.assert_allclose(actions[:, :6], np.tile(np.arange(1, 7) / 10, (3, 1)))
    np.testing.assert_array_equal(actions[:, -1], [1., 0., -1.])
    for key in original:
        np.testing.assert_array_equal(obs[key], original[key])
    policy.predict(obs, "another whole instruction")
    assert len(fake.inputs) == 2  # No stale cached action chunk inside adapter.
    policy.close()
    policy.close()
    assert fake.closed
    with pytest.raises(RuntimeError, match="closed"):
        policy.predict(obs, "task")
    with pytest.raises(RuntimeError, match="closed"):
        policy.reset()


@pytest.mark.parametrize("generation", ["Gr00tN1d5", "Gr00tN1d6", "other"])
def test_rejects_version_substitution_before_loading(configured, generation):
    config, _, calls, path = configured
    (path / "config.json").write_text(json.dumps({"model_type": generation, "architectures": [generation]}))
    with pytest.raises(ValueError, match="actual GR00T N1.7"):
        groot.make_policy(config)
    assert calls == []


def test_base_model_without_libero_finetuning_rejected(configured):
    config, _, calls, path = configured
    (path / "processor_config.json").write_text(json.dumps({"processor_class": "Gr00tN1d7Processor", "processor_kwargs": {"modality_configs": {}}}))
    with pytest.raises(ValueError, match="lacks LIBERO_PANDA"):
        groot.make_policy(config)
    assert not calls


@pytest.mark.parametrize("filename", ["statistics.json", "model.safetensors", "embodiment_id.json"])
def test_missing_checkpoint_artifacts_fail_before_gpu(configured, filename):
    config, _, calls, path = configured
    (path / filename).unlink()
    with pytest.raises(FileNotFoundError):
        groot.make_policy(config)
    assert not calls


def test_sharded_checkpoint_is_supported_and_cannot_escape(configured):
    config, _, _, path = configured
    index = path / "model.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {"tensor": "model.safetensors"}}))
    groot.make_policy(config)
    index.write_text(json.dumps({"weight_map": {"tensor": "../foreign.safetensors"}}))
    (path.parent / "foreign.safetensors").write_bytes(b"not valid weights")
    with pytest.raises(FileNotFoundError, match="unsafe"):
        groot.make_policy(config)


def test_official_finetune_processor_subdirectory_layout(configured):
    config, _, _, path = configured
    processor = path / "processor"
    processor.mkdir()
    for name in ("processor_config.json", "statistics.json", "embodiment_id.json"):
        (path / name).rename(processor / name)
    groot.make_policy(config)


def test_suite_identity_is_not_silently_substituted(configured):
    config, _, calls, _ = configured
    config["suite"] = config["adapter_options"]["suite"] = "libero_90"
    with pytest.raises(ValueError, match="checkpoint_suite"):
        groot.make_policy(config)
    assert not calls
    config["adapter_options"]["checkpoint_suite"] = "libero_90"
    # A separately supplied, explicitly declared local N1.7 LIBERO90 checkpoint
    # is accepted; this declaration is not proof of its training provenance.
    groot.make_policy(config)


@pytest.mark.parametrize("field,value", [("robot0_eef_quat", [0, 0, 0, 2]),
                                         ("robot0_eef_pos", [0, float("nan"), 0]),
                                         ("robot0_gripper_qpos", [0]),
                                         ("agentview_image", np.zeros((256,256,3), np.float32))])
def test_invalid_observation_fails_before_inference(configured, field, value):
    config, fake, _, _ = configured
    policy = groot.make_policy(config)
    obs = observation()
    obs[field] = value
    with pytest.raises(ValueError):
        policy.predict(obs, "task")
    assert not fake.inputs


@pytest.mark.parametrize("case", ["nan", "shape", "missing", "stop"])
def test_invalid_output_never_becomes_action_or_stop(configured, case):
    config, fake, _, _ = configured
    policy = groot.make_policy(config)
    if case == "nan": fake.actions["x"][0, 0, 0] = np.nan
    if case == "shape": fake.actions["x"] = np.zeros((3, 1))
    if case == "missing": fake.actions.pop("yaw")
    if case == "stop": fake.get_action = lambda obs: None
    with pytest.raises(ValueError):
        policy.predict(observation(), "task")


def test_unsupported_observation_history_fails_closed(configured):
    config, fake, _, _ = configured
    fake.modalities["video"].delta_indices = [-1, 0]
    with pytest.raises(ValueError, match="single-observation"):
        groot.make_policy(config)


def test_identity_quaternion_is_finite():
    obs = observation()
    obs["robot0_eef_quat"] = [0, 0, 0, 1]
    value = groot._policy_observation(obs, "task")
    assert all(value["state"][key].item() == 0 for key in ("roll", "pitch", "yaw"))


def test_import_does_not_import_torch_or_gr00t():
    result = subprocess.run([sys.executable, "-c",
        "import sys; import benchmark.remaining_goals.adapters.groot; "
        "assert 'torch' not in sys.modules; assert 'gr00t' not in sys.modules"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_real_loader_verifies_checkout_and_calls_official_api(tmp_path, monkeypatch):
    source = tmp_path / "gr00t/policy/gr00t_policy.py"
    source.parent.mkdir(parents=True)
    source.write_text("# fake source for API loader test\n")
    calls = []
    fake_module = SimpleNamespace(__file__=str(source), Gr00tPolicy=lambda **kw: calls.append(kw) or "policy")
    monkeypatch.setattr(groot.subprocess, "check_output", lambda args, **kw: groot.OFFICIAL_REVISION if "rev-parse" in args else "")
    monkeypatch.setattr(groot.importlib, "import_module", lambda name: fake_module)
    monkeypatch.delitem(sys.modules, "gr00t", raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert groot._load_policy(tmp_path, groot.OFFICIAL_REVISION, tmp_path / "weights", "cuda:0") == "policy"
    assert calls == [{"embodiment_tag": "LIBERO_PANDA", "model_path": str(tmp_path / "weights"), "device": "cuda:0", "strict": True}]
    monkeypatch.setattr(groot.subprocess, "check_output", lambda *args, **kw: "a" * 40)
    with pytest.raises(ValueError, match="repo_revision"):
        groot._load_policy(tmp_path, groot.OFFICIAL_REVISION, tmp_path / "weights", "cuda:0")
