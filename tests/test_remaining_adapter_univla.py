from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import univla
from tests.test_remaining_adapter_openvla import configuration, observation, upstream


def setup_policy(monkeypatch, tmp_path):
    config = configuration(tmp_path)
    decoder_path = tmp_path / "action_decoder.pt"
    decoder_path.write_bytes(b"fake-state-dict")
    config["adapter_options"]["action_decoder_path"] = str(decoder_path)
    api, torch, calls = upstream()

    class Decoder:
        def __init__(self, window):
            assert window == 12
            self.net = self
            self.count = 0

        def load_state_dict(self, state):
            assert state == {"weight": 1}

        def eval(self):
            return self

        def cuda(self):
            return self

        def reset(self):
            self.count = 0

        def __call__(self, latent, visual, mask, low, high):
            assert latent == "latent" and visual == "visual"
            np.testing.assert_array_equal(mask, [True] * 6 + [False])
            np.testing.assert_array_equal(low, [-1.] * 7)
            np.testing.assert_array_equal(high, [1.] * 7)
            self.count += 1
            return np.array([self.count / 10, 0., 0., 0., 0., 0., 1.])

    def latent(cfg, model, obs, instruction, **kwargs):
        calls.append(("latent", obs, instruction, kwargs))
        return "latent", "visual", np.array([[32001, 32002, 32031, 32032]])

    api.ActionDecoder = Decoder
    api.get_latent_action = latent
    monkeypatch.setattr(univla, "_load_upstream", lambda *args: (api, torch, "f" * 40))
    return univla.make_policy(config), api, calls


def test_univla_decoder_history_reset_and_single_action(monkeypatch, tmp_path):
    policy, api, calls = setup_policy(monkeypatch, tmp_path)
    raw = observation()
    first = policy.predict(raw, "Original instruction")
    second = policy.predict(raw, "Original instruction")
    assert first.shape == second.shape == (7,)
    assert first[0] == .1 and second[0] == .2 and first[-1] == -1
    queries = [x for x in calls if x[0] == "latent"]
    assert queries[0][3]["hist_action"] == ""
    assert queries[1][3]["hist_action"] == "<ACT_0><ACT_1><ACT_30><ACT_31>"
    assert queries[0][2] == "Original instruction"
    assert set(queries[0][1]) == {"full_image"}
    policy.reset()
    assert policy.predict(raw, "Task")[0] == .1
    assert [x for x in calls if x[0] == "latent"][-1][3]["hist_action"] == ""
    policy.close()
    with pytest.raises(RuntimeError, match="closed"):
        policy.reset()


def test_univla_rejects_non_action_tokens(monkeypatch, tmp_path):
    policy, api, _ = setup_policy(monkeypatch, tmp_path)
    api.get_latent_action = lambda *args, **kwargs: ("latent", "visual", np.array([[32000]]))
    with pytest.raises(ValueError, match="token IDs"):
        policy.predict(observation(), "Task")
    assert policy._history == "" and policy.decoder.count == 0


def test_univla_requires_separate_decoder(tmp_path):
    with pytest.raises(ValueError, match="action_decoder_path"):
        univla.make_policy(configuration(tmp_path))
