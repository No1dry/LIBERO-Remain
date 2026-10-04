"""Official openpi LIBERO pi0/pi0.5 policies, loaded only inside a model worker.

The checkpoint's official ``create_trained_policy`` owns normalization,
tokenization, state padding and output transforms (including the legacy pi0
extra-delta inverse). This adapter owns only the official LIBERO observation
conversion. Output is a native action chunk in LIBERO's seven-dimensional
controller coordinates; the benchmark runner owns open-loop truncation.

No goal predicates, object poses, masks, or automatic STOP enter this policy.
The explicit sampling noise is seeded per episode for paired comparisons.
Its Gaussian distribution matches the flow sampler, but its NumPy sequence is
not the official server's default JAX RNG sequence. Model weights have not been
validated merely by importing this module or passing the adapter unit tests.
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path
import subprocess
import sys

import numpy as np


UPSTREAM_REPO = "https://github.com/Physical-Intelligence/openpi"
UPSTREAM_COMMIT = "215abfb217dbac7d5f1273282331b9b1866c0479"
NORMALIZATION_KEY = "physical-intelligence/libero"
SUPPORTED_SUITES = frozenset({"libero_spatial", "libero_object", "libero_goal", "libero_10", "libero_90"})
_MODEL_CONFIGS = {"pi0": ("pi0_libero", 50), "pi05": ("pi05_libero", 10)}


def _positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonempty_string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _options(config):
    if not isinstance(config, dict) or not isinstance(config.get("model_id"), str) or config["model_id"] not in _MODEL_CONFIGS:
        raise ValueError("openpi adapter requires model_id 'pi0' or 'pi05'")
    options = config.get("adapter_options")
    if not isinstance(options, dict):
        raise ValueError("adapter_options must be an object")
    options = dict(options)
    model_id = config["model_id"]
    expected_config, horizon = _MODEL_CONFIGS[model_id]
    if options.get("train_config") != expected_config:
        raise ValueError(f"{model_id} requires train_config={expected_config!r}")
    suite = options.get("suite")
    if not isinstance(suite, str) or suite not in SUPPORTED_SUITES or suite != config.get("suite"):
        raise ValueError("adapter_options.suite must be a supported LIBERO suite matching top-level suite")
    if suite == "libero_90" and options.get("evaluation_track") != "zero_shot_extension":
        raise ValueError("LIBERO90 is outside the official four-suite fine-tuning mixture; explicitly set evaluation_track='zero_shot_extension'")
    _nonempty_string(options.get("repo_path"), "adapter_options.repo_path")
    _nonempty_string(options.get("checkpoint"), "adapter_options.checkpoint (LIBERO-finetuned weights)")
    if any(options.get(key, UPSTREAM_COMMIT) != UPSTREAM_COMMIT for key in ("repo_revision", "revision")):
        raise ValueError(f"This adapter is audited against openpi commit {UPSTREAM_COMMIT}")
    if options.get("normalization_key", NORMALIZATION_KEY) != NORMALIZATION_KEY:
        raise ValueError(f"Official LIBERO configs require checkpoint normalization asset {NORMALIZATION_KEY!r}")
    seed = options.get("random_seed")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("adapter_options.random_seed must be an integer in [0, 2**32)")
    steps = _positive_int(options.get("num_inference_steps", 10), "num_inference_steps")
    execution = config.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution must be an object")
    chunk = _positive_int(execution.get("max_chunk_steps"), "execution.max_chunk_steps")
    if chunk > horizon:
        raise ValueError("execution.max_chunk_steps exceeds the model's native prediction horizon")
    if "replan_steps" in options and options["replan_steps"] != chunk:
        raise ValueError("Legacy replan_steps must equal execution.max_chunk_steps; runner owns truncation")
    device = options.get("pytorch_device")
    if device is not None:
        _nonempty_string(device, "pytorch_device")
    options.update(random_seed=seed, num_inference_steps=steps, native_horizon=horizon)
    return options


def _load_components(options):
    """Verify an editable official checkout before importing its heavy modules."""
    repo = Path(options["repo_path"]).expanduser().resolve()
    if not (repo / "src/openpi/training/config.py").is_file():
        raise ValueError("repo_path must identify an official openpi checkout installed in the model environment")
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no", "--", "src", "packages/openpi-client"],
            text=True, stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Cannot verify the official openpi Git checkout") from exc
    if commit != UPSTREAM_COMMIT or dirty:
        raise ValueError("openpi checkout must match the pinned commit with unmodified model/client sources")
    sys.path[:0] = [str(repo / "src"), str(repo / "packages/openpi-client/src")]
    try:
        training = importlib.import_module("openpi.training.config")
        policies = importlib.import_module("openpi.policies.policy_config")
        images = importlib.import_module("openpi_client.image_tools")
    except ImportError as exc:
        raise RuntimeError("Install openpi's pinned uv environment separately from the simulation environment") from exc
    for module in (training, policies, images):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(repo):
            raise RuntimeError(f"Imported {module.__name__} from a different checkout: {path}")
    return training, policies, images


def _vector(obs, key, size):
    if key not in obs:
        raise ValueError(f"Missing raw LIBERO observation: {key}")
    value = np.asarray(obs[key])
    if value.shape != (size,) or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
        raise ValueError(f"{key} must be a finite numeric vector of shape ({size},)")
    return value.copy()


def _quat_to_axis_angle(quaternion):
    """LIBERO xyzw quaternion conversion used by official examples/libero/main.py."""
    quat = np.asarray(quaternion).copy()
    scalar = float(np.clip(quat[3], -1.0, 1.0))
    denominator = math.sqrt(1.0 - scalar * scalar)
    if math.isclose(denominator, 0.0):
        return np.zeros(3)
    return quat[:3] * (2.0 * math.acos(scalar) / denominator)


def prepare_observation(obs, instruction, image_tools):
    """Copy the five official raw sensor fields into openpi's LIBERO input dict.

    Extra observation fields are never forwarded. Images are native uint8 RGB
    HWC, rotated 180 degrees before the official bilinear resize-with-pad.
    Proprioception is xyz + quaternion-to-axis-angle + both finger positions.
    """
    if not isinstance(obs, dict):
        raise ValueError("obs must be a raw LIBERO observation dict")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("instruction must be a nonempty string")
    converted = {}
    for raw_key, policy_key in (
        ("agentview_image", "observation/image"),
        ("robot0_eye_in_hand_image", "observation/wrist_image"),
    ):
        if raw_key not in obs:
            raise ValueError(f"Missing raw LIBERO observation: {raw_key}")
        image = np.asarray(obs[raw_key])
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 1:
            raise ValueError(f"{raw_key} must be a nonempty uint8 HWC RGB image")
        rotated = np.ascontiguousarray(image[::-1, ::-1]).copy()
        converted[policy_key] = image_tools.convert_to_uint8(image_tools.resize_with_pad(rotated, 224, 224))
    converted["observation/state"] = np.concatenate((
        _vector(obs, "robot0_eef_pos", 3),
        _quat_to_axis_angle(_vector(obs, "robot0_eef_quat", 4)),
        _vector(obs, "robot0_gripper_qpos", 2),
    ))
    converted["prompt"] = instruction
    return converted


class OpenPILiberoPolicy:
    def __init__(self, config):
        self.options = _options(config)
        training, policies, self._image_tools = _load_components(self.options)
        train_config = training.get_config(self.options["train_config"])
        expected_pi05 = config["model_id"] == "pi05"
        if (
            train_config.model.action_horizon != self.options["native_horizon"]
            or train_config.model.action_dim != 32
            or train_config.model.pi05 is not expected_pi05
            or train_config.data.repo_id != NORMALIZATION_KEY
            or train_config.data.extra_delta_transform is not (not expected_pi05)
        ):
            raise ValueError("Installed openpi LIBERO config disagrees with the audited model/data transforms")
        kwargs = {"sample_kwargs": {"num_steps": self.options["num_inference_steps"]}}
        if self.options.get("pytorch_device") is not None:
            kwargs["pytorch_device"] = self.options["pytorch_device"]
        # Official loader reads checkpoint/assets/physical-intelligence/libero/
        # norm_stats.json and applies the correct model-specific output pipeline.
        self._policy = policies.create_trained_policy(train_config, self.options["checkpoint"], **kwargs)
        self.metadata = {
            "model_id": config["model_id"], "repo_commit": UPSTREAM_COMMIT,
            "suite": self.options["suite"], "checkpoint": self.options["checkpoint"],
            "evaluation_track": "zero_shot_extension" if self.options["suite"] == "libero_90" else "official_four_suite",
            "train_config": self.options["train_config"], "normalization_key": NORMALIZATION_KEY,
            "native_prediction_steps": self.options["native_horizon"],
            "max_chunk_steps": config["execution"]["max_chunk_steps"],
            "random_seed": self.options["random_seed"],
            "seed_scope": "NumPy PCG64 float32 Gaussian flow noise; reset same stream per episode; paired masks share stream",
            "sampling_matches_official_default_rng": False,
            "explicit_stop": False, "actions_already_unnormalized": True,
            "additional_gripper_transform": "identity",
        }
        self._closed = False
        self.reset()

    def reset(self):
        if self._closed:
            raise RuntimeError("Policy is closed")
        self._rng = np.random.default_rng(self.options["random_seed"])
        reset = getattr(self._policy, "reset", None)
        if callable(reset):
            reset()

    def predict(self, obs, instruction):
        if self._closed:
            raise RuntimeError("Policy is closed")
        inputs = prepare_observation(obs, instruction, self._image_tools)
        noise = self._rng.standard_normal((self.options["native_horizon"], 32), dtype=np.float32)
        prediction = self._policy.infer(inputs, noise=noise)
        if not isinstance(prediction, dict) or "actions" not in prediction:
            raise ValueError("Official openpi infer() must return an actions dict")
        action = np.asarray(prediction["actions"])
        expected_shape = (self.options["native_horizon"], 7)
        if action.shape != expected_shape or action.dtype.kind not in "fiu" or not np.isfinite(action).all():
            raise ValueError(f"Official openpi must return finite {expected_shape} unnormalized LIBERO actions")
        # Do not unnormalize twice, add xyz/state again, flip/binarize the gripper,
        # or clip here: official LiberoOutputs already returns env.step actions.
        return action.copy()

    def close(self):
        if self._closed:
            return
        close = getattr(self._policy, "close", None)
        try:
            if callable(close):
                close()
        finally:
            self._policy = None
            self._closed = True


def make_policy(config):
    """Factory accepting the full benchmark JSON; loader options live in adapter_options."""
    return OpenPILiberoPolicy(config)
