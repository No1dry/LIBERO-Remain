"""Contract tests with lightweight upstream doubles, not checkpoint evaluation."""
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import openvla


def configuration(tmp_path):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "dataset_statistics.json").write_text(json.dumps({"libero_10_no_noops": {}}))
    (checkpoint / "config.json").write_text("{}")
    repo = tmp_path / "upstream"
    repo.mkdir()
    return {"suite": "libero_10", "adapter_options": {
        "repo_path": str(repo), "checkpoint": str(checkpoint), "suite": "libero_10"}}


def observation():
    return {"agentview_image": np.arange(48, dtype=np.uint8).reshape(4, 4, 3),
            "robot0_eye_in_hand_image": np.arange(48, 96, dtype=np.uint8).reshape(4, 4, 3),
            "robot0_eef_pos": np.array([.1, .2, .3]), "robot0_eef_quat": np.array([0., 0., 0., 1.00001]),
            "robot0_gripper_qpos": np.array([.04, -.04]), "mask": [True, False]}


def upstream():
    calls = []
    model = SimpleNamespace(norm_stats={"libero_10_no_noops": {}}, eval=lambda: None)
    model.get_action_stats = lambda key: {"q01": [-1.] * 7, "q99": [1.] * 7,
                                          "mask": [True] * 6 + [False]}

    def image(raw, size):
        calls.append(("image", raw, size))
        return raw["agentview_image"][::-1, ::-1].copy()

    def action(cfg, model, obs, instruction, **kwargs):
        calls.append(("action", cfg, obs, instruction, kwargs))
        return np.array([.1, .2, .3, .4, .5, .6, 1.])

    def normalize(value, binarize):
        assert binarize is True
        value[..., -1] = np.sign(2 * value[..., -1] - 1)
        return value

    def invert(value):
        value[..., -1] *= -1
        return value

    api = SimpleNamespace(GenerateConfig=SimpleNamespace, set_seed_everywhere=lambda seed: calls.append(("seed", seed)),
                          get_model=lambda cfg: model, get_processor=lambda cfg: "processor",
                          get_image_resize_size=lambda cfg: 224, get_libero_image=image,
                          get_action=action, normalize_gripper_action=normalize, invert_gripper_action=invert)
    torch = SimpleNamespace(inference_mode=nullcontext, cuda=SimpleNamespace(is_available=lambda: True),
                            load=lambda *args, **kwargs: {"weight": 1})
    return api, torch, calls


def test_openvla_uses_upstream_preprocessing_once_and_decodes_gripper(monkeypatch, tmp_path):
    config = configuration(tmp_path)
    api, torch, calls = upstream()
    monkeypatch.setattr(openvla, "_load_upstream", lambda *args: (api, torch, "f" * 40))
    policy = openvla.make_policy(config)
    raw = observation()
    before = raw["agentview_image"].copy()
    action = policy.predict(raw, "Put the pan on the stove")
    np.testing.assert_array_equal(action, [.1, .2, .3, .4, .5, .6, -1.])
    image_call = next(x for x in calls if x[0] == "image")
    assert set(image_call[1]) == {"agentview_image"}  # no GT and no unused proprio
    np.testing.assert_array_equal(image_call[1]["agentview_image"], before)
    action_call = next(x for x in calls if x[0] == "action")
    np.testing.assert_array_equal(action_call[2]["full_image"], before[::-1, ::-1])
    assert action_call[3] == "Put the pan on the stove"
    assert action_call[1].center_crop is True
    assert action_call[1].unnorm_key == "libero_10_no_noops"
    policy.reset()
    assert policy.predict(raw, "Task").shape == (7,)
    policy.close()
    with pytest.raises(RuntimeError, match="closed"):
        policy.predict(raw, "Task")


@pytest.mark.parametrize("gripper,expected", [(0., 1.), (.5, 0.), (1., -1.)])
def test_gripper_boundary_preserves_official_sign_rule(gripper, expected):
    api, _, _ = upstream()
    value = np.array([0., 0., 0., 0., 0., 0., gripper])
    assert openvla._decode_action(api, value)[-1] == expected
    assert value[-1] == gripper


@pytest.mark.parametrize("bad", [None, np.zeros(6), np.zeros((1, 7)), [float("nan")] * 7])
def test_no_none_stop_or_bad_action(bad):
    api, _, _ = upstream()
    with pytest.raises((ValueError, TypeError)):
        openvla._decode_action(api, bad)


def test_no_silent_libero90_statistics_fallback(tmp_path):
    config = configuration(tmp_path)
    config["suite"] = config["adapter_options"]["suite"] = "libero_90"
    with pytest.raises(ValueError, match="another suite"):
        openvla.make_policy(config)


def test_options_reject_mismatch_unknown_and_bad_image(tmp_path):
    config = configuration(tmp_path)
    config["suite"] = "libero_90"
    with pytest.raises(ValueError, match="differ"):
        openvla._options(config)
    config["suite"] = "libero_10"
    config["adapter_options"]["unnorm_key"] = "libero_90"
    with pytest.raises(ValueError, match="Unknown"):
        openvla._options(config)
    raw = observation()
    raw["agentview_image"] = raw["agentview_image"].astype(np.float32)
    with pytest.raises(ValueError, match="uint8"):
        openvla._raw_observation(raw)


def test_revision_mismatch_rejected_before_heavy_import(monkeypatch, tmp_path):
    target = tmp_path / "experiments/robot/libero/run_libero_eval.py"
    target.parent.mkdir(parents=True)
    target.write_text("")
    monkeypatch.setattr(openvla.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    with pytest.raises(ValueError, match="revision mismatch"):
        openvla._load_upstream({"repo_path": str(tmp_path)}, "b" * 40)


def test_execution_seed_is_authoritative_and_disagreement_fails(tmp_path):
    config = configuration(tmp_path)
    config["execution"] = {"random_seed": 19}
    assert openvla._options(config)["seed"] == 19
    config["adapter_options"]["seed"] = 7
    with pytest.raises(ValueError, match="seed.*differ"):
        openvla._options(config)


def test_other_upstream_fork_already_imported_is_rejected(monkeypatch, tmp_path):
    target = tmp_path / "experiments/robot/libero/run_libero_eval.py"
    target.parent.mkdir(parents=True)
    target.write_text("")
    monkeypatch.setattr(openvla.subprocess, "check_output", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setitem(openvla.sys.modules, "prismatic.fake", SimpleNamespace(__file__=str(tmp_path.parent / "other-fork/module.py")))
    with pytest.raises(RuntimeError, match="dedicated model worker"):
        openvla._load_upstream({"repo_path": str(tmp_path)}, "a" * 40)
