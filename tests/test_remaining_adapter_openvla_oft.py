from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import openvla_oft
from tests.test_remaining_adapter_openvla import configuration, observation, upstream


def test_oft_preserves_two_raw_cameras_and_uses_upstream_proprio_and_chunk(monkeypatch, tmp_path):
    config = configuration(tmp_path)
    api, torch, calls = upstream()
    original_checkpoint = Path(config["adapter_options"]["checkpoint"])
    previous_cwd = Path.cwd()

    def initialize(cfg):
        assert Path.cwd() == Path(config["adapter_options"]["repo_path"])
        assert Path(cfg.pretrained_checkpoint) != original_checkpoint
        (Path(cfg.pretrained_checkpoint) / "config.json").write_text('{"prepared":true}')
        return api.get_model(cfg), "action_head", "proprio_projector", None, "processor"

    def prepare(raw, size):
        calls.append(("prepare", raw, size))
        # Simulate the upstream in-place clipping to prove caller data is safe.
        raw["robot0_eef_quat"][3] = 1.
        return {"full_image": raw["agentview_image"][::-1, ::-1],
                "wrist_image": raw["robot0_eye_in_hand_image"][::-1, ::-1],
                "state": np.r_[raw["robot0_eef_pos"], [0., 0., 0.], raw["robot0_gripper_qpos"]]}, None

    def action(cfg, model, obs, instruction, **kwargs):
        calls.append(("action", cfg, obs, instruction, kwargs))
        result = np.arange(56, dtype=float).reshape(8, 7) / 100
        result[:, -1] = [0., 1.] * 4
        return result

    api.initialize_model = initialize
    api.NUM_ACTIONS_CHUNK = 8
    api.prepare_observation = prepare
    api.get_action = action
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: (api, torch, "f" * 40))
    policy = openvla_oft.make_policy(config)
    assert Path.cwd() == previous_cwd
    assert (original_checkpoint / "config.json").read_text() == "{}"
    raw = observation()
    action = policy.predict(raw, "Original instruction")
    assert action.shape == (8, 7)
    np.testing.assert_array_equal(action[:, -1], [1., -1.] * 4)
    assert raw["robot0_eef_quat"][3] == 1.00001
    query = next(x for x in calls if x[0] == "action")
    np.testing.assert_array_equal(query[2]["wrist_image"], raw["robot0_eye_in_hand_image"][::-1, ::-1])
    np.testing.assert_array_equal(query[2]["state"], [.1, .2, .3, 0., 0., 0., .04, -.04])
    assert query[4]["proprio_projector"] == "proprio_projector"
    assert query[4]["action_head"] == "action_head"
    assert "mask" not in next(x for x in calls if x[0] == "prepare")[1]
    policy.reset()
    policy.predict(raw, "Original instruction")
    assert len([x for x in calls if x[0] == "action"]) == 2
    temporary = Path(policy.cfg.pretrained_checkpoint)
    policy.close()
    assert not temporary.exists()


def test_checkpoint_view_does_not_overwrite_original_small_files(tmp_path):
    config = configuration(tmp_path)
    source = Path(config["adapter_options"]["checkpoint"])
    view = openvla_oft._checkpoint_view(source)
    try:
        (Path(view.name) / "config.json").write_text("changed")
        assert (source / "config.json").read_text() == "{}"
    finally:
        view.cleanup()


def test_oft_missing_wrist_rejected_before_upstream():
    raw = observation()
    del raw["robot0_eye_in_hand_image"]
    with pytest.raises(ValueError, match="eye_in_hand"):
        openvla_oft._raw_observation(raw, wrist=True, proprio=True)


def test_oft_failed_initialization_restores_cwd_and_cleans_view(monkeypatch, tmp_path):
    config = configuration(tmp_path)
    api, torch, _ = upstream()
    previous = Path.cwd()
    temporary = []

    def failure(cfg):
        temporary.append(Path(cfg.pretrained_checkpoint))
        raise RuntimeError("component checkpoint mismatch")

    api.initialize_model = failure
    api.NUM_ACTIONS_CHUNK = 8
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: (api, torch, "f" * 40))
    with pytest.raises(RuntimeError, match="component checkpoint mismatch"):
        openvla_oft.make_policy(config)
    assert Path.cwd() == previous
    assert not temporary[0].exists()
