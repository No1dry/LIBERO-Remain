"""Synthetic HDF5 and fake provider only: no LIBERO restoration or VLA calls."""
import copy
import hashlib
import json

import numpy as np
import pytest

h5py = pytest.importorskip("h5py", reason="optional finish-data dependency for synthetic HDF5 audit tests")

from benchmark.remaining_goals.finish import data


def observation(value=0):
    return {"agentview_image": np.full((2, 2, 3), value, np.uint8),
            "robot0_eye_in_hand_image": np.full((2, 2, 3), value, np.uint8),
            "robot0_eef_pos": np.zeros(3), "robot0_eef_quat": np.array([0., 0., 0., 1.]),
            "robot0_gripper_qpos": np.zeros(2)}


def truth(complete=True, released=True):
    return {"goals": [complete, complete], "released": released,
            "release_evidence": {"method": "fake-contact-and-geometry", "test_only": True}}


def hold(state, complete=True):
    return {"source_state_sha256": data.state_sha256(state), "hold_contract": {"test_only": True},
            "trace": [{"step": i, **truth(complete)} for i in range(5)]}


class Provider:
    def __init__(self):
        self.restore_calls, self.hold_calls, self.closed = 0, 0, False

    def restore_demonstration(self, state, model_xml=None):
        self.restore_calls += 1
        return {"observation": observation(int(state[0])), **truth(bool(state[1]))}

    def capture_hold_label(self, state, steps, model_xml=None):
        self.hold_calls += 1
        assert steps == 4
        return hold(state)

    def close(self):
        self.closed = True


@pytest.fixture
def assets(tmp_path):
    initials = np.array([[i, 0] for i in range(50)], dtype=np.float64)
    np.save(tmp_path / "init.npy", initials)
    with h5py.File(tmp_path / "demo.hdf5", "w") as file:
        group = file.create_group("data")
        for index in range(50):
            # Names intentionally do not encode the source index.
            demo = group.create_group(f"demo_{49-index:02d}")
            demo.create_dataset("states", data=np.array([initials[index], [index, 1]], dtype=np.float64))
            demo.attrs["model_file"] = "<mujoco/>"
    (tmp_path / "task.bddl").write_text("fake CPU fixture", encoding="utf-8")
    return {"hdf5_path": str(tmp_path / "demo.hdf5"), "init_states_path": str(tmp_path / "init.npy"),
            "bddl_path": str(tmp_path / "task.bddl"), "original_instruction": "original task", "state_stride": 8}


@pytest.fixture
def audited(assets, tmp_path):
    provider = Provider()
    path = tmp_path / "audit"
    report = data.audit_demonstrations(assets, provider_factory=lambda config: provider, out=path)
    assert report["status"] == "ready_for_feature_export", report["issues"]
    return path, report, provider


def test_audit_reads_real_hdf5_layout_and_maps_by_state_not_demo_number(audited):
    path, report, provider = audited
    assert {t["trajectory_id"]: t["source_index"] for t in report["trajectories"]}["demo_00"] == 49
    assert len(report["rows"]) == 70
    assert provider.restore_calls == 70 and provider.hold_calls == 35 and provider.closed
    assert {r["source_index"] for r in report["rows"]} == set(range(5, 40))
    assert data.validate_audit(report, base_dir=path) == report
    assert all(r["label"] == r["saved_state_index"] for r in report["rows"])


def test_dry_plan_and_missing_assets_never_create_provider(tmp_path):
    config = {"hdf5_path": str(tmp_path / "missing.h5"), "init_states_path": "missing.npy",
              "bddl_path": "missing.bddl", "original_instruction": "unchanged"}
    assert data.audit_plan(config)["simulation_created"] is False
    result = data.audit_demonstrations(config, provider_factory=lambda _: pytest.fail("must not create env"), out=tmp_path / "out")
    assert result["status"] == "insufficient" and result["rows"] == []
    assert (tmp_path / "out" / "audit.json").is_file()


