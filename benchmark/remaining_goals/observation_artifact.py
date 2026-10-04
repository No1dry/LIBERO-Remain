"""Lossless, hash-bound initial observations for independent replay auditing.

Only numeric arrays and dictionaries are supported. NPZ contains the original
array dtypes/values plus a uint8-encoded JSON structure; pickle is never used.
Artifacts are evaluator evidence, never substituted for live policy images.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import zipfile

import numpy as np

from .validation import compare_observations

FORMAT = "remaining-observation-npz-v1"
MAX_BYTES = 128 * 1024 * 1024
MAX_ARRAYS = 64


def _path(base_dir, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("initial observation artifact needs a relative NPZ path")
    path = PurePosixPath(relative.replace("\\", "/"))
    windows = PureWindowsPath(relative)
    if (windows.drive or windows.root or path.is_absolute() or ".." in path.parts
            or path.suffix != ".npz" or any(":" in p or p.endswith((" ", ".")) for p in path.parts)):
        raise ValueError("initial observation artifact path must be a contained relative NPZ path")
    base = Path(base_dir).resolve()
    target = (base / Path(*path.parts)).resolve()
    if not target.is_relative_to(base):
        raise ValueError("initial observation artifact path escaped the pack")
    return target


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _digest(observation):
    check = compare_observations(observation, observation, atol=0)
    if not check["matches"]:
        raise ValueError("initial observation artifact contains invalid observations")
    return check["returned_sha256"]


def _numeric(value):
    array = np.asarray(value)
    if (not array.size or array.dtype.kind not in "fiu" or not np.isfinite(array).all()
            or array.dtype.fields is not None or array.nbytes > MAX_BYTES):
        raise ValueError("initial observation artifact arrays must be finite, real and bounded")
    return array.copy(order="C")


def save_observation_artifact(base_dir, relative_path, observation) -> dict:
    """Save the exact captured observation and return its manifest reference."""
    arrays, descriptors = {}, []

    def encode(value, depth=0):
        if depth > 16:
            raise ValueError("initial observation structure is too deep")
        if isinstance(value, dict):
            if not value or any(not isinstance(k, str) or not k for k in value):
                raise ValueError("initial observation dictionaries need nonempty string keys")
            return {"dict": [[key, encode(value[key], depth + 1)] for key in sorted(value)]}
        if len(arrays) >= MAX_ARRAYS:
            raise ValueError("too many initial observation arrays")
        array = _numeric(value)
        key = f"array_{len(arrays):03d}"
        arrays[key] = array
        descriptors.append({"key": key, "dtype": array.dtype.str, "shape": list(array.shape)})
        return {"array": key}

    if not isinstance(observation, dict):
        raise ValueError("initial observation must be a dictionary")
    tree = encode(observation)
    if sum(a.nbytes for a in arrays.values()) > MAX_BYTES:
        raise ValueError("initial observation artifact exceeds size limit")
    digest = _digest(observation)
    metadata = {"format": FORMAT, "tree": tree, "arrays": descriptors, "observation_sha256": digest}
    arrays["metadata_json"] = np.frombuffer(json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                                       allow_nan=False).encode("utf-8"), dtype=np.uint8)
    target = _path(base_dir, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a prior captured observation or historical evidence.
    with target.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    return {"format": FORMAT, "path": str(relative_path).replace("\\", "/"),
            "sha256": _hash(target.read_bytes()), "observation_sha256": digest}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON metadata key")
        result[key] = value
    return result


def load_observation_artifact(base_dir, reference, *, expected_digest=None) -> dict:
    """Validate contained path, NPZ bytes, typed structure and observation digest.

    expected_digest binds the artifact to the construction audit's step-zero
    returned observation. Decode the same bytes that were hashed (no TOCTOU).
    """
    if not isinstance(reference, dict) or reference.get("format") != FORMAT:
        raise ValueError("missing/unsupported initial observation artifact format")
    for key in ("sha256", "observation_sha256"):
        value = reference.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"initial observation artifact needs {key}")
    path = _path(base_dir, reference.get("path"))
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("initial observation artifact exceeds size limit")
    raw = path.read_bytes()
    if _hash(raw) != reference["sha256"]:
        raise ValueError("initial observation artifact file hash mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if (len(members) > MAX_ARRAYS + 1 or len({m.filename for m in members}) != len(members)
                    or sum(m.file_size for m in members) > MAX_BYTES):
                raise ValueError("invalid or oversized initial observation archive")
        with np.load(io.BytesIO(raw), allow_pickle=False) as packed:
            metadata_array = packed["metadata_json"]
            if metadata_array.dtype != np.uint8 or metadata_array.ndim != 1 or metadata_array.size > 1024 * 1024:
                raise ValueError("invalid initial observation JSON metadata")
            metadata = json.loads(metadata_array.tobytes().decode("utf-8"), object_pairs_hook=_unique)
            if metadata.get("format") != FORMAT:
                raise ValueError("initial observation metadata format differs")
            descriptors = metadata["arrays"]
            if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= MAX_ARRAYS:
                raise ValueError("invalid initial observation array table")
            arrays = {}
            for index, item in enumerate(descriptors):
                key = f"array_{index:03d}"
                if not isinstance(item, dict) or item.get("key") != key:
                    raise ValueError("invalid initial observation array key/order")
                array = _numeric(packed[key])
                if item.get("dtype") != array.dtype.str or item.get("shape") != list(array.shape):
                    raise ValueError("initial observation dtype/shape metadata mismatch")
                arrays[key] = array
            if set(packed.files) != {"metadata_json", *arrays}:
                raise ValueError("unexpected initial observation archive entries")
        used = set()

        def decode(node, depth=0):
            if depth > 16 or not isinstance(node, dict):
                raise ValueError("invalid initial observation structure")
            if set(node) == {"array"}:
                key = node["array"]
                if not isinstance(key, str) or key not in arrays or key in used:
                    raise ValueError("invalid/reused initial observation array reference")
                used.add(key)
                return arrays[key]
            if set(node) != {"dict"} or not isinstance(node["dict"], list) or not node["dict"]:
                raise ValueError("invalid initial observation dictionary structure")
            result = {}
            for pair in node["dict"]:
                if (not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str)
                        or not pair[0] or pair[0] in result):
                    raise ValueError("invalid/duplicate initial observation channel")
                result[pair[0]] = decode(pair[1], depth + 1)
            return result

        observation = decode(metadata["tree"])
        if not isinstance(observation, dict) or used != set(arrays):
            raise ValueError("initial observation structure leaves unused arrays")
        digest = _digest(observation)
        if (digest != metadata.get("observation_sha256") or digest != reference["observation_sha256"]
                or (expected_digest is not None and digest != expected_digest)):
            raise ValueError("initial observation digest differs from manifest/construction audit")
        return observation
    except (KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as error:
        raise ValueError(f"invalid initial observation artifact: {error}") from error
