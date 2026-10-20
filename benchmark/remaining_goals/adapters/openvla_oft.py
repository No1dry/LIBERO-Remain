"""Official OpenVLA-OFT LIBERO L1 policy (two images, proprio, eight actions)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from .openvla import (_action_array, _config, _decode_action, _instruction,
                      _load_upstream, _normalization_key, _options, _raw_observation)
from .oft_transfer import validate_suite_transfer, is_sog10, TRAINING_SUITES, INFERENCE_SOURCES

UPSTREAM_COMMIT = "e4287e94541f459edc4feabc4e181f537cd569a8"
UPSTREAM_REPO = "https://github.com/moojink/openvla-oft"


def _statistics_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def _file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _initialize_transferred(api, cfg, transfer):
    """Keep the official loader; replace only its suite-derived stats selector.

    The pinned loader calls check_unnorm_key once. A fresh isolated worker owns
    this module; the hook is restored even on failure. The model cfg remains
    LIBERO90 throughout, and no upstream file or normalization data is edited.
    """
    original = api.check_unnorm_key
    seen = []
    def check(config, model):
        if config is not cfg or config.task_suite_name != "libero_90":
            raise ValueError("OFT transfer initialization changed evaluation suite")
        key = transfer["normalization_key"]
        if key not in model.norm_stats:
            raise ValueError("SOG10 checkpoint lacks the explicitly requested normalization key")
        config.unnorm_key = key
        seen.append(key)
    try:
        api.check_unnorm_key = check
        result = api.initialize_model(cfg)
        if seen != [transfer["normalization_key"]]:
            raise ValueError("pinned OFT loader did not use its expected normalization-check interface")
        return result
    finally:
        api.check_unnorm_key = original


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
        transfer = validate_suite_transfer(config)
        options = _options(config, extra=("suite_transfer",),
                           normalization_suite=transfer["normalization_suite"] if transfer else None)
        statistics_path = Path(options["checkpoint"]) / "dataset_statistics.json"
        statistics_raw = statistics_path.read_bytes()
        statistics = json.loads(statistics_raw)
        if transfer and transfer["normalization_key"] not in statistics:
            raise ValueError("SOG10 checkpoint lacks the explicitly requested normalization key")
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
             self.noisy_action_projector, self.processor) = (
                _initialize_transferred(self.api, self.cfg, transfer) if transfer else self.api.initialize_model(self.cfg))
        except BaseException:
            self._checkpoint_directory.cleanup()
            raise
        finally:
            os.chdir(previous_cwd)
        self.model.eval()
        self.cfg.unnorm_key = transfer["normalization_key"] if transfer else _normalization_key(self.model.norm_stats, self.cfg.task_suite_name)
        self.resize_size = self.api.get_image_resize_size(self.cfg)
        self.metadata = {"model": "openvla_oft", "repo_commit": commit, "suite": self.cfg.task_suite_name,
                         "unnorm_key": self.cfg.unnorm_key, "explicit_stop": False, "action_chunk": 8}
        try:
            loaded_stats = self.model.norm_stats[self.cfg.unnorm_key]
            if _statistics_digest(loaded_stats) != _statistics_digest(statistics[self.cfg.unnorm_key]):
                raise ValueError("loaded OFT normalization statistics differ from checkpoint dataset_statistics.json")
            self.metadata.update(evaluation_suite=self.cfg.task_suite_name,
                checkpoint=options["checkpoint"], checkpoint_source=config.get("checkpoint_source"),
                checkpoint_training_suites=list(TRAINING_SUITES) if is_sog10(config) else None,
                normalization_suite=transfer["normalization_suite"] if transfer else self.cfg.task_suite_name,
                evaluation_track=transfer["evaluation_track"] if transfer else
                    "libero_10_primary" if is_sog10(config) and self.cfg.task_suite_name == "libero_10" else "same_suite",
                suite_transfer=transfer, dataset_statistics_sha256=hashlib.sha256(statistics_raw).hexdigest(),
                normalization_statistics_sha256=_statistics_digest(loaded_stats))
            repo = Path(options["repo_path"]).expanduser().resolve()
            self.metadata["inference_source_sha256"] = {name: _file_digest(repo / name)
                for name in INFERENCE_SOURCES if (repo / name).is_file()}
            self.metadata["component_checkpoint_sha256"] = {path.name: _file_digest(path)
                for path in sorted(Path(self.cfg.pretrained_checkpoint).iterdir()) if path.is_file()
                and "checkpoint" in path.name and any(name in path.name for name in ("action_head", "proprio_projector"))}
            self.metadata["inference_configuration"] = {name: getattr(self.cfg, name) for name in (
                "center_crop", "load_in_8bit", "load_in_4bit", "use_l1_regression", "use_diffusion", "use_film",
                "num_images_in_input", "use_proprio", "num_open_loop_steps", "lora_rank")}
        except BaseException:
            self._checkpoint_directory.cleanup()
            raise
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
