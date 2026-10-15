"""A separate, read-only OFT feature/FINISH adapter using its original forward.

The pinned L1 head calls ``predict_action(hidden)`` directly, bypassing nn.Module
forward hooks. Instance-local method wrappers observe that exact input and the
original model call; a processor proxy copies the two actual cropped images.
Every wrapped method is restored, including on exceptions. No second forward,
crop, processor invocation, action decoding, or runtime queue is introduced.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
import torch

from .model import (FEATURE_VERSION, assert_frozen, canonical_hash, freeze_base_modules,
                    load_head_artifact, module_state_sha256, pool_action_hidden)


def _modules(base):
    result = {name: getattr(base, name, None) for name in
              ("model", "action_head", "proprio_projector", "noisy_action_projector")}
    if result["model"] is None or result["action_head"] is None:
        raise ValueError("finish OFT requires the original model and L1 action head")
    return result


def _file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inventory(directory, *, python_only=False):
    directory = Path(directory).resolve()
    rows = []
    for path in sorted(directory.rglob("*.py" if python_only else "*")):
        if path.is_file() and ".git" not in path.relative_to(directory).parts:
            rows.append({"path": path.relative_to(directory).as_posix(), "bytes": path.stat().st_size,
                         "sha256": _file_sha(path)})
    if not rows:
        raise ValueError("base checkpoint/source identity requires actual files")
    return rows


def base_identity(config, base):
    """Read actual local weights/source identities; never accept a path as a hash."""
    options = config["adapter_options"]
    checkpoint = _inventory(options["checkpoint"])
    source = _inventory(options["repo_path"], python_only=True)
    from ..adapters import openvla, openvla_oft
    return {"schema_version": "remaining-oft-base-identity-v1",
            "checkpoint_files": checkpoint, "checkpoint_content_sha256": canonical_hash(checkpoint),
            "upstream_commit": base.metadata["repo_commit"],
            "upstream_source_sha256": canonical_hash(source),
            "adapter_source_sha256": {"openvla.py": _file_sha(openvla.__file__),
                                      "openvla_oft.py": _file_sha(openvla_oft.__file__)},
            "prepared_checkpoint_code_sha256": deepcopy(base.metadata.get("prepared_checkpoint_code_sha256", {})),
            "parameters_sha256": module_state_sha256(_modules(base)),
            "suite": base.metadata["suite"], "unnorm_key": base.metadata["unnorm_key"]}


def _tensor(value):
    """Copy actual input storage, including lossless BF16 and boolean transport."""
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu().contiguous()
        declared = str(tensor.dtype)
        if tensor.is_floating_point() and not torch.isfinite(tensor).all().item():
            raise ValueError("nonfinite actual OFT input")
        if tensor.dtype == torch.bfloat16:
            array = tensor.view(torch.uint16).numpy().copy()
        elif tensor.dtype == torch.bool:
            array = tensor.to(torch.uint8).numpy().copy()
        else:
            array = tensor.numpy().copy()
    else:
        array = np.asarray(value)
        declared = "numpy." + str(array.dtype)
        if array.dtype.kind == "b":
            array = array.astype(np.uint8)
        else:
            array = array.copy()
    if array.dtype.kind not in "fiu" or not array.size or not np.isfinite(array).all():
        raise ValueError("actual OFT input must have finite numeric storage")
    return array, declared


class _ProcessorCapture:
    def __init__(self, processor, crops):
        self.processor, self.crops = processor, crops

    def __getattr__(self, name):
        return getattr(self.processor, name)

    def __call__(self, *args, **kwargs):
        image = args[1] if len(args) > 1 else kwargs.get("images")
        pixels = np.asarray(image)
        if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError("OFT processor input must be an actual uint8 RGB cropped image")
        self.crops.append(pixels.copy())
        return self.processor(*args, **kwargs)


class _Capture:
    def __init__(self, base):
        self.base = base
        self.crops, self.hidden, self.inputs = [], [], []
        self.restore = []

    def _replace(self, target, name, value):
        local = name in vars(target)
        old = vars(target).get(name)
        setattr(target, name, value)
        self.restore.append((target, name, local, old))

    def __enter__(self):
        action_call = self.base.action_head.predict_action
        model_call = self.base.model.predict_action

        def action_wrapper(*args, **kwargs):
            hidden = args[0] if args else kwargs.get("actions_hidden_states")
            # Pool only the exact original L1 input, before calling it unchanged.
            self.hidden.append(pool_action_hidden(hidden).detach().cpu().numpy().copy())
            return action_call(*args, **kwargs)

        def model_wrapper(*args, **kwargs):
            actual = dict(kwargs)
            if args:
                if len(args) != 1 or "input_ids" in actual:
                    raise ValueError("unsupported OFT predict_action calling convention")
                actual["input_ids"] = args[0]
            names = ("input_ids", "attention_mask", "pixel_values", "proprio")
            if any(name not in actual or actual[name] is None for name in names):
                raise ValueError("actual OFT model input is missing a required field")
            copied = {name: _tensor(actual[name]) for name in names}
            self.inputs.append({"tensors": {key: value[0] for key, value in copied.items()},
                                "tensor_dtypes": {key: value[1] for key, value in copied.items()}})
            return model_call(*args, **kwargs)

        try:
            self._replace(self.base.action_head, "predict_action", action_wrapper)
            self._replace(self.base.model, "predict_action", model_wrapper)
            self._replace(self.base, "processor", _ProcessorCapture(self.base.processor, self.crops))
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *unused):
        for target, name, local, old in reversed(self.restore):
            if local:
                setattr(target, name, old)
            else:
                delattr(target, name)
        self.restore.clear()

    def result(self):
        if len(self.hidden) != 1 or len(self.inputs) != 1 or len(self.crops) != 2:
            raise ValueError("feature capture requires exactly one L1/model prediction and two original crops")
        if self.hidden[0].shape[0] != 1:
            raise ValueError("released OFT inference must have batch size one")
        return self.hidden[0], {"schema_version": "remaining-finish-input-v1", **self.inputs[0],
                                "crops": dict(zip(("agentview", "wrist"), self.crops))}


class OFTFeaturePolicy:
    """Feature-only worker policy. ``predict`` and ``predict_features`` are identical."""
    def __init__(self, config):
        from ..adapters.openvla_oft import OpenVLAOFTPolicy
        if config.get("adapter_options", {}).get("suite") != "libero_10":
            raise ValueError("finish-v1 currently supports only the released SOG10 OFT base")
        self.base = OpenVLAOFTPolicy(config)
        try:
            freeze_base_modules(_modules(self.base))
            self._initialize(base_identity(config, self.base))
        except BaseException:
            self.base.close()
            raise

    @classmethod
    def from_base(cls, base, *, identity):
        """Dependency-injection seam for explicit CPU fakes/parity fixtures."""
        instance = cls.__new__(cls)
        instance.base = base
        freeze_base_modules(_modules(base))
        instance._initialize(identity)
        return instance

    def _initialize(self, identity):
        if not isinstance(identity, dict) or not identity:
            raise ValueError("feature extraction requires an actual base identity")
        self.base_identity = deepcopy(identity)
        self.metadata = {"model": "openvla_oft_readonly_features", "feature_version": FEATURE_VERSION,
                         "base_identity": self.base_identity,
                         "base_identity_sha256": canonical_hash(self.base_identity),
                         "frozen_base": True, "action_chunk": 8, "feature_dtype": "float32"}

    def reset(self):
        self.base.reset()

    def predict_features(self, observation, instruction):
        assert_frozen(_modules(self.base))
        # Old adapter continues to own validation, preprocessing, one forward,
        # original normalization and decoding. It receives no head metadata.
        with _Capture(self.base) as capture:
            actions = self.base.predict(observation, instruction)
        features, inputs = capture.result()
        actions = np.asarray(actions)
        if actions.shape != (8, 7) or actions.dtype.kind not in "fiu" or not np.isfinite(actions).all():
            raise ValueError("original OFT candidate actions must be a finite decoded (8,7) chunk")
        return {"candidate_actions": actions.copy(), "features": features,
                "feature_version": FEATURE_VERSION, "base_identity_sha256": canonical_hash(self.base_identity),
                "input_evidence": inputs}

    def predict(self, observation, instruction):
        return self.predict_features(observation, instruction)

    def close(self):
        self.base.close()


class FinishOFTPolicy(OFTFeaturePolicy):
    def __init__(self, config):
        options = config.get("finish")
        if not isinstance(options, dict) or set(options) - {"head_artifact", "threshold", "threshold_identity"}:
            raise ValueError("finish config requires head_artifact and an explicit threshold")
        if not isinstance(options.get("head_artifact"), str) or not options["head_artifact"]:
            raise ValueError("missing finish head artifact")
        threshold = options.get("threshold")
        if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError("finish threshold must be explicitly in (0,1)")
        # Validate local safe artifact before loading expensive original weights.
        head, artifact = load_head_artifact(options["head_artifact"])
        super().__init__(config)
        try:
            if artifact["identities"]["base_identity"] != self.base_identity:
                raise ValueError("finish head base checkpoint/code identity mismatch")
            self._attach(head, artifact, float(threshold), options.get("threshold_identity"))
        except BaseException:
            self.base.close()
            raise

    @classmethod
    def from_feature_policy(cls, feature_policy, *, head, artifact, threshold):
        instance = cls.__new__(cls)
        instance.base = feature_policy.base
        instance._initialize(feature_policy.base_identity)
        if artifact["identities"]["base_identity"] != instance.base_identity:
            raise ValueError("finish head base checkpoint/code identity mismatch")
        instance._attach(head, artifact, threshold, None)
        return instance

    def _attach(self, head, artifact, threshold, threshold_identity):
        if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError("finish threshold must be in (0,1)")
        self.head = head.to(device="cpu", dtype=torch.float32).eval()
        self.threshold = float(threshold)
        self.head_identity = {"artifact_sha256": artifact["artifact_sha256"], "feature_version": FEATURE_VERSION,
                              "base_identity_sha256": canonical_hash(self.base_identity)}
        self.metadata.update(model="openvla_oft_finish", head_identity=deepcopy(self.head_identity),
                             threshold=self.threshold, threshold_identity=deepcopy(threshold_identity),
                             supported_interface="remaining-finish-policy-v1")

    def predict(self, observation, instruction):
        prediction = self.predict_features(observation, instruction)
        with torch.inference_mode():
            logit_tensor = self.head(torch.from_numpy(prediction["features"]))
            logit = float(logit_tensor.item())
            probability = float(torch.sigmoid(logit_tensor).item())
        if not math.isfinite(logit) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("finish head produced invalid logit/probability")
        return {"schema_version": "remaining-finish-policy-v1",
                "candidate_actions": prediction["candidate_actions"], "logit": logit, "p": probability,
                "threshold": self.threshold, "head_decision": "finish" if probability >= self.threshold else "continue",
                "head_identity": deepcopy(self.head_identity), "input_evidence": prediction["input_evidence"]}


def make_feature_policy(config):
    return OFTFeaturePolicy(config)


def make_policy(config):
    return FinishOFTPolicy(config)


class ParityOFTPolicy:
    """Pair original/new calls inside one model worker, where RNG state lives."""
    def __init__(self, config):
        self.shadow = FinishOFTPolicy(config)
        self.metadata = {**deepcopy(self.shadow.metadata), "purpose": "same-worker-action-parity",
                         "calls_per_input": {"original": 1, "shadow": 1}}

    def reset(self):
        self.shadow.reset()

    def predict(self, observation, instruction):
        state = _rng_state()
        try:
            original = self.shadow.base.predict(deepcopy(observation), instruction)
            _restore_rng(state)
            shadow = self.shadow.predict(deepcopy(observation), instruction)
            return {"schema_version": "remaining-finish-parity-pair-v1",
                    "original_actions": np.asarray(original).copy(), "shadow": shadow,
                    "rng_restored_in_model_worker": True}
        finally:
            _restore_rng(state)

    def close(self):
        self.shadow.close()


def make_parity_policy(config):
    return ParityOFTPolicy(config)


def _rng_state():
    return {"python": random.getstate(), "numpy": np.random.get_state(), "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_initialized() else None}


def _restore_rng(state):
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if state["cuda"] is not None:
        torch.cuda.set_rng_state_all(state["cuda"])


def parity_inputs(original, shadow, inputs, *, atol=0.0, rtol=0.0, required_count=32):
    """Compare fixed independent validation inputs; no simulator or dataset selection.

    Caller supplies audited rows with observation, original instruction, split,
    and distinct input_id. Tolerances are fixed before sampling, never relaxed.
    Each input invokes the original and read-only branch once from equal RNG
    states, restoring the caller's outer RNG even if a prediction fails.
    """
    if type(required_count) is not int or required_count < 1 or len(inputs) != required_count:
        raise ValueError("parity requires the prespecified exact validation input count")
    for value in (atol, rtol):
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("parity tolerance must be finite, nonnegative and declared in advance")
    if any(row.get("split") != "validation" for row in inputs):
        raise ValueError("parity inputs must come only from independent validation")
    identifiers = [row.get("input_id") for row in inputs]
    if any(not isinstance(key, str) or not key for key in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("parity requires unique fixed input identities")
    outer = _rng_state()
    comparisons = []
    try:
        for row in inputs:
            state = _rng_state()
            if original is None:
                pair = shadow.predict(deepcopy(row["observation"]), row["instruction"])
                if (pair.get("schema_version") != "remaining-finish-parity-pair-v1"
                        or pair.get("rng_restored_in_model_worker") is not True):
                    raise ValueError("remote parity must restore RNG inside the model worker")
                old, result = np.asarray(pair["original_actions"]), pair["shadow"]
            else:
                old = np.asarray(original.predict(deepcopy(row["observation"]), row["instruction"]))
                _restore_rng(state)
                result = shadow.predict(deepcopy(row["observation"]), row["instruction"])
            new = np.asarray(result["candidate_actions"])
            if old.shape != (8, 7) or new.shape != old.shape or not np.isfinite(old).all() or not np.isfinite(new).all():
                raise ValueError("parity requires finite original/new (8,7) decoded actions")
            difference = np.abs(old.astype(np.float64) - new.astype(np.float64))
            comparisons.append({"input_id": row["input_id"], "max_abs_error": float(difference.max()),
                                "exact": bool(np.array_equal(old, new)),
                                "passed": bool(np.allclose(old, new, atol=atol, rtol=rtol))})
    finally:
        _restore_rng(outer)
    return {"schema_version": "remaining-finish-action-parity-v1", "expected": required_count,
            "original_calls": len(comparisons), "shadow_calls": len(comparisons), "atol": atol, "rtol": rtol,
            "max_abs_error": max(row["max_abs_error"] for row in comparisons),
            "passed": all(row["passed"] for row in comparisons), "comparisons": comparisons,
            "notice": "Action comparison only; CPU synthetic tests do not establish real CUDA parity."}
