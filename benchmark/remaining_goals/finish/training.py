"""Explicit finish-head training over an audited cache; no action-policy optimizer."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re

import numpy as np
import torch
from torch import nn

from .model import (FinishHead, _identities, assert_frozen, canonical_hash,
                    freeze_base_modules, module_state_sha256, save_head_artifact)


DEFAULTS = {"seed": 7, "learning_rate": 1e-3, "weight_decay": 1e-4,
            "batch_size": 128, "epochs": 50, "device": "cpu"}


def training_config(config=None):
    if config is not None and not isinstance(config, dict):
        raise ValueError("training config must be an object")
    if set(config or {}) - set(DEFAULTS):
        raise ValueError("unknown finish training config field")
    value = {**DEFAULTS, **(config or {})}
    for key, low, high in (("seed", 0, 2**32 - 1), ("batch_size", 1, 2**20), ("epochs", 1, 50)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError(f"invalid training {key}")
    for key in ("learning_rate", "weight_decay"):
        item = value[key]
        if type(item) not in (int, float) or not math.isfinite(item) or item < 0:
            raise ValueError(f"invalid training {key}")
        value[key] = float(item)
    if value["learning_rate"] == 0:
        raise ValueError("learning_rate must be positive")
    if not isinstance(value["device"], str) or re.fullmatch(r"cpu|cuda(?::[0-9]+)?", value["device"]) is None:
        raise ValueError("training device must be explicit cpu or cuda device")
    return value


def _features(value, name):
    tensor = value.detach().cpu() if isinstance(value, torch.Tensor) else torch.as_tensor(np.asarray(value))
    if (tensor.ndim != 2 or min(tensor.shape) < 1 or not tensor.is_floating_point()
            or not torch.isfinite(tensor).all().item()):
        raise ValueError(f"{name} must be a nonempty finite floating feature matrix")
    return tensor.to(torch.float32).clone()


def _labels(value, count, name):
    array = np.asarray(value)
    if (array.shape != (count,) or array.dtype.kind not in "biuf" or not np.isfinite(array).all()
            or not np.isin(array, [0, 1]).all()):
        raise ValueError(f"{name} must contain one binary label per feature")
    return torch.from_numpy(array.astype(np.float32, copy=True))


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def train_head(train_features, train_labels, val_features, val_labels, output, *,
               identities, config=None, base_modules=None):
    """Train only the declared head. Caller must supply already audited splits.

    ``train_from_cache`` is the public file entry and verifies provenance before
    invoking this tensor-level function. Test data is not an accepted argument.
    Each epoch logs ordinary validation BCE, and strict improvement selects the
    earliest minimum. Interruptions retain progress in the new output directory;
    resuming/overwriting it is deliberately unsupported.
    """
    config = training_config(config)
    identities = _identities(identities)
    x_train, x_val = _features(train_features, "training features"), _features(val_features, "validation features")
    if x_train.shape[1] != x_val.shape[1]:
        raise ValueError("training and validation feature dimensions differ")
    y_train, y_val = _labels(train_labels, len(x_train), "training labels"), _labels(val_labels, len(x_val), "validation labels")
    positives = int(y_train.sum().item())
    negatives = len(y_train) - positives
    if not positives or not negatives:
        raise ValueError("insufficient training data: both positive and negative labels are required")
    modules = {} if base_modules is None else base_modules
    freeze_base_modules(modules)
    base_before = module_state_sha256(modules) if modules else None
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"schema_version": "remaining-finish-training-v1", "status": "running", "config": config,
                "identities": identities, "pos_weight": negatives / positives,
                "class_counts": {"training_positive": positives, "training_negative": negatives,
                                 "validation_positive": int(y_val.sum().item()),
                                 "validation_negative": len(y_val) - int(y_val.sum().item())},
                "checkpoint_selection": "ordinary unweighted validation BCE; strict improvement, earlier epoch on tie",
                "base_parameter_sha256_before": base_before, "base_parameter_sha256_after": None,
                "base_modules_present": bool(modules), "base_modules_frozen": True,
                "input_shapes": {"training": list(x_train.shape), "validation": list(x_val.shape)},
                "epochs": [], "best_epoch": None, "best_validation_bce": None}
    _write(output / "training.json", progress)
    try:
        device = torch.device(config["device"])
        # Head initialization is isolated from the caller's CPU random stream.
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(config["seed"])
            head = FinishHead(x_train.shape[1]).to(device=device, dtype=torch.float32)
        optimizer = torch.optim.AdamW(head.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
        weighted_loss = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(progress["pos_weight"], device=device))
        validation_loss = nn.BCEWithLogitsLoss()
        generator = torch.Generator(device="cpu").manual_seed(config["seed"])
        best_state = None
        for epoch in range(1, config["epochs"] + 1):
            head.train()
            order = torch.randperm(len(x_train), generator=generator)
            loss_sum = 0.0
            for indices in order.split(config["batch_size"]):
                optimizer.zero_grad(set_to_none=True)
                logits = head(x_train[indices].to(device))
                loss = weighted_loss(logits, y_train[indices].to(device))
                if not torch.isfinite(loss).item():
                    raise ValueError("nonfinite head training loss")
                loss.backward()
                optimizer.step()
                loss_sum += float(loss.detach().cpu()) * len(indices)
            head.eval()
            with torch.inference_mode():
                val_logits = head(x_val.to(device))
                val_bce = float(validation_loss(val_logits, y_val.to(device)).cpu())
            if not math.isfinite(val_bce):
                raise ValueError("nonfinite validation BCE")
            if progress["best_validation_bce"] is None or val_bce < progress["best_validation_bce"]:
                progress.update(best_epoch=epoch, best_validation_bce=val_bce)
                best_state = {key: value.detach().cpu().clone() for key, value in head.state_dict().items()}
            progress["epochs"].append({"epoch": epoch, "training_weighted_bce": loss_sum / len(x_train),
                                        "validation_bce": val_bce})
            assert_frozen(modules)
            _write(output / "training.json", progress)
        base_after = module_state_sha256(modules) if modules else None
        if base_before != base_after:
            raise ValueError("frozen base parameter/buffer bytes changed during head training")
        progress.update(base_parameter_sha256_after=base_after, status="finished")
        head.load_state_dict(best_state, strict=True)
        head.eval()
        manifest = save_head_artifact(output / "head", head, identities=identities, training=progress)
        progress["head_artifact_sha256"] = manifest["artifact_sha256"]
        _write(output / "training.json", progress)
        return manifest
    except BaseException as error:
        progress.update(status="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "error",
                        error=f"{type(error).__name__}: {error}")
        _write(output / "training.json", progress)
        raise


def train_from_cache(cache_path, output, *, config=None):
    from .data import load_feature_cache
    cache = load_feature_cache(cache_path, allowed_splits=["train", "validation"])
    train = np.array([row["split"] == "train" for row in cache["rows"]], dtype=bool)
    validation = np.array([row["split"] == "validation" for row in cache["rows"]], dtype=bool)
    if not train.any() or not validation.any() or not (train | validation).all():
        raise ValueError("head training needs audited train and validation rows only")
    return train_head(cache["features"][train], cache["labels"][train],
                      cache["features"][validation], cache["labels"][validation], output,
                      identities=cache["identities"], config=config)
