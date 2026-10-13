"""Small FP32 finish head and pickle-free, identity-bound weight artifacts.

Import this module only in the selected training/model interpreter. It does not
load a VLA, download weights, initialize CUDA, or run an experiment on import.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import torch
from torch import nn


FEATURE_VERSION = "oft-l1-action56-mean-v1"
HEAD_SCHEMA = "remaining-finish-head-v1"
IDENTITY_FIELDS = {"base_identity", "data_identity", "split_identity", "label_contract"}
MAX_HEAD_BYTES = 128 * 1024 * 1024


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate artifact JSON key: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite artifact value: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=invalid)


def pool_action_hidden(hidden):
    """Pool exactly the L1 method's 56 input tokens; never slice a full sequence."""
    if (not isinstance(hidden, torch.Tensor) or hidden.ndim != 3 or hidden.shape[0] < 1
            or hidden.shape[1] != 56 or hidden.shape[2] < 1 or not hidden.is_floating_point()
            or not torch.isfinite(hidden).all().item()):
        raise ValueError("finish features require finite floating action hidden states (B,56,D)")
    return hidden.detach().to(dtype=torch.float32).mean(dim=1)


class FinishHead(nn.Module):
    def __init__(self, dimension):
        super().__init__()
        if type(dimension) is not int or not 1 <= dimension <= 65536:
            raise ValueError("finish feature dimension must be an integer in [1,65536]")
        self.dimension = dimension
        self.net = nn.Sequential(nn.LayerNorm(dimension), nn.Linear(dimension, 128),
                                 nn.GELU(), nn.Linear(128, 1)).float()

    def forward(self, features):
        if (not isinstance(features, torch.Tensor) or features.ndim != 2
                or features.shape[0] < 1 or features.shape[1] != self.dimension
                or not features.is_floating_point() or not torch.isfinite(features).all().item()):
            raise ValueError("head input must be a finite (B,D) floating feature tensor")
        if any(parameter.dtype != torch.float32 for parameter in self.parameters()):
            raise ValueError("finish head parameters must remain FP32")
        parameter = next(self.parameters())
        return self.net(features.detach().to(device=parameter.device, dtype=torch.float32)).squeeze(-1)


def freeze_base_modules(modules):
    """Freeze every supplied base component, including LoRA/projectors/action head."""
    for module in modules.values():
        if module is None:
            continue
        if not isinstance(module, nn.Module):
            raise TypeError("base components must be torch modules")
        module.eval()
        for parameter in module.parameters():
            parameter.requires_grad_(False)
            parameter.grad = None
    assert_frozen(modules)


def assert_frozen(modules):
    for name, module in modules.items():
        if module is None:
            continue
        if any(part.training for part in module.modules()):
            raise ValueError(f"base module left eval mode: {name}")
        if any(parameter.requires_grad or parameter.grad is not None for parameter in module.parameters()):
            raise ValueError(f"base module is trainable or has gradients: {name}")