def test_bad_mapping_reports_insufficient_without_replacement_or_env(assets, tmp_path):
    assets["trajectory_source_map"] = {"demo_00": 0}
    result = data.audit_demonstrations(assets, provider_factory=lambda _: pytest.fail("must not create env"), out=tmp_path / "bad")
    assert result["status"] == "insufficient"
    assert any(a.get("exact_match_candidates") == [49] for a in result["alternatives"])


def test_unmapped_audit_retains_actual_state_hash_inventory_without_certifying_mapping(assets, tmp_path):
    with h5py.File(assets["hdf5_path"], "a") as file:
        file["data/demo_00/states"][0] = np.array([49., .25])
    out = tmp_path / "unmapped_inventory"
    report = data.audit_demonstrations(assets, out=out,
        provider_factory=lambda _: pytest.fail("unverified provenance must not initialize environment"))
    assert report["status"] == "insufficient" and report["rows"] == []
    inventory = report["source_inventory"]
    assert inventory["establishes_source_mapping"] is False
    assert len(inventory["official_initial_states"]) == len(inventory["demonstrations"]) == 50
    source = next(item for item in inventory["official_initial_states"] if item["source_index"] == 49)
    demo = next(item for item in inventory["demonstrations"] if item["trajectory_id"] == "demo_00")
    assert source["source_state_sha256"] == data.state_sha256([49., 0.])
    assert demo["trajectory_initial_state_sha256"] == data.state_sha256([49., .25])
    assert source["source_state_sha256"] != demo["trajectory_initial_state_sha256"]
    assert not any(item["trajectory_id"] == "demo_00" for item in report["trajectories"])
    assert data.read_json(out / "audit.json")["source_inventory"] == inventory


def test_collection_provenance_requires_bound_hashes_and_human_confirmation(assets):
    trajectories = data.read_demonstrations(assets["hdf5_path"])
    initials = data.read_initial_states(assets["init_states_path"])
    trajectories[0]["states"][0][1] = 0.25
    identity = data.state_sha256(initials[49])
    record = {"source_index": 49, "method": "collection_provenance", "hdf5_sha256": "a" * 64,
              "init_states_sha256": "b" * 64, "trajectory_id": "demo_00", "source_state_sha256": identity,
              "trajectory_initial_state_sha256": data.state_sha256(trajectories[0]["states"][0]),
              "manually_confirmed": True, "collection_record_source": "collection-log.json#run-1",
              "reviewer": "user", "confirmation_reason": "matching collection transaction"}
    config = {"trajectory_source_map": {"demo_00": record}}
    mappings, issues, _ = data._mapping(trajectories, initials, config, "a" * 64, "b" * 64)
    assert not issues and mappings[0]["method"] == "collection_provenance"
    record["manually_confirmed"] = 1
    assert data._mapping(trajectories, initials, config, "a" * 64, "b" * 64)[1]


@pytest.mark.parametrize("change", ["overlap", "bool", "unconfirmed", "move_remain"])
def test_invalid_group_split_rejected(change):
    split = copy.deepcopy(data.DEFAULT_SPLIT)
    confirmation = None
    if change == "overlap":
        split["train"].append(35)
    elif change == "bool":
        split["train"][0] = True
    elif change == "unconfirmed":
        split["train"] = [5]
    else:
        split["remain_test"] = [0, 1, 2, 3]
        confirmation = {"confirmed": True, "reviewer": "x", "reason": "bad"}
    with pytest.raises(ValueError):
        data.validate_split(split, alternative_confirmation=confirmation)


def test_cross_source_and_variant_leakage_rejected():
    rows = [{"row_id": "a", "source_index": 5, "split": "train", "trajectory_id": "same", "state_sha256": "a"},
            {"row_id": "b", "source_index": 35, "split": "validation", "trajectory_id": "same", "state_sha256": "b"}]
    with pytest.raises(ValueError, match="trajectory"):
        data.validate_group_rows(rows, data.DEFAULT_SPLIT)
    rows[1]["trajectory_id"] = "other"
    rows[1]["state_sha256"] = "a"
    with pytest.raises(ValueError, match="state"):
        data.validate_group_rows(rows, data.DEFAULT_SPLIT)
    rows = [dict(rows[0], edited_variant=True)]
    with pytest.raises(ValueError, match="edited"):
        data.validate_group_rows(rows, data.DEFAULT_SPLIT)


