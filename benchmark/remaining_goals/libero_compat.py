"""Explicit, fingerprinted LIBERO runtime compatibility without source edits.

Only the legacy utils module's collections binding is replaced. The standard
library module and the official, hash-verified LIBERO files remain unchanged.
The current region sampler already uses collections.abc.Iterable; the proxy
also keeps direct users of the legacy utils sampler compatible with Python 3.10.
"""

from __future__ import annotations

import collections
import collections.abc
import hashlib
import importlib
import json
from pathlib import Path
import platform


RULES = (
    "libero-utils-local-collections-iterable-proxy-v1",
    "native-reset-randomization-only-bounded-retries-v1",
    "windows-private-macro-and-version-matched-dll-record-v1",
    "post-step-synchronized-observations-forward-force-v1",
    "forward-free-ball-unit-quaternion-roundoff-16eps-restore-bits-v1",
    "panda-gripper-qpos-inverse-position-servo-clipped-command-and-ctrl-v1",
    "hard-reset-rebuild-bddl-property-samplers-without-history-accumulation-v1",
)
WINDOWS_RECORD = Path(__file__).resolve().parents[2] / ".runtime" / "remaining_libero" / "windows_compat.json"


class _CollectionsProxy:
    def __getattr__(self, name):
        if name == "Iterable":
            return collections.abc.Iterable
        return getattr(collections, name)


def apply_libero_compat():
    """Apply an idempotent module-local shim before constructing a scene."""
    module = importlib.import_module("libero.libero.envs.utils")
    current = getattr(module, "collections", None)
    if isinstance(current, _CollectionsProxy):
        return
    if current is not collections:
        raise RuntimeError("unexpected LIBERO utils.collections binding; refusing to hide a foreign patch")
    module.collections = _CollectionsProxy()


def compatibility_identity():
    """Include rule names and implementation bytes in the environment lock."""
    result = {"protocol": "remaining-libero-runtime-compat-v1", "rules": list(RULES),
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "bridge_source_sha256": hashlib.sha256(Path(__file__).with_name("libero_env.py").read_bytes()).hexdigest(),
              "platform": platform.system()}
    if result["platform"] == "Windows":
        result["windows_preparation"] = _windows_identity(WINDOWS_RECORD)
    return result


def _windows_identity(path):
    if not path.is_file():
        return {"status": "unprepared"}
    raw = path.read_bytes()
    record = json.loads(raw)
    if (record.get("schema_version") != "remaining-libero-windows-compat-v1"
            or record.get("platform") != "Windows"
            or record.get("configuration", {}).get("MUJOCO_GPU_RENDERING") is not False
            or record.get("configuration", {}).get("FILE_LOGGING_LEVEL", "absent") is not None):
        raise RuntimeError("invalid Windows runtime compatibility record")
    venv = (path.parent / "venv").resolve()
    hashes = {}
    for field in ("source_dll", "target_dll", "macro_file"):
        item = record.get(field, {})
        artifact = Path(item.get("path", "")).resolve()
        if not artifact.is_relative_to(venv) or not artifact.is_file():
            raise RuntimeError(f"Windows compatibility {field} must be inside the workspace venv")
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != item.get("sha256"):
            raise RuntimeError(f"Windows compatibility {field} hash mismatch")
        hashes[field] = actual
    if hashes["source_dll"] != hashes["target_dll"]:
        raise RuntimeError("Windows MuJoCo DLL source and installed copy differ")
    return {"status": "prepared", "record_sha256": hashlib.sha256(raw).hexdigest(),
            "verified_file_sha256": hashes, "configuration": record["configuration"],
            "package_versions": record.get("package_versions")}


def _randomization_error_type():
    from robosuite.utils.errors import RandomizationError
    return RandomizationError


def _property_sampler_types():
    from libero.libero.envs.regions.object_property_sampler import OpenCloseSampler, TurnOnOffSampler
    return OpenCloseSampler, TurnOnOffSampler


def _clear_regenerated_property_samplers(native):
    """Discard only verified BDDL-derived samplers before model regeneration.

    Upstream _load_model rebuilds placements but appends property samplers to a
    list initialized only in __init__. Repeated hard resets otherwise consume
    progressively more random draws, changing fixed fixture model positions
    even with the same seed. Regenerate one sampler per official init predicate,
    using the upstream loader; never edit a model or relax its XML identity.
    Soft/deterministic resets do not regenerate the model and retain samplers.
    Foreign/custom sampler contracts fail before any list mutation.
    """
    if not getattr(native, "hard_reset", False) or getattr(native, "deterministic_reset", False):
        return
    samplers = getattr(native, "object_property_initializers", None)
    if type(samplers) is not list:
        raise RuntimeError("hard reset requires the official BDDL property sampler list")
    if samplers:
        classes = _property_sampler_types()
        init = native.parsed_problem.get("initial_state", [])
        ranges = {"open": "default_open_ranges", "close": "default_close_ranges",
                  "turnon": "default_turnon_ranges", "turnoff": "default_turnoff_ranges"}
        declared = {(item[0], item[1]) for item in init
                    if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] in ranges}
        for sampler in samplers:
            kind, name = getattr(sampler, "state_type", None), getattr(sampler, "name", None)
            try:
                expected_type = classes[0] if kind in ("open", "close") else classes[1]
                obj = native.get_object(name)
                expected_range = obj.object_properties["articulation"][ranges[kind]]
                valid = (type(sampler) is expected_type and (kind, name) in declared
                         and not sampler.mujoco_objects
                         and tuple(sampler.joint_ranges) == tuple(expected_range))
            except (AttributeError, KeyError, TypeError):
                valid = False
            if not valid:
                raise RuntimeError("cannot regenerate unknown or modified BDDL property sampler")
    native.object_property_initializers = []


def reset_scene(env, *, max_attempts=50):
    """Reset a native LIBERO task with a bounded, explicit retry policy.

    Accept a ControlEnv with ``env.env`` or a native task exposing
    ``parsed_problem`` and ``reset``. Never call the upstream ControlEnv.reset:
    its finally/continue loop suppresses unrelated exceptions indefinitely.
    Only RandomizationError is retried; every other exception propagates.
    Before each hard-reset attempt, verified generated property samplers are
    cleared for the official loader to rebuild, preventing RNG-history drift.
    Test doubles must expose this same native interface, or patch this helper
    explicitly. There is deliberately no fallback to an arbitrary wrapper.
    """
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    native = env if hasattr(env, "parsed_problem") else getattr(env, "env", None)
    if native is None or not hasattr(native, "parsed_problem") or not callable(getattr(native, "reset", None)):
        raise TypeError("reset_scene requires a native LIBERO task or ControlEnv.env with parsed_problem/reset")
    randomization_error = _randomization_error_type()
    last_error = None
    for _ in range(max_attempts):
        try:
            _clear_regenerated_property_samplers(native)
            return native.reset()
        except randomization_error as exc:
            last_error = exc
    raise RuntimeError(f"LIBERO scene reset failed after {max_attempts} RandomizationError attempts") from last_error
