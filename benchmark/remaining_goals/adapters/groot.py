"""GR00T N1.7 LIBERO policy for an isolated model worker.

API reference: NVIDIA/Isaac-GR00T at 51d4c89f72fda44cbf77285c6a8114b52676b8a1,
gr00t/policy/gr00t_policy.py and gr00t/eval/sim/LIBERO/libero_env.py.
This adapter does not import the simulator, inspect goal truth, or invent STOP.
"""
from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np


OFFICIAL_REVISION = "51d4c89f72fda44cbf77285c6a8114b52676b8a1"
OFFICIAL_CHECKPOINT_REVISION = "2ea293aa20ba7cf5bbf3ba17a5fbcb1a01cbfe21"
SUITES = {"libero_10", "libero_90", "libero_spatial", "libero_object", "libero_goal"}
AXES = ("x", "y", "z", "roll", "pitch", "yaw", "gripper")
LANGUAGE_KEY = "annotation.human.action.task_description"


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _json(path):
    if not path.is_file():
        raise FileNotFoundError(f"GR00T N1.7 checkpoint file missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _checkpoint(path):
    """Reject other model generations before importing a GPU framework."""
    config = _json(path / "config.json")
    if config.get("model_type") != "Gr00tN1d7" or "Gr00tN1d7" not in config.get("architectures", []):
        raise ValueError("This adapter requires an actual GR00T N1.7 checkpoint (Gr00tN1d7); no version substitution")
    processor_dir = path if (path / "processor_config.json").is_file() else path / "processor"
    processor = _json(processor_dir / "processor_config.json")
    if processor.get("processor_class") != "Gr00tN1d7Processor":
        raise ValueError("Checkpoint must use Gr00tN1d7Processor")
    modalities = processor.get("processor_kwargs", {}).get("modality_configs", {}).get("libero_sim")
    if not modalities:
        raise ValueError("Checkpoint lacks LIBERO_PANDA/libero_sim finetuning; the N1.7 base model is not a LIBERO checkpoint")
    _modality_contract(modalities)
    _json(processor_dir / "statistics.json")
    _json(processor_dir / "embodiment_id.json")
    index = path / "model.safetensors.index.json"
    if index.is_file():
        mapping = _json(index).get("weight_map")
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Checkpoint safetensors index has no weight_map")
        shards = set(mapping.values())
    else:
        shards = {"model.safetensors"}
    for name in shards:
        if not isinstance(name, str) or not name.endswith(".safetensors"):
            raise ValueError("Invalid checkpoint shard name")
        shard = (path / name).resolve()
        if not shard.is_relative_to(path) or not shard.is_file() or not shard.stat().st_size:
            raise FileNotFoundError(f"Missing or unsafe GR00T checkpoint shard: {name}")


def _modality_contract(modalities):
    expected = {"video": {"image", "wrist_image"}, "state": set(AXES),
                "action": set(AXES), "language": {LANGUAGE_KEY}}
    for name, keys in expected.items():
        entry = modalities.get(name)
        get = entry.get if isinstance(entry, dict) else lambda key: getattr(entry, key, None)
        if entry is None or set(get("modality_keys") or []) != keys:
            raise ValueError(f"Unsupported N1.7 LIBERO {name} modality keys")
        deltas = list(get("delta_indices") or [])
        if name != "action" and deltas != [0]:
            raise ValueError("Only the published single-observation LIBERO input contract is supported")
        if name == "action" and (not deltas or deltas != list(range(len(deltas)))):
            raise ValueError("LIBERO action horizon must start at zero and be contiguous")
    return len(modalities["action"]["delta_indices"] if isinstance(modalities["action"], dict)
               else modalities["action"].delta_indices)


def _load_policy(repo, revision, checkpoint, device):
    source = repo / "gr00t/policy/gr00t_policy.py"
    if not source.is_file():
        raise FileNotFoundError(f"Official Isaac-GR00T checkout missing: {source}")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("repo_revision must be a full 40-character Git commit")
    try:
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Cannot verify the configured GR00T Git checkout") from error
    if actual != revision or dirty.strip():
        raise ValueError("GR00T checkout must match repo_revision with no tracked modifications")
    existing = sys.modules.get("gr00t")
    if existing is not None and not Path(existing.__file__).resolve().is_relative_to(repo):
        raise RuntimeError("Another GR00T installation is already imported; use an isolated model worker")
    sys.path.insert(0, str(repo))
    try:
        module = importlib.import_module("gr00t.policy.gr00t_policy")
    except ImportError as error:
        raise RuntimeError("GR00T N1.7 dependencies are unavailable; use the pinned repository's Python 3.12 uv environment") from error
    if Path(module.__file__).resolve() != source.resolve():
        raise RuntimeError("Imported GR00T policy does not belong to repo_path")
    return module.Gr00tPolicy(embodiment_tag="LIBERO_PANDA", model_path=str(checkpoint),
                              device=device, strict=True)


def _vector(obs, key, size):
    result = np.asarray(obs[key])
    if result.shape != (size,) or result.dtype.kind not in "fiu" or not np.isfinite(result).all():
        raise ValueError(f"{key} must be a finite real vector of length {size}")
    return result.astype(np.float64, copy=True)


def _policy_observation(obs, instruction):
    if not isinstance(obs, dict):
        raise ValueError("LIBERO policy observation must be a dictionary")
    _text(instruction, "instruction")
    video = {}
    for target, raw in (("image", "agentview_image"), ("wrist_image", "robot0_eye_in_hand_image")):
        pixels = np.asarray(obs[raw])
        if pixels.dtype != np.uint8 or pixels.shape != (256, 256, 3):
            raise ValueError(f"{raw} must be raw LIBERO uint8 RGB with shape (256,256,3)")
        video[target] = np.ascontiguousarray(pixels[::-1, ::-1])[None, None]
    xyz = _vector(obs, "robot0_eef_pos", 3)
    quat = _vector(obs, "robot0_eef_quat", 4)  # xyzw; do not change caller's array.
    if not np.isclose(np.linalg.norm(quat), 1.0, rtol=0.0, atol=1e-5):
        raise ValueError("robot0_eef_quat must be a unit xyzw quaternion")
    w = float(np.clip(quat[3], -1.0, 1.0))
    denominator = math.sqrt(1.0 - w * w)
    rotvec = np.zeros(3) if math.isclose(denominator, 0.0) else quat[:3] * (2.0 * math.acos(w) / denominator)
    state = {key: np.asarray([[[value]]], dtype=np.float32)
             for key, value in zip(AXES[:6], np.concatenate((xyz, rotvec)))}
    state["gripper"] = _vector(obs, "robot0_gripper_qpos", 2).astype(np.float32)[None, None]
    # Explicit construction ensures other fields (including any evaluator data)
    # never reach the model. Image resize/crop and action unnormalization belong
    # exclusively to the checkpoint's official processor.
    return {"video": video, "state": state, "language": {LANGUAGE_KEY: [[instruction]]}}


class GrootPolicy:
    def __init__(self, config):
        if not isinstance(config, dict) or not isinstance(config.get("adapter_options"), dict):
            raise ValueError("make_policy expects the complete JSON config with adapter_options")
        if config.get("model_id") != "groot_n1_7":
            raise ValueError("model_id must be groot_n1_7")
        options = config["adapter_options"]
        self.suite = _text(options.get("suite"), "adapter_options.suite")
        if self.suite not in SUITES or config.get("suite") != self.suite:
            raise ValueError("Top-level suite and adapter_options.suite must name the same LIBERO suite")
        if options.get("checkpoint_suite") != self.suite:
            raise ValueError("checkpoint_suite must equal suite; no silent cross-suite checkpoint/normalization substitution")
        checkpoint = Path(_text(options.get("checkpoint"), "adapter_options.checkpoint")).expanduser().resolve()
        repo = Path(_text(options.get("repo_path"), "adapter_options.repo_path")).expanduser().resolve()
        revision = _text(options.get("repo_revision", OFFICIAL_REVISION), "adapter_options.repo_revision")
        device = _text(options.get("device", "cuda:0"), "adapter_options.device")
        _checkpoint(checkpoint)
        self._policy = _load_policy(repo, revision, checkpoint, device)
        self._horizon = _modality_contract(self._policy.get_modality_config())
        self.metadata = {"model_id": "groot_n1_7", "repo_commit": revision,
                         "suite": self.suite, "checkpoint_suite": options["checkpoint_suite"],
                         "checkpoint": str(checkpoint), "embodiment_tag": "LIBERO_PANDA",
                         "normalization": "checkpoint processor.decode_action; no second normalization",
                         "native_prediction_steps": self._horizon,
                         "gripper_mapping": "-sign(2*g-1)", "explicit_stop": False,
                         "weight_bytes_verified": False}
        self._closed = False

    def reset(self):
        if self._closed:
            raise RuntimeError("GR00T policy is closed")
        self._policy.reset()

    def predict(self, obs, instruction):
        if self._closed:
            raise RuntimeError("GR00T policy is closed")
        result = self._policy.get_action(_policy_observation(obs, instruction))
        if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], dict):
            raise ValueError("GR00T get_action must return (action_dict, info_dict), never a fabricated STOP")
        values = []
        for key in AXES:
            value = np.asarray(result[0].get(key))
            if value.shape != (1, self._horizon, 1) or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
                raise ValueError(f"GR00T {key} must be finite with shape (1,{self._horizon},1)")
            values.append(value[0].astype(np.float64))
        actions = np.concatenate(values, axis=1)
        # The official LIBERO wrapper applies this after processor.decode_action.
        # A midpoint prediction retains zero, exactly as np.sign in that wrapper.
        actions[:, 6] = -np.sign(2.0 * actions[:, 6] - 1.0)
        return actions

    def close(self):
        if not self._closed:
            policy, self._policy = self._policy, None
            self._closed = True
            close = getattr(policy, "close", None)
            if callable(close):
                close()


def make_policy(config):
    """Instantiate in the configured model worker, not the simulator process."""
    return GrootPolicy(config)