@pytest.mark.parametrize("current,expected", [(truth(False), 0), (truth(True, False), 0), (truth(True, None), None)])
def test_current_truth_label_not_last_frame(current, expected):
    current.update(is_last=True, t=999, T=999)
    assert data.derive_label(current)["label"] == expected


def test_positive_requires_current_state_and_passive_hold_not_demonstration_future():
    state = np.array([5, 1.])
    evidence = hold(state)
    assert data.derive_label(truth(), evidence, state_digest=data.state_sha256(state))["label"] == 1
    assert data.derive_label(truth(), None, state_digest=data.state_sha256(state))["label"] is None
    evidence["trace"][3]["goals"] = [False, True]
    assert data.derive_label(truth(), evidence, state_digest=data.state_sha256(state))["label"] == 0
    evidence = hold(state)
    evidence["source_state_sha256"] = "wrong"
    assert data.derive_label(truth(), evidence, state_digest=data.state_sha256(state))["label"] is None


@pytest.mark.parametrize("change", ["short", "duplicate", "unknown", "initial"])
def test_hold_missing_or_unknown_evidence_stays_unknown(change):
    state = np.array([1, 1.])
    evidence = hold(state)
    if change == "short":
        evidence["trace"].pop()
    elif change == "duplicate":
        evidence["trace"][2]["step"] = 1
    elif change == "unknown":
        evidence["trace"][2]["released"] = None
    else:
        evidence["trace"][0]["goals"] = [False, True]
    assert data.derive_label(truth(), evidence, state_digest=data.state_sha256(state))["label"] is None


def input_evidence():
    tensors = {"input_ids": np.array([[1, 2]], dtype=np.int64), "attention_mask": np.ones((1, 2), dtype=np.int64),
               "pixel_values": np.ones((1, 6, 2, 2), np.float32), "proprio": np.zeros((1, 8), np.float32)}
    return {"schema_version": "remaining-finish-input-v1", "tensors": tensors,
            "tensor_dtypes": {k: "numpy." + str(v.dtype) for k, v in tensors.items()},
            "crops": {"agentview": np.zeros((2, 2, 3), np.uint8), "wrist": np.zeros((2, 2, 3), np.uint8)}}


class FeaturePolicy:
    def __init__(self):
        self.calls = 0

    def predict(self, obs, instruction):
        assert set(obs).issubset(data.OBSERVATION_KEYS) and instruction == "original task"
        self.calls += 1
        return {"features": np.ones((1, 3), np.float32), "candidate_actions": np.zeros((8, 7)),
                "input_evidence": input_evidence()}


@pytest.fixture
def cache(audited, tmp_path):
    directory, audit, _ = audited
    policy = FeaturePolicy()
    output = tmp_path / "cache"
    manifest = data.export_features(directory, policy, output, base_identity={"checkpoint_sha256": "a" * 64})
    assert policy.calls == 70
    assert manifest["audit"]["audit_sha256"] == audit["audit_sha256"]
    return output, manifest


