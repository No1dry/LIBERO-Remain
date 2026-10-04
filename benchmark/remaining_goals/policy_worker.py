"""Model interpreter entry point; invoked by SubprocessPolicy, not by users."""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import traceback

import numpy as np

from .policy_transport import read_frame, write_frame


def provenance(config, policy=None):
    repo = config.get("adapter_options", {}).get("repo_path")
    source = {"path": repo, "revision": None, "dirty": None}
    if repo and Path(repo).is_dir():
        def git(*args):
            return subprocess.check_output(["git", "-C", repo, *args], stderr=subprocess.DEVNULL,
                                           text=True, timeout=10).strip()
        try:
            source.update(revision=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain")))
        except (OSError, subprocess.SubprocessError):
            pass
    metadata = getattr(policy, "metadata", {}) if policy is not None else {}
    if not isinstance(metadata, dict):
        raise ValueError("policy.metadata must be a JSON object")
    def json_default(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f"unsupported policy metadata: {type(value).__name__}")
    metadata = json.loads(json.dumps(metadata, default=json_default, allow_nan=False))
    return {"python": sys.executable, "python_version": platform.python_version(),
            "packages": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
                                    if d.metadata.get("Name"))), "model_source": source,
            "checkpoint": config.get("adapter_options", {}).get("checkpoint"),
            "checkpoint_bytes_verified": False,
            "policy_metadata": metadata,
            "random_seed": config.get("execution", {}).get("random_seed", 0),
            "seed_scope": "Python/NumPy and already imported PyTorch reset to this seed before each episode; adapter-local RNGs follow policy_metadata; CUDA bit determinism is not claimed",
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}


def _seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    if "torch" in sys.modules:
        torch = sys.modules["torch"]
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)


def serve(input_stream, output_stream):
    policy = None
    try:
        request = read_frame(input_stream)
        if request.get("command") != "initialize":
            raise ValueError("worker must be initialized first")
        config = request["config"]
        seed = config.get("execution", {}).get("random_seed", 0)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("random_seed must be an integer in [0, 2**32)")
        _seed(seed)
        module, _, name = config["policy_factory"].partition(":")
        factory = getattr(importlib.import_module(module), name)
        _seed(seed)
        policy = factory(config)
        # Also seed lazy imports performed inside factory; no deterministic CUDA claim.
        _seed(seed)
        write_frame(output_stream, {"ok": True, "provenance": provenance(config, policy)})
        while True:
            request = read_frame(input_stream)
            command = request.get("command")
            if command == "close":
                break
            if command == "reset":
                _seed(seed)
                policy.reset()
                result = None
            elif command == "predict":
                result = policy.predict(request["observation"], request["instruction"])
            else:
                raise ValueError(f"unknown worker command: {command}")
            write_frame(output_stream, {"ok": True, "result": result})
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        try:
            write_frame(output_stream, {"ok": False, "error": f"{type(error).__name__}: {error}"})
        except (OSError, EOFError):
            pass
        return 1
    finally:
        if policy is not None and callable(getattr(policy, "close", None)):
            policy.close()
    return 0


def main():
    # Preserve a private protocol fd; even native libraries' stdout goes to stderr.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with protocol:
        return serve(sys.stdin.buffer, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