def module_state_sha256(modules):
    """Hash names/dtypes/shapes and exact weights/buffers, one tensor at a time."""
    digest = hashlib.sha256()
    for name, module in sorted(modules.items()):
        if module is None:
            continue
        for key, value in sorted(module.state_dict().items()):
            tensor = value.detach().cpu().contiguous()
            descriptor = [name, key, str(tensor.dtype), list(tensor.shape)]
            digest.update(json.dumps(descriptor, separators=(",", ":")).encode())
            digest.update(tensor.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def _identities(value):
    if (not isinstance(value, dict) or set(value) != IDENTITY_FIELDS
            or any(not isinstance(item, dict) or not item for item in value.values())):
        raise ValueError("head identities require nonempty base/data/split/label-contract objects")
    canonical_hash(value)
    return deepcopy(value)


def _architecture(dimension):
    return {"name": "LayerNorm-Linear128-GELU-Linear1", "dimension": dimension,
            "hidden_dimension": 128, "dtype": "float32", "dropout": 0.0,
            "feature_version": FEATURE_VERSION, "action_tokens": 56, "pooling": "mean"}


def save_head_artifact(output, head, *, identities, training):
    identities = _identities(identities)
    if not isinstance(head, FinishHead):
        raise TypeError("only the declared FinishHead architecture can be saved")
    if not isinstance(training, dict) or not training:
        raise ValueError("head artifact requires training provenance")
    canonical_hash(training)
    arrays = {name: value.detach().cpu().numpy().copy() for name, value in head.state_dict().items()}
    if any(value.dtype != np.float32 or not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("head weights must be finite FP32")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    weights = output / "head.npz"
    with weights.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    manifest = {"schema_version": HEAD_SCHEMA, "architecture": _architecture(head.dimension),
                "identities": identities,
                "identity_sha256": {key: canonical_hash(value) for key, value in identities.items()},
                "training": deepcopy(training),
                "implementation_sha256": {
                    name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in ("model.py", "training.py", "oft.py")},
                "weights": {"path": "head.npz", "sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                            "format": "numpy-npz-no-pickle", "bytes": weights.stat().st_size},
                "notice": "Finish head only; base action weights are neither stored nor updated."}
    manifest["artifact_sha256"] = canonical_hash(manifest)
    (output / "head.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def load_head_artifact(path, *, expected_base_identity=None):
    path = Path(path)
    path = path / "head.json" if path.is_dir() else path
    manifest = read_json(path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != HEAD_SCHEMA:
        raise ValueError("unsupported finish head artifact version")
    payload = {key: value for key, value in manifest.items() if key != "artifact_sha256"}
    if manifest.get("artifact_sha256") != canonical_hash(payload):
        raise ValueError("finish head artifact hash mismatch")
    identities = _identities(manifest.get("identities"))
    if manifest.get("identity_sha256") != {key: canonical_hash(value) for key, value in identities.items()}:
        raise ValueError("finish head identities hash mismatch")
    if expected_base_identity is not None and identities["base_identity"] != expected_base_identity:
        raise ValueError("finish head base checkpoint/code identity mismatch")
    architecture = manifest.get("architecture", {})
    dimension = architecture.get("dimension")
    if type(dimension) is not int or architecture != _architecture(dimension):
        raise ValueError("finish head architecture/feature version differs")
    # Initializing a then-overwritten head must not consume the action policy RNG.
    with torch.random.fork_rng(devices=[]):
        head = FinishHead(dimension)
    reference = manifest.get("weights", {})
    if reference.get("path") != "head.npz" or reference.get("format") != "numpy-npz-no-pickle":
        raise ValueError("unsafe head weight path or format")
    weights = path.parent / "head.npz"
    if not weights.resolve().is_relative_to(path.parent.resolve()) or weights.stat().st_size > MAX_HEAD_BYTES:
        raise ValueError("head weights must be contained and within the size limit")
    raw = weights.read_bytes()
    if (len(raw) > MAX_HEAD_BYTES or len(raw) != reference.get("bytes")
            or hashlib.sha256(raw).hexdigest() != reference.get("sha256")):
        raise ValueError("finish head weights hash/size mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (len(members) != len(head.state_dict()) or len({m.filename for m in members}) != len(members)
                or sum(m.file_size for m in members) > MAX_HEAD_BYTES):
            raise ValueError("invalid or oversized head archive")
    state = {}
    with np.load(io.BytesIO(raw), allow_pickle=False) as packed:
        if set(packed.files) != set(head.state_dict()):
            raise ValueError("finish head weight keys differ")
        for key, template in head.state_dict().items():
            value = packed[key]
            if value.dtype != np.float32 or value.shape != tuple(template.shape) or not np.isfinite(value).all():
                raise ValueError(f"invalid finish head weight: {key}")
            state[key] = torch.from_numpy(value.copy())
    head.load_state_dict(state, strict=True)
    head.eval()
    return head, manifest
