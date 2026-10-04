"""Protocol tests using fake official components; no weights or GPU required."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import openpi


def config(model="pi05"):
    return {
        "model_id": model, "suite": "libero_10", "execution": {"max_chunk_steps": 5},
        "adapter_options": {
            "repo_path": "/models/openpi", "checkpoint": "/weights/libero",
            "train_config": "pi05_libero" if model == "pi05" else "pi0_libero",
            "suite": "libero_10", "random_seed": 7, "num_inference_steps": 10,
        },
    }


def observation():
    return {
        "agentview_image": np.arange(18, dtype=np.uint8).reshape(2, 3, 3),
        "robot0_eye_in_hand_image": np.arange(18, 36, dtype=np.uint8).reshape(2, 3, 3),
        "robot0_eef_pos": np.array([0.2, 0.3, 0.4]),
        "robot0_eef_quat": np.array([0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)]),
        "robot0_gripper_qpos": np.array([0.02, -0.03]),
        "object-state": "must never reach model", "initial_mask": [True, False],
    }


class FakeImages:
    def __init__(self):
        self.calls = []

    def resize_with_pad(self, value, height, width):
        self.calls.append((value.copy(), height, width, value.flags.c_contiguous))
        return np.broadcast_to(value[0, 0], (height, width, 3)).copy()

    def convert_to_uint8(self, value):
        return value


class FakeOfficial:
    def __init__(self, horizon):
        self.actions = np.linspace(-1.4, 1.3, horizon * 7).reshape(horizon, 7)
        self.calls = []
        self.resets = 0
        self.closed = False

    def infer(self, obs, *, noise):
        self.calls.append((deepcopy(obs), noise.copy()))
        return {"actions": self.actions, "policy_timing": {"infer_ms": 1}}

    def reset(self):
        self.resets += 1

    def close(self):
        self.closed = True


def fake_components(monkeypatch, model="pi05"):
    horizon = 10 if model == "pi05" else 50
    official = FakeOfficial(horizon)
    images = FakeImages()
    trained = SimpleNamespace(
        model=SimpleNamespace(action_horizon=horizon, action_dim=32, pi05=model == "pi05"),
        data=SimpleNamespace(repo_id=openpi.NORMALIZATION_KEY, extra_delta_transform=model == "pi0"),
    )
    calls = []

    def get_config(name):
        calls.append(("get_config", name))
        return trained

    def create(train_config, checkpoint_dir, **kwargs):
        calls.append(("load", train_config, checkpoint_dir, kwargs))
        return official

    monkeypatch.setattr(openpi, "_load_components", lambda options: (
        SimpleNamespace(get_config=get_config), SimpleNamespace(create_trained_policy=create), images,
    ))
    return official, images, trained, calls


@pytest.mark.parametrize("model,horizon", [("pi0", 50), ("pi05", 10)])
def test_factory_official_api_and_native_action_space(monkeypatch, model, horizon):
    official, images, trained, calls = fake_components(monkeypatch, model)
    cfg = config(model)
    cfg["adapter_options"]["pytorch_device"] = "cuda:0"
    policy = openpi.make_policy(cfg)
    assert calls == [
        ("get_config", cfg["adapter_options"]["train_config"]),
        ("load", trained, "/weights/libero", {"sample_kwargs": {"num_steps": 10}, "pytorch_device": "cuda:0"}),
    ]
    result = policy.predict(observation(), "put the bowl on the plate")
    assert result.shape == (horizon, 7)  # Runner, not adapter, executes first five.
    np.testing.assert_array_equal(result, official.actions)
    assert not np.shares_memory(result, official.actions)
    # No second normalization, clipping, xyz addition, gripper sign or threshold.
    assert result.min() < -1
    assert result.max() > 1
    assert policy.metadata["additional_gripper_transform"] == "identity"
    assert official.calls[0][1].shape == (horizon, 32)
    assert official.calls[0][1].dtype == np.float32


def test_raw_images_rotation_and_state_semantics_do_not_mutate_inputs():
    raw = observation()
    before = deepcopy(raw)
    images = FakeImages()
    prepared = openpi.prepare_observation(raw, "do both tasks", images)
    assert set(prepared) == {"observation/image", "observation/wrist_image", "observation/state", "prompt"}
    for index, key in enumerate(("agentview_image", "robot0_eye_in_hand_image")):
        np.testing.assert_array_equal(images.calls[index][0], raw[key][::-1, ::-1])
        assert images.calls[index][1:] == (224, 224, True)
        np.testing.assert_array_equal(raw[key], before[key])
    np.testing.assert_allclose(prepared["observation/state"], [0.2, 0.3, 0.4, 0, 0, np.pi / 2, 0.02, -0.03])
    np.testing.assert_array_equal(raw["robot0_eef_quat"], before["robot0_eef_quat"])
    assert prepared["prompt"] == "do both tasks"


@pytest.mark.parametrize("w", [1.0, -1.0, 1.000000001])
def test_quaternion_identity_clips_scalar_without_mutation(w):
    quat = np.array([0.0, 0.0, 0.0, w])
    np.testing.assert_array_equal(openpi._quat_to_axis_angle(quat), np.zeros(3))
    assert quat[3] == w


def test_episode_reset_replays_seeded_noise_without_reloading(monkeypatch):
    official, _, _, loads = fake_components(monkeypatch)
    policy = openpi.make_policy(config())
    policy.predict(observation(), "task")
    policy.predict(observation(), "task")
    assert not np.array_equal(official.calls[0][1], official.calls[1][1])
    policy.reset()
    policy.predict(observation(), "task")
    np.testing.assert_array_equal(official.calls[0][1], official.calls[2][1])
    assert len(loads) == 2
    assert official.resets == 2
    assert policy.metadata["sampling_matches_official_default_rng"] is False
    policy.close()
    policy.close()
    assert official.closed
    with pytest.raises(RuntimeError, match="closed"):
        policy.predict(observation(), "task")
    with pytest.raises(RuntimeError, match="closed"):
        policy.reset()


@pytest.mark.parametrize("key,value", [
    ("agentview_image", np.zeros((2, 3, 3), dtype=np.float32)),
    ("robot0_eye_in_hand_image", np.zeros((3, 2), dtype=np.uint8)),
    ("robot0_eef_pos", np.array([np.nan, 0, 0])),
    ("robot0_eef_quat", np.zeros(3)),
    ("robot0_gripper_qpos", np.array([0.02])),
])
def test_invalid_raw_observation_is_rejected_before_inference(monkeypatch, key, value):
    official, _, _, _ = fake_components(monkeypatch)
    policy = openpi.make_policy(config())
    obs = observation()
    obs[key] = value
    with pytest.raises(ValueError, match=key):
        policy.predict(obs, "task")
    assert official.calls == []


@pytest.mark.parametrize("shape", [(7,), (5, 7), (10, 32), (1, 10, 7)])
def test_rejects_wrong_native_output_shape(monkeypatch, shape):
    official, _, _, _ = fake_components(monkeypatch)
    policy = openpi.make_policy(config())
    official.actions = np.zeros(shape)
    with pytest.raises(ValueError, match="unnormalized"):
        policy.predict(observation(), "task")


def test_rejects_nonfinite_output(monkeypatch):
    official, _, _, _ = fake_components(monkeypatch)
    policy = openpi.make_policy(config())
    official.actions[0, 6] = np.inf
    with pytest.raises(ValueError, match="finite"):
        policy.predict(observation(), "task")


@pytest.mark.parametrize("key,value", [
    ("checkpoint", None), ("repo_path", ""), ("suite", "libero_90"),
    ("train_config", "pi0_libero"), ("random_seed", True),
    ("random_seed", -1), ("num_inference_steps", 0),
    ("normalization_key", "droid"), ("revision", "main"), ("replan_steps", 3),
])
def test_bad_configuration_is_rejected_before_heavy_import(monkeypatch, key, value):
    def forbidden(_):
        pytest.fail("heavy import reached before config validation")
    monkeypatch.setattr(openpi, "_load_components", forbidden)
    cfg = config()
    cfg["adapter_options"][key] = value
    with pytest.raises(ValueError):
        openpi.make_policy(cfg)


def test_installed_model_transform_drift_is_rejected(monkeypatch):
    _, _, trained, calls = fake_components(monkeypatch)
    trained.data.extra_delta_transform = True
    with pytest.raises(ValueError, match="transforms"):
        openpi.make_policy(config())
    assert len(calls) == 1


def test_libero90_requires_explicit_transfer_track_before_loading(monkeypatch):
    def forbidden(_):
        pytest.fail("silent suite90 baseline was loaded")
    monkeypatch.setattr(openpi, "_load_components", forbidden)
    cfg = config()
    cfg["suite"] = cfg["adapter_options"]["suite"] = "libero_90"
    with pytest.raises(ValueError, match="zero_shot_extension"):
        openpi.make_policy(cfg)


def test_libero90_transfer_is_labeled_in_runtime_metadata(monkeypatch):
    fake_components(monkeypatch)
    cfg = config()
    cfg["suite"] = cfg["adapter_options"]["suite"] = "libero_90"
    cfg["adapter_options"]["evaluation_track"] = "zero_shot_extension"
    policy = openpi.make_policy(cfg)
    assert policy.metadata["evaluation_track"] == "zero_shot_extension"
    assert policy.metadata["normalization_key"] == "physical-intelligence/libero"


def test_checkout_verification_prevents_wrong_revision_import(tmp_path, monkeypatch):
    source = tmp_path / "src/openpi/training/config.py"
    source.parent.mkdir(parents=True)
    source.write_text("# source placeholder", encoding="utf-8")
    monkeypatch.setattr(openpi.subprocess, "check_output", lambda args, **kwargs: "wrong-sha" if "rev-parse" in args else "")
    def forbidden(_):
        pytest.fail("imported wrong upstream revision")
    monkeypatch.setattr(openpi.importlib, "import_module", forbidden)
    with pytest.raises(ValueError, match="pinned commit"):
        openpi._load_components({"repo_path": str(tmp_path)})
