"""Official OpenVLA-OFT LIBERO L1 policy (two images, proprio, eight actions)."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .openvla import (_action_array, _config, _decode_action, _instruction,
                      _load_upstream, _normalization_key, _options, _raw_observation)

UPSTREAM_COMMIT = "e4287e94541f459edc4feabc4e181f537cd569a8"
UPSTREAM_REPO = "https://github.com/moojink/openvla-oft"


def _checkpoint_view(checkpoint):
    """Protect original files from the official loader's config/code syncing.

    Small metadata/code files are copied. Large immutable weights are linked,
    never duplicated or opened for writing by this adapter or the official loader.
    """
    directory = tempfile.TemporaryDirectory(prefix="remaining-openvla-oft-")
    target = Path(directory.name)
    try:
        for source in Path(checkpoint).rglob("*"):
            dest = target / source.relative_to(checkpoint)
            if source.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                if source.suffix in {".json", ".py"} or source.stat().st_size <= 16 * 1024 * 1024:
                    shutil.copy2(source, dest)
                else:
                    try:
                        os.link(source.resolve(), dest)
                    except OSError:
                        os.symlink(source.resolve(), dest)
        return directory
    except BaseException:
        directory.cleanup()
        raise


class OpenVLAOFTPolicy:
    def __init__(self, config):
        options = _options(config)
        self.api, self.torch, commit = _load_upstream(options, UPSTREAM_COMMIT)
        self.cfg = _config(self.api, options)
        # These are the released LIBERO OFT architecture, not a generic ablation.
        self.cfg.use_l1_regression = True
        self.cfg.use_diffusion = False
        self.cfg.use_film = False
        self.cfg.num_images_in_input = 2
        self.cfg.use_proprio = True
        self.cfg.num_open_loop_steps = 8
        self.cfg.lora_rank = 32
        if self.api.NUM_ACTIONS_CHUNK != 8:
            raise ValueError("Expected the official LIBERO OFT eight-action architecture")
        self.api.set_seed_everywhere(self.cfg.seed)
        self._checkpoint_directory = _checkpoint_view(options["checkpoint"])
        self.cfg.pretrained_checkpoint = self._checkpoint_directory.name
        previous_cwd = Path.cwd()
        try:
            # Upstream searches ./prismatic when syncing the local checkpoint.
            os.chdir(Path(options["repo_path"]).expanduser().resolve())
            (self.model, self.action_head, self.proprio_projector,
             self.noisy_action_projector, self.processor) = self.api.initialize_model(self.cfg)
        except BaseException:
            self._checkpoint_directory.cleanup()
            raise
        finally:
            os.chdir(previous_cwd)
        self.model.eval()
        self.cfg.unnorm_key = _normalization_key(self.model.norm_stats, self.cfg.task_suite_name)
        self.resize_size = self.api.get_image_resize_size(self.cfg)
        self.metadata = {"model": "openvla_oft", "repo_commit": commit, "suite": self.cfg.task_suite_name,
                         "unnorm_key": self.cfg.unnorm_key, "explicit_stop": False, "action_chunk": 8}
        self.metadata["prepared_checkpoint_code_sha256"] = {
            name: hashlib.sha256((Path(self.cfg.pretrained_checkpoint) / name).read_bytes()).hexdigest()
            for name in ("config.json", "modeling_prismatic.py", "configuration_prismatic.py")
            if (Path(self.cfg.pretrained_checkpoint) / name).is_file()
        }
        self._closed = False

    def reset(self):
        if self._closed:
            raise RuntimeError("Policy is closed")
        # No internal queue: run_episode owns chunk truncation and episode reset.

    def predict(self, obs, instruction):
        self.reset()
        instruction = _instruction(instruction)
        raw = _raw_observation(obs, wrist=True, proprio=True)
        observation, _ = self.api.prepare_observation(raw, self.resize_size)
        with self.torch.inference_mode():
            action = self.api.get_action(
                self.cfg, self.model, observation, instruction, processor=self.processor,
                action_head=self.action_head, proprio_projector=self.proprio_projector,
                noisy_action_projector=self.noisy_action_projector, use_film=False,
            )
        action = _action_array(action, chunk=True)
        if action.shape != (8, 7):
            raise ValueError(f"Expected an OFT (8, 7) chunk, got {action.shape}")
        return _decode_action(self.api, action, chunk=True)

    def close(self):
        self.model = self.processor = self.action_head = self.proprio_projector = self.noisy_action_projector = None
        self._checkpoint_directory.cleanup()
        self._closed = True


def make_policy(config):
    return OpenVLAOFTPolicy(config)
