"""OpenVLA's official LIBERO inference path, loaded only inside its model worker.

Images remain raw until the upstream get_libero_image call (180-degree rotation,
JPEG roundtrip, Lanczos resize); get_action applies the official 0.9-area crop.
The benchmark owns simulation, warmup, episode length and chunk scheduling.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping

import numpy as np

UPSTREAM_COMMIT = "c8f03f48af692657d3060c19588038c7220e9af9"
UPSTREAM_REPO = "https://github.com/openvla/openvla"
_BASE_OPTIONS = {"repo_path", "repo_revision", "checkpoint", "suite", "seed", "center_crop",
                 "load_in_8bit", "load_in_4bit"}
_SUITES = {"libero_spatial", "libero_object", "libero_goal", "libero_10", "libero_90"}


def _options(config, extra=()):
    if not isinstance(config, Mapping) or not isinstance(config.get("adapter_options"), Mapping):
        raise ValueError("config.adapter_options must be an object")
    options = dict(config["adapter_options"])
    unknown = set(options) - _BASE_OPTIONS - set(extra)
    if unknown:
        raise ValueError(f"Unknown adapter_options: {sorted(unknown)}")
    execution_seed = config.get("execution", {}).get("random_seed")
    if execution_seed is not None:
        if "seed" in options and options["seed"] != execution_seed:
            raise ValueError("adapter_options.seed and execution.random_seed differ")
        options["seed"] = execution_seed
    for key in ("repo_path", "checkpoint", "suite"):
        if not isinstance(options.get(key), str) or not options[key].strip():
            raise ValueError(f"adapter_options.{key} must be a nonempty string")
    if options["suite"] not in _SUITES:
        raise ValueError(f"Unsupported LIBERO suite: {options['suite']}")
    if config.get("suite") is not None and config["suite"] != options["suite"]:
        raise ValueError("Top-level suite and adapter_options.suite differ")
    for key in ("center_crop", "load_in_8bit", "load_in_4bit"):
        if key in options and type(options[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if options.get("load_in_8bit") and options.get("load_in_4bit"):
        raise ValueError("8-bit and 4-bit loading are mutually exclusive")
    if type(options.get("seed", 7)) is not int or options.get("seed", 7) < 0:
        raise ValueError("seed must be a nonnegative integer")
    checkpoint = Path(options["checkpoint"]).expanduser().resolve()
    if not checkpoint.is_dir():
        raise ValueError("checkpoint must be a downloaded local checkpoint directory")
    stats_file = checkpoint / "dataset_statistics.json"
    if not stats_file.is_file():
        raise ValueError("checkpoint is missing dataset_statistics.json")
    with stats_file.open(encoding="utf-8") as handle:
        stats = json.load(handle)
    _normalization_key(stats, options["suite"])
    options["checkpoint"] = str(checkpoint)
    return options


def _normalization_key(stats, suite):
    # This is the only upstream alias: never substitute another task suite.
    for key in (suite, f"{suite}_no_noops"):
        if key in stats:
            return key
    raise ValueError(f"Checkpoint has no action statistics for {suite}; another suite's statistics cannot be substituted")


def _load_upstream(options, revision):
    repo = Path(options["repo_path"]).expanduser().resolve()
    relative = Path("experiments/robot/libero/run_libero_eval.py")
    if not (repo / relative).is_file():
        raise ValueError(f"Official evaluation source missing: {repo / relative}")
    expected = options.get("repo_revision", revision)
    if not isinstance(expected, str) or not 7 <= len(expected) <= 40 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("repo_revision must be a pinned hexadecimal Git commit (7-40 characters)")
    actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if not actual.startswith(expected):
        raise ValueError(f"Upstream revision mismatch: expected {expected}, got {actual}")
    # The three repositories intentionally share top-level module names. Never
    # silently reuse a different model's already-imported implementation.
    for name, module in list(sys.modules.items()):
        if name.split(".")[0] in {"experiments", "prismatic"}:
            filename = getattr(module, "__file__", None)
            paths = [filename] if filename else list(getattr(module, "__path__", ()))
            if any(not Path(path).resolve().is_relative_to(repo) for path in paths):
                raise RuntimeError("Conflicting upstream modules loaded; use a fresh dedicated model worker")
    sys.path.insert(0, str(repo))
    api = importlib.import_module("experiments.robot.libero.run_libero_eval")
    if Path(api.__file__).resolve() != (repo / relative).resolve():
        raise RuntimeError("Imported evaluation module did not come from repo_path")
    torch = importlib.import_module("torch")
    return api, torch, actual


def _config(api, options):
    cfg = api.GenerateConfig()
    cfg.pretrained_checkpoint = options["checkpoint"]
    cfg.task_suite_name = options["suite"]
    cfg.seed = options.get("seed", 7)
    cfg.center_crop = options.get("center_crop", True)
    cfg.load_in_8bit = options.get("load_in_8bit", False)
    cfg.load_in_4bit = options.get("load_in_4bit", False)
    return cfg


def _raw_observation(obs, *, wrist=False, proprio=False):
    if not isinstance(obs, Mapping):
        raise ValueError("Observation must be a mapping")
    clean = {}
    keys = ["agentview_image"] + (["robot0_eye_in_hand_image"] if wrist else [])
    for key in keys:
        value = obs.get(key)
        if not isinstance(value, np.ndarray) or value.dtype != np.uint8 or value.ndim != 3 or value.shape[-1] != 3 or min(value.shape[:2]) < 1:
            raise ValueError(f"{key} must be a raw HxWx3 uint8 image")
        clean[key] = value.copy()
    if proprio:
        for key, size in (("robot0_eef_pos", 3), ("robot0_eef_quat", 4), ("robot0_gripper_qpos", 2)):
            value = np.asarray(obs.get(key))
            if value.shape != (size,) or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
                raise ValueError(f"{key} must be a finite {size}-vector")
            clean[key] = value.copy()  # upstream quat2axisangle clips its input in place
    return clean


def _action_array(action, *, chunk=False):
    value = np.array(action, dtype=np.float64, copy=True)
    valid_shape = value.ndim == 2 and value.shape[1] == 7 and value.shape[0] > 0 if chunk else value.shape == (7,)
    if not valid_shape or not np.isfinite(value).all():
        raise ValueError("Official policy returned invalid/non-finite action shape")
    return value


def _decode_action(api, action, *, chunk=False):
    value = _action_array(action, chunk=chunk)
    value = api.normalize_gripper_action(value, binarize=True)
    value = api.invert_gripper_action(value)
    return _action_array(value, chunk=chunk)


def _instruction(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instruction must be a nonempty string")
    return value


class OpenVLAPolicy:
    def __init__(self, config):
        options = _options(config)
        self.api, self.torch, commit = _load_upstream(options, UPSTREAM_COMMIT)
        self.cfg = _config(self.api, options)
        self.api.set_seed_everywhere(self.cfg.seed)
        self.model = self.api.get_model(self.cfg)
        self.model.eval()
        self.cfg.unnorm_key = _normalization_key(self.model.norm_stats, self.cfg.task_suite_name)
        self.processor = self.api.get_processor(self.cfg)
        self.resize_size = self.api.get_image_resize_size(self.cfg)
        self.metadata = {"model": "openvla", "repo_commit": commit, "suite": self.cfg.task_suite_name,
                         "unnorm_key": self.cfg.unnorm_key, "explicit_stop": False, "action_chunk": 1}
        self._closed = False

    def reset(self):
        if self._closed:
            raise RuntimeError("Policy is closed")

    def predict(self, obs, instruction):
        self.reset()
        instruction = _instruction(instruction)
        raw = _raw_observation(obs)
        image = self.api.get_libero_image(raw, self.resize_size)
        with self.torch.inference_mode():
            action = self.api.get_action(self.cfg, self.model, {"full_image": image}, instruction, processor=self.processor)
        return _decode_action(self.api, action)

    def close(self):
        self.model = self.processor = None
        self._closed = True


def make_policy(config):
    return OpenVLAPolicy(config)