def rewrite_cache(path, manifest):
    manifest.pop("cache_sha256", None)
    manifest["cache_sha256"] = data.canonical_hash(manifest)
    (path / "cache.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_cache_roundtrip_has_only_legal_inputs_and_preserves_audit_identity(cache):
    directory, manifest = cache
    loaded = data.load_feature_cache(directory, allowed_splits=["train", "validation"])
    assert loaded["features"].shape == (70, 3)
    assert loaded["features"].dtype == np.float32
    assert loaded["labels"].tolist().count(1) == 35
    assert loaded["identities"]["data_identity"]["audit_sha256"] == manifest["audit"]["audit_sha256"]
    with pytest.raises(ValueError, match="base identity"):
        data.load_feature_cache(directory, expected_base_identity={"different": True})
    with pytest.raises(ValueError, match="allowed split"):
        data.load_feature_cache(directory, allowed_splits=["train"])


@pytest.mark.parametrize("change", ["label", "truth_label", "input", "dtype_label", "observation", "test_split", "nan"])
def test_cache_rejects_rehashed_but_inconsistent_evidence(cache, change):
    directory, manifest = cache
    if change == "label":
        manifest["rows"][0]["label"] = 1 - manifest["rows"][0]["label"]
    elif change == "truth_label":
        audit = manifest["audit"]
        audit["rows"][0]["label"] = 1 - audit["rows"][0]["label"]
        audit.pop("audit_sha256")
        audit["audit_sha256"] = data.canonical_hash(audit)
    elif change == "input":
        manifest["rows"][0]["input_sha256"] = "f" * 64
    elif change == "dtype_label":
        manifest["rows"][0]["input_tensor_dtypes"]["pixel_values"] = "torch.bfloat16"
    elif change == "observation":
        manifest["rows"][0]["raw_observation_sha256"] = "f" * 64
    elif change == "test_split":
        manifest["rows"][0]["split"] = "normal_test"
    else:
        with np.load(directory / "features.npz", allow_pickle=False) as source:
            features, labels = source["features"], source["labels"]
        features[0, 0] = np.nan
        np.savez_compressed(directory / "features.npz", features=features, labels=labels)
        manifest["features_sha256"] = hashlib.sha256((directory / "features.npz").read_bytes()).hexdigest()
    rewrite_cache(directory, manifest)
    with pytest.raises(ValueError):
        data.load_feature_cache(directory)


def test_cache_rejects_changed_npz_and_forbidden_observation(cache):
    directory, _ = cache
    with (directory / "features.npz").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="hash"):
        data.load_feature_cache(directory)
    obs = observation()
    obs["source_index"] = np.array([35])
    with pytest.raises(ValueError, match="forbidden"):
        data._legal_observation(obs)


def test_exclusive_audit_output(assets, tmp_path):
    out = tmp_path / "exists"
    out.mkdir()
    with pytest.raises(FileExistsError):
        data.audit_demonstrations(assets, out=out)


def test_deterministic_alternative_never_moves_heldout_sources_into_training():
    available = [i for i in range(50) if i not in {35, 40}]
    proposal = data.deterministic_alternative_split(available)
    assert proposal["status"] == "proposal_requires_confirmation"
    split = proposal["proposed_split"]
    assert split["remain_test"] == list(range(5))
    assert 34 in split["normal_test"] and 33 in split["validation"]
    assert set(split["train"]).isdisjoint(range(35, 50))
    assert len(split["validation"]) == 5 and len(split["normal_test"]) == 10
    assert not proposal["automatically_applied"]
    assert data.deterministic_alternative_split([0, 1, 2, 3, 4, 5, 6])["status"] == "not_proposable"


def test_official_style_torch_numpy_init_pickle_uses_restricted_numeric_loader(tmp_path):
    torch = pytest.importorskip("torch")
    values = [np.array([index, 0., .5], dtype=np.float64) for index in range(3)]
    path = tmp_path / "official_style.pruned_init"
    torch.save(values, path)
    np.testing.assert_array_equal(data.read_initial_states(path), np.array(values))
    tensor_path = tmp_path / "tensor.pt"
    torch.save(torch.tensor(values[0]).repeat(2, 1), tensor_path)
    np.testing.assert_array_equal(data.read_initial_states(tensor_path), np.array([values[0], values[0]]))


def test_initial_state_pickle_rejects_non_numeric_code_globals(tmp_path):
    torch = pytest.importorskip("torch")
    class Forbidden:
        def __reduce__(self):
            return eval, ("40 + 2",)
    path = tmp_path / "forbidden.pt"
    torch.save(Forbidden(), path)
    with pytest.raises(Exception, match="forbidden initial-state pickle global"):
        data.read_initial_states(path)
