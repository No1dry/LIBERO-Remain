"""UniVLA's released LIBERO policy and official temporal action decoder."""
from pathlib import Path

import numpy as np

from .openvla import (_config, _decode_action, _instruction, _load_upstream,
                      _normalization_key, _options, _raw_observation)

# Official GitHub history identifies this commit; the worker records its full SHA.
UPSTREAM_COMMIT = "0ab9e9d"
UPSTREAM_REPO = "https://github.com/OpenDriveLab/UniVLA"


class UniVLAPolicy:
    def __init__(self, config):
        options = _options(config, {"action_decoder_path", "window_size"})
        decoder = Path(options.get("action_decoder_path", "")).expanduser().resolve()
        if not decoder.is_file():
            raise ValueError("action_decoder_path must name the downloaded official action_decoder.pt")
        if options.get("window_size", 12) != 12:
            raise ValueError("The released LIBERO decoder uses window_size=12")
        self.api, self.torch, commit = _load_upstream(options, UPSTREAM_COMMIT)
        self.cfg = _config(self.api, options)
        self.cfg.window_size = 12
        self.cfg.action_decoder_path = str(decoder)
        self.api.set_seed_everywhere(self.cfg.seed)
        if not self.torch.cuda.is_available():
            raise RuntimeError("The official UniVLA LIBERO decoder path requires a CUDA worker")
        self.decoder = self.api.ActionDecoder(self.cfg.window_size)
        state_dict = self.torch.load(str(decoder), map_location="cpu", weights_only=True)
        self.decoder.net.load_state_dict(state_dict)
        self.decoder.eval().cuda()
        self.model = self.api.get_model(self.cfg)
        self.model.eval()
        self.cfg.unnorm_key = _normalization_key(self.model.norm_stats, self.cfg.task_suite_name)
        self.processor = self.api.get_processor(self.cfg)
        self.resize_size = self.api.get_image_resize_size(self.cfg)
        stats = self.model.get_action_stats(self.cfg.unnorm_key)
        self.low = np.asarray(stats["q01"], dtype=np.float64)
        self.high = np.asarray(stats["q99"], dtype=np.float64)
        self.mask = np.asarray(stats.get("mask", np.ones(7, dtype=bool)), dtype=bool)
        if self.low.shape != (7,) or self.high.shape != (7,) or self.mask.shape != (7,) or not np.isfinite(self.low).all() or not np.isfinite(self.high).all() or np.any(self.high < self.low):
            raise ValueError("Invalid UniVLA action normalization statistics")
        self.metadata = {"model": "univla", "repo_commit": commit, "suite": self.cfg.task_suite_name,
                         "unnorm_key": self.cfg.unnorm_key, "explicit_stop": False, "action_chunk": 1,
                         "temporal_aggregation_window": 12}
        self._closed = False
        self.reset()

    def reset(self):
        if self._closed:
            raise RuntimeError("Policy is closed")
        self.decoder.reset()
        self._history = ""

    def predict(self, obs, instruction):
        if self._closed:
            raise RuntimeError("Policy is closed")
        instruction = _instruction(instruction)
        raw = _raw_observation(obs)
        image = self.api.get_libero_image(raw, self.resize_size)
        with self.torch.inference_mode():
            latent, visual, ids = self.api.get_latent_action(
                self.cfg, self.model, {"full_image": image}, instruction,
                processor=self.processor, hist_action=self._history,
            )
            tokens = [int(token.item()) for token in ids[0]]
            if not tokens or any(not 32001 <= token < 32033 for token in tokens):
                raise ValueError("UniVLA generated invalid latent action token IDs")
            action = self.decoder(latent, visual, self.mask, self.low, self.high)
        result = _decode_action(self.api, action)
        # The official eval uses only the immediately preceding latent string.
        self._history = "".join(f"<ACT_{token - 32001}>" for token in tokens)
        return result

    def close(self):
        self.model = self.processor = self.decoder = None
        self._history = ""
        self._closed = True


def make_policy(config):
    return UniVLAPolicy(config)
