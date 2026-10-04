"""Manifest integrity/provenance tests; no LIBERO, simulator or model needed."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.remaining_goals.schema import (  # noqa: E402
    SCHEMA_VERSION,
    load_manifest,
    manifest_hash,
    validate_manifest,
    verify_state_file,
    write_manifest,
)


def make_manifest(n_goals=2, *, source="scene-0", split="test", pose="home"):
    goals = [
        {"id": f"g{i}", "language": f"put item {i} in tray", "predicates": [["in", f"item_{i}", "tray"]]}
        for i in range(n_goals)
    ]
    episodes = []
    for mask in itertools.product((False, True), repeat=n_goals):
        label = "".join(str(int(bit)) for bit in mask)
        episodes.append({
            "episode_id": f"{source}-{pose}-{label}", "task_id": "sort-two",
            "suite": "toy", "libero_task_id": 0, "task_name": "sort",
            "instruction": "put every item in the tray", "goal_specs": copy.deepcopy(goals),
            "initial_mask": list(mask), "state_path": f"states/{source}-{pose}-{label}.npy",
            "state_sha256": "0" * 64, "source_id": source, "split": split,
            "initial_state_index": 0, "seed": 7, "pose_id": pose,
            "horizon": 12, "retention_steps": 4,
            "construction": {"method": "toy-fixture", "legal": True, "reviewed_by": "test-author"},
        })
    return {"schema_version": SCHEMA_VERSION, "environment": {"name": "toy", "fingerprint": "toy-v1"}, "episodes": episodes}


def save_states(manifest, directory):
    for episode in manifest["episodes"]:
        path = directory / episode["state_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, np.array(episode["initial_mask"], dtype=float), allow_pickle=False)
        episode["state_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("n_goals", [2, 3])
def test_roundtrip_complete_manifest_and_state_files(tmp_path, n_goals):
    manifest = make_manifest(n_goals)
    save_states(manifest, tmp_path)
    before = copy.deepcopy(manifest)
    destination = tmp_path / "manifest.json"
    write_manifest(manifest, destination)
    assert manifest == before
    loaded = load_manifest(destination)
    assert loaded["content_hash"] == manifest_hash(manifest)
    assert len(loaded["episodes"]) == 2 ** n_goals
    assert verify_state_file(loaded["episodes"][0], tmp_path).is_file()


def test_hash_includes_all_configuration_and_ignores_only_top_hash():
    manifest = make_manifest()
    manifest["extras"] = {"content_hash": "nested", "note": "中文"}
    baseline = manifest_hash(manifest)
    assert manifest_hash(dict(reversed(list(manifest.items())))) == baseline
    manifest["content_hash"] = "ignored"
    assert manifest_hash(manifest) == baseline
    for mutate in (
        lambda m: m["environment"].update(fingerprint="new"),
        lambda m: m["episodes"][0].update(horizon=99),
        lambda m: m["episodes"][0]["construction"].update(reviewed_by="other"),
        lambda m: m["extras"].update(content_hash="changed"),
        lambda m: m.update(created_at="future"),
    ):
        changed = copy.deepcopy(manifest)
        mutate(changed)
        assert manifest_hash(changed) != baseline


def test_stale_hash_is_rejected_and_write_refreshes_it(tmp_path):
    manifest = make_manifest()
    manifest["content_hash"] = manifest_hash(manifest)
    manifest["environment"]["fingerprint"] = "changed"
    with pytest.raises(ValueError, match="content_hash.*mismatch"):
        validate_manifest(manifest)
    destination = tmp_path / "manifest.json"
    write_manifest(manifest, destination)
    assert load_manifest(destination, check_files=False)["content_hash"] == manifest_hash(manifest)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), (1, 2), {1: "non-string key"}])
def test_hash_rejects_non_json_extension_values(invalid):
    manifest = make_manifest()
    manifest["extension"] = invalid
    with pytest.raises(ValueError):
        manifest_hash(manifest)


@pytest.mark.parametrize("field,value", [
    ("episode_id", ""), ("task_name", " "), ("seed", True),
    ("libero_task_id", -1), ("initial_state_index", False),
    ("horizon", 0), ("retention_steps", 0), ("split", "dev"),
    ("initial_mask", [0, 1]), ("initial_mask", [True]),
    ("state_sha256", "bad"), ("construction", {"method": "manual", "legal": 1, "reviewed_by": "reviewer"}),
    ("construction", {"method": "manual", "legal": False, "reviewed_by": "reviewer"}),
    ("construction", {"method": "manual", "legal": True}),
])
def test_episode_contract_rejects_invalid_values(field, value):
    manifest = make_manifest()
    manifest["episodes"][0][field] = value
    with pytest.raises(ValueError):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", ["source_id", "pose_id", "instruction", "goal_specs", "initial_state_index", "seed", "construction", "state_path"])
def test_required_fields(field):
    manifest = make_manifest()
    del manifest["episodes"][0][field]
    with pytest.raises(ValueError):
        validate_manifest(manifest)


@pytest.mark.parametrize("predicates", [[], [[]], ["in a tray"], [["or", "a", "b"]], [["NOT", "a"]], [["and", "a"]], [["in", ["nested"]]], [["in", ""]], [["(not a)"]]])
def test_only_flat_positive_atomic_conjunctions(predicates):
    manifest = make_manifest()
    manifest["episodes"][0]["goal_specs"][0]["predicates"] = predicates
    with pytest.raises(ValueError):
        validate_manifest(manifest)


def test_goal_ids_unique_and_goal_count_limited():
    for n_goals in (1, 4):
        with pytest.raises(ValueError, match="2 or 3"):
            validate_manifest(make_manifest(n_goals))
    manifest = make_manifest()
    manifest["episodes"][0]["goal_specs"][1]["id"] = "g0"
    with pytest.raises(ValueError, match="goal id"):
        validate_manifest(manifest)


def test_missing_masks_rejected_but_construction_can_check_partial_group():
    manifest = make_manifest()
    manifest["episodes"].pop()
    with pytest.raises(ValueError, match="complete masks"):
        validate_manifest(manifest)
    validate_manifest(manifest, require_complete_masks=False)


def test_duplicate_mask_rejected_even_when_completeness_disabled():
    manifest = make_manifest()
    duplicate = copy.deepcopy(manifest["episodes"][0])
    duplicate["episode_id"] = "extra-run"
    manifest["episodes"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate mask"):
        validate_manifest(manifest, require_complete_masks=False)


def test_empty_manifest_and_duplicate_episode_ids_rejected():
    manifest = make_manifest()
    manifest["episodes"][1]["episode_id"] = manifest["episodes"][0]["episode_id"]
    with pytest.raises(ValueError, match="episode_id"):
        validate_manifest(manifest)
    manifest["episodes"] = []
    with pytest.raises(ValueError, match="non-empty list"):
        validate_manifest(manifest)


@pytest.mark.parametrize("field,value", [("horizon", 13), ("retention_steps", 5), ("initial_state_index", 1), ("split", "val")])
def test_group_configuration_must_match(field, value):
    manifest = make_manifest()
    manifest["episodes"][1][field] = value
    with pytest.raises(ValueError, match="paired group"):
        validate_manifest(manifest)


def test_task_identity_stable_across_source_groups():
    manifest = make_manifest()
    other = make_manifest(source="scene-1")
    for episode in other["episodes"]:
        episode["instruction"] = "different task semantics"
    manifest["episodes"] += other["episodes"]
    with pytest.raises(ValueError, match="task definition"):
        validate_manifest(manifest)


def test_native_task_cannot_gain_an_alias():
    manifest = make_manifest()
    other = make_manifest(source="scene-1")
    for episode in other["episodes"]:
        episode["task_id"] = "alias"
    manifest["episodes"] += other["episodes"]
    with pytest.raises(ValueError, match="multiple task_id aliases"):
        validate_manifest(manifest)


@pytest.mark.parametrize("relation", ["source", "donor", "donor-to-source"])
def test_provenance_cannot_cross_splits(relation):
    manifest = make_manifest(source="scene-0", split="train")
    other = make_manifest(source="scene-1", split="test", pose="other")
    for episode in other["episodes"]:
        if relation == "source":
            episode["source_id"] = "scene-0"
        else:
            episode["donor_source_ids"] = ["shared-donor" if relation == "donor" else "scene-0"]
    if relation == "donor":
        for episode in manifest["episodes"]:
            episode["donor_source_ids"] = ["shared-donor"]
    manifest["episodes"] += other["episodes"]
    with pytest.raises(ValueError, match="shared across splits"):
        validate_manifest(manifest)


def test_different_sources_can_use_different_splits_and_same_split_donors():
    manifest = make_manifest(source="scene-0", split="train")
    manifest["episodes"][0]["donor_source_ids"] = ["train-donor"]
    manifest["episodes"] += make_manifest(source="scene-1", split="test")["episodes"]
    validate_manifest(manifest)


@pytest.mark.parametrize("raw_path", ["../escape.npy", "inside/../../escape.npy", ".. /escape.npy", "folder./state.npy", "/tmp/escape.npy", "C:\\escape.npy", "C:escape.npy", "\\\\host\\share\\escape.npy", "\\escape.npy", "state.npy:stream", "state.npz"])
def test_paths_are_portably_relative_and_contained(raw_path):
    manifest = make_manifest()
    manifest["episodes"][0]["state_path"] = raw_path
    with pytest.raises(ValueError, match="state_path"):
        validate_manifest(manifest)


def test_resolved_symlink_cannot_escape(tmp_path):
    root = tmp_path / "manifest-dir"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")
    manifest = make_manifest()
    manifest["episodes"][0]["state_path"] = "link/escape.npy"
    with pytest.raises(ValueError, match="escapes"):
        validate_manifest(manifest, base_dir=root)


@pytest.mark.parametrize("state", [np.array([float("nan")]), np.array([float("inf")]), np.zeros((2, 2)), np.array([]), np.array(["text"]), np.array([1 + 2j]), np.array([object()], dtype=object)])
def test_invalid_numpy_states_rejected(tmp_path, state):
    path = tmp_path / "state.npy"
    np.save(path, state)
    episode = {"state_path": "state.npy", "state_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(ValueError):
        verify_state_file(episode, tmp_path)


def test_archive_disguised_as_npy_rejected(tmp_path):
    path = tmp_path / "state.npy"
    with path.open("wb") as stream:
        np.savez(stream, state=np.ones(2))
    episode = {"state_path": "state.npy", "state_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="not an archive"):
        verify_state_file(episode, tmp_path)


def test_state_tampering_is_detected_by_default_loader(tmp_path):
    manifest = make_manifest()
    save_states(manifest, tmp_path)
    destination = tmp_path / "manifest.json"
    write_manifest(manifest, destination)
    np.save(tmp_path / manifest["episodes"][0]["state_path"], np.ones(2))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_manifest(destination)


def test_missing_state_file_and_missing_base_directory_rejected(tmp_path):
    manifest = make_manifest()
    with pytest.raises(ValueError, match="base_dir"):
        validate_manifest(manifest, check_files=True)
    with pytest.raises(ValueError, match="cannot read"):
        validate_manifest(manifest, base_dir=tmp_path, check_files=True)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"episodes": [], "episodes": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_manifest(path, check_files=False)


def test_written_manifest_contains_actual_hash(tmp_path):
    path = tmp_path / "nested" / "manifest.json"
    write_manifest(make_manifest(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content_hash"] == manifest_hash(data)
