"""Synthetic two-domain head artifacts/training selection; no real VLA or data."""
from copy import deepcopy
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="tiny FINISH head CPU tests need optional torch")
pytest.importorskip("h5py", reason="synthetic FINISH HDF fixtures require optional h5py")
from benchmark.remaining_goals.finish import data, model, training
from benchmark.remaining_goals.finish.data_registry import source_identity
from tests.finish_domain_helpers import make_audit
from tests.test_remaining_finish_domain_consumers import FeatureWorker, BASE


@pytest.fixture(autouse=True)
def one_thread():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.fixture
def domain_identities(tmp_path):
    _, audit, _ = make_audit(tmp_path / "data")
    return data._identities(audit, BASE)


def rewrite_head(path, manifest):
    manifest["identity_sha256"] = {key: data.canonical_hash(value) for key, value in manifest["identities"].items()}
    manifest["artifact_sha256"] = data.canonical_hash({key: value for key, value in manifest.items() if key != "artifact_sha256"})
    (path / "head.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_v2_head_roundtrip_binds_both_domains_without_consuming_rng(tmp_path, domain_identities):
    head = model.FinishHead(3)
    out = tmp_path / "head"
    manifest = model.save_head_artifact(out, head, identities=domain_identities, training={"synthetic": True})
    before = torch.get_rng_state().clone()
    loaded, restored = model.load_head_artifact(out, expected_source_identity=domain_identities["split_identity"])
    assert torch.equal(before, torch.get_rng_state())
    assert restored == manifest and manifest["schema_version"] == model.DOMAIN_HEAD_SCHEMA
    assert restored["identities"]["split_identity"]["ancestry_independence"] == "unproven"
    for key, value in head.state_dict().items():
        assert torch.equal(value, loaded.state_dict()[key])
    with pytest.raises(ValueError, match="source-domain"):
        model.load_head_artifact(out, expected_source_identity={"another": True})


@pytest.mark.parametrize("change", ["downgrade", "strip_source_version", "profile_hash", "registry_hash",
                                   "asset", "group", "label", "legacy_identity"])
def test_v2_head_rejects_rehashed_cross_identity_or_version_mix(tmp_path, domain_identities, change):
    out = tmp_path / "head"
    manifest = model.save_head_artifact(out, model.FinishHead(3), identities=domain_identities, training={"synthetic": True})
    identity = manifest["identities"]
    if change == "downgrade":
        manifest["schema_version"] = model.HEAD_SCHEMA
    elif change == "strip_source_version":
        identity["split_identity"].pop("schema_version")
    elif change == "profile_hash":
        identity["data_identity"]["profile_sha256"] = "f" * 64
    elif change == "registry_hash":
        identity["data_identity"]["registry_sha256"] = "f" * 64
    elif change == "asset":
        identity["data_identity"]["assets"]["hdf5_path"]["sha256"] = "f" * 64
    elif change == "group":
        identity["split_identity"]["groups"]["head_demonstration"]["head_validation"][0] = "init:" + "f" * 64 + ":35"
    elif change == "label":
        identity["label_contract"]["confirmation_steps"] = 1
    else:
        identity["split_identity"] = {"split": deepcopy(data.DEFAULT_SPLIT), "sha256": data.canonical_hash(data.DEFAULT_SPLIT)}
    rewrite_head(out, manifest)
    with pytest.raises(ValueError):
        model.load_head_artifact(out)


def test_legacy_identity_cannot_be_relabelled_as_v2_head(tmp_path):
    identity = {key: {"synthetic": True} for key in model.IDENTITY_FIELDS}
    out = tmp_path / "head"
    manifest = model.save_head_artifact(out, model.FinishHead(3), identities=identity, training={"synthetic": True})
    manifest["schema_version"] = model.DOMAIN_HEAD_SCHEMA
    rewrite_head(out, manifest)
    with pytest.raises(ValueError, match="versions"):
        model.load_head_artifact(out)


def test_train_from_v2_cache_selects_only_head_train_and_head_validation(tmp_path, monkeypatch):
    directory, audit, _ = make_audit(tmp_path / "dataset")
    cache_path = tmp_path / "cache"
    data.export_features(directory, FeatureWorker(), cache_path, base_identity=BASE)
    captured = {}
    def fake_train(x, y, val_x, val_y, output, **kwargs):
        captured.update(x=x, y=y, val_x=val_x, val_y=val_y, **kwargs)
        return {"synthetic_selection_only": True}
    monkeypatch.setattr(training, "train_head", fake_train)
    result = training.train_from_cache(cache_path, tmp_path / "not-created")
    assert result["synthetic_selection_only"]
    assert captured["x"].shape == (60, 3) and captured["val_x"].shape == (10, 3)
    assert set(captured["x"][:, 0]) == set(range(1005, 1035))
    assert set(captured["val_x"][:, 0]) == set(range(1035, 1040))
    assert captured["identities"]["split_identity"] == source_identity(audit["registry"])
    manifest = data.read_json(cache_path / "cache.json")
    assert captured["feature_provenance"]["kind"] == "validated-feature-cache"
    assert captured["feature_provenance"]["cache_sha256"] == manifest["cache_sha256"]
    assert captured["feature_provenance"]["features_sha256"] == manifest["features_sha256"]
    assert captured["feature_provenance"]["input_rows_sha256"] == data.canonical_hash(manifest["rows"])
    assert not (tmp_path / "not-created").exists()


def test_v2_training_saves_v2_head_and_keeps_train_only_weight_and_validation_bce(tmp_path, domain_identities):
    features = np.arange(24, dtype=np.float32).reshape(8, 3)
    result = training.train_head(features, [0, 0, 0, 0, 0, 0, 1, 1], features[:4], [0, 1, 1, 1],
        tmp_path / "synthetic_train", identities=domain_identities, config={"epochs": 2, "batch_size": 4},
        feature_provenance={"kind": "synthetic-test-only", "test_only": True})
    assert result["schema_version"] == model.DOMAIN_HEAD_SCHEMA
    assert result["training"]["schema_version"] == "remaining-finish-training-v2"
    assert result["training"]["pos_weight"] == 3.0
    assert result["training"]["feature_provenance"] == {"kind": "synthetic-test-only", "test_only": True}
    selected = min(result["training"]["epochs"], key=lambda row: row["validation_bce"])
    assert selected["epoch"] == result["training"]["best_epoch"]
    head, _ = model.load_head_artifact(tmp_path / "synthetic_train/head")
    with torch.inference_mode():
        expected = torch.nn.functional.binary_cross_entropy_with_logits(head(torch.tensor(features[:4])),
                                                                         torch.tensor([0., 1., 1., 1.])).item()
    assert result["training"]["best_validation_bce"] == pytest.approx(expected)


@pytest.mark.parametrize("train_labels,val_labels", [([0, 0], [0, 1]), ([0, 1], [1, 1])])
def test_v2_class_shortage_does_not_borrow_or_start_training(tmp_path, domain_identities, train_labels, val_labels):
    with pytest.raises(ValueError, match="insufficient"):
        training.train_head(np.ones((2, 3), np.float32), train_labels, np.ones((2, 3), np.float32), val_labels,
                            tmp_path / "missing", identities=domain_identities, config={"epochs": 1})
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("provenance", [None, {"kind": "synthetic-test-only", "test_only": True, "cache_sha256": "a" * 64},
                                        {"kind": "validated-feature-cache"}])
def test_v2_training_cannot_omit_or_fake_feature_provenance(tmp_path, domain_identities, provenance):
    with pytest.raises(ValueError, match="provenance"):
        training.train_head(np.ones((2, 3), np.float32), [0, 1], np.ones((2, 3), np.float32), [0, 1],
            tmp_path / "missing", identities=domain_identities, config={"epochs": 1}, feature_provenance=provenance)
    assert not (tmp_path / "missing").exists()


def test_train_from_cache_persists_validated_feature_binding_inside_head(tmp_path):
    directory, _, _ = make_audit(tmp_path / "dataset")
    cache_path = tmp_path / "cache"
    cache = data.export_features(directory, FeatureWorker(), cache_path, base_identity=BASE)
    result = training.train_from_cache(cache_path, tmp_path / "synthetic_train", config={"epochs": 1})
    saved = data.read_json(tmp_path / "synthetic_train/head/head.json")
    provenance = saved["training"]["feature_provenance"]
    assert saved == result
    assert provenance["kind"] == "validated-feature-cache"
    assert provenance["cache_sha256"] == cache["cache_sha256"]
    assert provenance["features_sha256"] == cache["features_sha256"]
    assert provenance["input_rows_sha256"] == data.canonical_hash(cache["rows"])
