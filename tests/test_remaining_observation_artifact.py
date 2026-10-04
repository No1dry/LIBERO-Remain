"""Lossless initial-observation evidence, with no simulator dependency."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from benchmark.remaining_goals.observation_artifact import (
    FORMAT, load_observation_artifact, save_observation_artifact,
)
from benchmark.remaining_goals.validation import compare_observations


def observation():
    return {"images": {"front": np.arange(48, dtype=np.uint8).reshape(4, 4, 3),
                       "wrist": np.zeros((2, 3, 3), dtype=np.uint8)},
            "proprio": np.array([0., -0., .125], dtype=np.float32),
            "joint_count": np.array(7, dtype=np.int16)}


def test_lossless_nested_typed_roundtrip_and_canonical_digest(tmp_path):
    original = observation()
    reference = save_observation_artifact(tmp_path, "observations/initial.npz", original)
    assert reference["format"] == FORMAT
    digest = compare_observations(original, original)["returned_sha256"]
    restored = load_observation_artifact(tmp_path, reference, expected_digest=digest)
    assert reference["observation_sha256"] == digest
    for name in ("front", "wrist"):
        assert restored["images"][name].dtype == original["images"][name].dtype
        assert restored["images"][name].tobytes() == original["images"][name].tobytes()
    assert restored["proprio"].dtype == np.float32
    assert restored["proprio"].tobytes() == original["proprio"].tobytes()
    assert restored["joint_count"].shape == () and restored["joint_count"].dtype == np.int16
    original["images"]["front"][:] = 255
    assert restored["images"]["front"][0, 0, 0] == 0
    assert hashlib.sha256((tmp_path / reference["path"]).read_bytes()).hexdigest() == reference["sha256"]
    with np.load(tmp_path / reference["path"], allow_pickle=False) as archive:
        assert archive["metadata_json"].dtype == np.uint8
        assert all(archive[key].dtype.kind != "O" for key in archive.files)


@pytest.mark.parametrize("relative", ["../escape.npz", "C:/escape.npz", "/absolute.npz", "bad.npy",
                                       "nested/../escape.npz", "folder./array.npz", "stream:array.npz"])
def test_artifact_paths_must_be_portably_contained(tmp_path, relative):
    with pytest.raises(ValueError, match="relative NPZ path"):
        save_observation_artifact(tmp_path, relative, observation())


def test_artifact_is_not_overwritten_or_accepted_after_byte_change(tmp_path):
    reference = save_observation_artifact(tmp_path, "initial.npz", observation())
    with pytest.raises(FileExistsError):
        save_observation_artifact(tmp_path, "initial.npz", observation())
    with (tmp_path / reference["path"]).open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="file hash mismatch"):
        load_observation_artifact(tmp_path, reference)


@pytest.mark.parametrize("binding", ["manifest", "construction"])
def test_observation_digest_is_bound_to_manifest_and_selected_audit(tmp_path, binding):
    reference = save_observation_artifact(tmp_path, "initial.npz", observation())
    expected = reference["observation_sha256"]
    if binding == "manifest":
        reference["observation_sha256"] = "f" * 64
    else:
        expected = "f" * 64
    with pytest.raises(ValueError, match="digest differs"):
        load_observation_artifact(tmp_path, reference, expected_digest=expected)


def rewrite_archive(tmp_path, reference, change):
    path = tmp_path / reference["path"]
    with np.load(path, allow_pickle=False) as source:
        arrays = {key: source[key].copy() for key in source.files}
    change(arrays)
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    reference["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", ["shape", "dtype", "extra", "object", "duplicate_tree", "nan"])
def test_rehashed_malformed_archive_is_rejected_without_pickle(tmp_path, change):
    reference = save_observation_artifact(tmp_path, "initial.npz", observation())

    def mutate(arrays):
        metadata = json.loads(arrays["metadata_json"].tobytes())
        if change == "shape":
            metadata["arrays"][0]["shape"] = [999]
        elif change == "dtype":
            metadata["arrays"][0]["dtype"] = "<f8"
        elif change == "extra":
            arrays["unreferenced"] = np.zeros(1)
        elif change == "object":
            arrays["array_000"] = np.array([object()], dtype=object)
        elif change == "duplicate_tree":
            metadata["tree"]["dict"].append(deepcopy(metadata["tree"]["dict"][0]))
        else:
            arrays["array_000"] = np.array([float("nan")])
        arrays["metadata_json"] = np.frombuffer(json.dumps(metadata).encode(), dtype=np.uint8)

    rewrite_archive(tmp_path, reference, mutate)
    with pytest.raises(ValueError):
        load_observation_artifact(tmp_path, reference)


@pytest.mark.parametrize("value", [np.array([np.nan]), np.array([np.inf]), np.array([], dtype=float),
                                  np.array([object()], dtype=object), np.array([True]), {}])
def test_nonfinite_non_numeric_or_empty_observations_are_not_saved(tmp_path, value):
    with pytest.raises(ValueError):
        save_observation_artifact(tmp_path, "bad.npz", {"proprio": value})
    assert not (tmp_path / "bad.npz").exists()
