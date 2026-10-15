"""Task008 synthetic file/CPU audit contract; no real physics or model execution."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py", reason="synthetic two-domain HDF fixture requires optional h5py")

from benchmark.remaining_goals.finish import data
from benchmark.remaining_goals.finish import data_profiles as profiles
from benchmark.remaining_goals.finish import data_registry as registry
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from tests.finish_domain_helpers import FakeProvider, make_assets, make_audit


def resign_audit(value):
    value["audit_sha256"] = data.canonical_hash({key: item for key, item in value.items() if key != "audit_sha256"})
    return value


def resign_registry(value):
    for name in ("head_registry", "eval_registry"):
        part = value[name]
        part["sha256"] = data.canonical_hash({key: item for key, item in part.items() if key != "sha256"})
    value["registry_sha256"] = registry._registry_digest(value)
    return value


def refresh_expected(config, path_key):
    config["expected_assets"][profiles.ASSET_KEYS[path_key]] = data._file_hash(config[path_key])


def test_fixed_domain_members_and_same_numeric_suffix_are_independent(tmp_path):
    config = make_assets(tmp_path)
    value = registry.build_source_registry(config)
    head = registry.registry_members(value, profiles.HEAD_DOMAIN, "head_validation")
    evaluation = registry.registry_members(value, profiles.EVAL_DOMAIN, "normal_calibration")
    assert [r["trajectory_id"] for r in head] == [f"demo_{i}" for i in range(35, 40)]
    assert [r["initial_state_index"] for r in evaluation] == list(range(35, 40))
    assert head[0]["source_key"] != evaluation[0]["source_key"]
    assert head[0]["state_sha256s"][0] != evaluation[0]["state_sha256"]
    assert all("source_index" not in row for row in value["head_registry"]["records"])
    assert value["demo_to_init_mapping"] is None and value["ancestry_independence"] == "unproven"
    assert value["ready_for_feature_export"] is False and value["labels_generated"] == 0
    identity = registry.source_identity(value)
    assert registry.validate_source_identity(identity) == identity
    assert str(tmp_path) not in str(identity)
    relocated = deepcopy(value)
    for asset in relocated["assets"].values():
        asset["path"] = "other-machine/not-present"
    assert registry.source_identity(relocated) == identity
    with pytest.raises((OSError, ValueError)):
        registry.validate_source_registry(relocated, verify_files=True)


@pytest.mark.parametrize("field", ["profile_id", "domain", "role", "overlap", "bool_index", "new_member"])
def test_fixed_profile_rejects_renaming_overlap_and_replacement(field):
    value = deepcopy(profiles.DEFAULT_PROFILE)
    if field == "profile_id":
        value[field] = "other"
    elif field == "domain":
        value["domains"]["head"] = value["domains"].pop(profiles.HEAD_DOMAIN)
    elif field == "role":
        groups = value["domains"][profiles.HEAD_DOMAIN]["groups"]
        groups["validation"] = groups.pop("head_validation")
    elif field == "overlap":
        value["domains"][profiles.HEAD_DOMAIN]["groups"]["head_validation"][0] = "demo_5"
    elif field == "bool_index":
        value["domains"][profiles.EVAL_DOMAIN]["groups"]["remain_test"][0] = False
    else:
        value["domains"][profiles.EVAL_DOMAIN]["groups"]["normal_calibration"][0] = 50
    with pytest.raises(ValueError):
        profiles.validate_profile(value)


@pytest.mark.parametrize("legacy", ["trajectory_source_map", "split", "alternative_confirmation"])
def test_v2_config_refuses_legacy_mapping_even_if_empty(tmp_path, legacy):
    config = make_assets(tmp_path)
    config[legacy] = {}
    with pytest.raises(ValueError, match="legacy"):
        data.audit_plan(config)


@pytest.mark.parametrize("entry", [data.audit_plan, data.audit_demonstrations])
def test_removing_profile_cannot_silently_downgrade_new_config(tmp_path, entry):
    config = make_assets(tmp_path)
    del config["data_profile"]
    with pytest.raises(ValueError, match="profile"):
        entry(config)


def test_plan_only_checks_existence_and_never_reads_dataset_or_creates_provider(tmp_path, monkeypatch):
    config = make_assets(tmp_path)
    monkeypatch.setattr(data, "read_demonstrations", lambda *_: pytest.fail("plan must not read HDF"))
    monkeypatch.setattr(data, "read_initial_states", lambda *_: pytest.fail("plan must not load init"))
    value = data.audit_plan(config)
    assert value["simulation_created"] is value["weights_loaded"] is value["ready_for_feature_export"] is False
    assert value["restoration_roles"] == ["head_train", "head_validation"]


def test_file_registry_never_certifies_physical_audit_or_generates_labels(tmp_path):
    config = make_assets(tmp_path / "assets")
    out = tmp_path / "registry-only"
    value = data.audit_demonstrations(config, out=out)
    assert value["status"] == "insufficient" and value["rows"] == []
    assert value["registry"]["ready_for_feature_export"] is False
    assert value["work_counts"]["restore_attempts"] == value["work_counts"]["hold_attempts"] == 0
    assert (out / "registry.json").is_file()
    with pytest.raises(ValueError, match="insufficient"):
        data.validate_audit(value, base_dir=out)


def test_unmatched_demonstrations_can_enter_only_declared_fake_physical_audit(tmp_path):
    out, audit, provider = make_audit(tmp_path)
    assert len(audit["rows"]) == len(provider.restore_calls) == 70
    assert len(provider.hold_calls) == 35 and provider.closed
    assert audit["provider_identity"]["test_only"] is True
    assert audit["provider_identity"]["physics_validated"] is False
    assert {row["role"] for row in audit["rows"]} == {"head_train", "head_validation"}
    assert {int(state[0]-1000) for state, _ in provider.restore_calls} == set(range(5, 40))
    assert all("source_index" not in row and "split" not in row for row in audit["rows"])
    assert data.validate_audit(audit, base_dir=out) == audit
    assert audit["coverage"][profiles.HEAD_DOMAIN]["head_unused"]["audited_frames"] == 0
    assert all(record["restored_frames"] == 0 for record in audit["coverage"][profiles.EVAL_DOMAIN].values())


@pytest.mark.parametrize("asset_key", list(profiles.ASSET_KEYS))
def test_actual_file_hash_changes_block_registry_and_later_training_validation(tmp_path, asset_key):
    out, audit, _ = make_audit(tmp_path)
    path = Path(audit["assets"][asset_key]["path"])
    with path.open("ab") as stream:
        stream.write(b"changed source bytes")
    with pytest.raises(ValueError, match="source file changed"):
        data.validate_audit(audit, base_dir=out)


@pytest.mark.parametrize("fault", ["missing_group", "extra_group", "missing_xml", "fewer_init", "duplicate_state"])
def test_source_file_defects_fail_before_any_physical_provider(tmp_path, fault):
    config = make_assets(tmp_path / "assets")
    if fault == "fewer_init":
        np.save(config["init_states_path"], np.zeros((49, 3)))
        refresh_expected(config, "init_states_path")
    else:
        with h5py.File(config["hdf5_path"], "a") as source:
            if fault == "missing_group":
                del source["data/demo_35"]
            elif fault == "extra_group":
                source.copy("data/demo_35", "data/demo_50")
            elif fault == "missing_xml":
                del source["data/demo_0"].attrs["model_file"]
            else:
                source["data/demo_35/states"][0] = source["data/demo_5/states"][0]
        refresh_expected(config, "hdf5_path")
    result = data.audit_demonstrations(config, out=tmp_path / "audit",
        provider_factory=lambda _: pytest.fail("invalid registry cannot initialize provider"))
    assert result["status"] == "insufficient" and not result["rows"]


@pytest.mark.parametrize("location,field,value", [
    ("root", "trajectory_source_map", {}), ("head", "source_index", 35),
    ("head", "initial_state_index", 35), ("head", "edited_variant", True),
    ("eval", "trajectory_id", "demo_35"), ("eval", "manually_confirmed", True),
])
def test_resigned_registry_cannot_mix_legacy_or_eval_records(tmp_path, location, field, value):
    source = registry.build_source_registry(make_assets(tmp_path))
    target = source if location == "root" else source["head_registry" if location == "head" else "eval_registry"]["records"][0]
    target[field] = value
    resign_registry(source)
    with pytest.raises(ValueError):
        registry.validate_source_registry(source)


@pytest.mark.parametrize("fault", ["eval_domain", "unused_role", "wrong_key", "wrong_frame", "legacy_index", "edited"])
def test_resigned_audit_rejects_wrong_row_domain_role_or_frame(tmp_path, fault):
    out, audit, _ = make_audit(tmp_path)
    row = audit["rows"][0]
    if fault == "eval_domain":
        row["domain"] = profiles.EVAL_DOMAIN
    elif fault == "unused_role":
        row["role"] = "head_unused"
    elif fault == "wrong_key":
        row["source_key"] = registry.registry_members(audit["registry"], profiles.EVAL_DOMAIN, "normal_calibration")[0]["source_key"]
    elif fault == "wrong_frame":
        row["saved_state_index"] = 1
    elif fault == "legacy_index":
        row["source_index"] = 35
    else:
        row["edited_variant"] = True
    with pytest.raises(ValueError):
        data.validate_audit(resign_audit(audit), base_dir=out)


def test_current_inputs_are_saved_before_hold_and_cannot_contain_metadata(tmp_path):
    config = make_assets(tmp_path / "assets")
    class MutatingProvider(FakeProvider):
        def restore_demonstration(self, state, model_xml=None):
            result = super().restore_demonstration(state, model_xml)
            self.last = result["observation"]
            return result
        def capture_hold_label(self, state, steps, model_xml=None):
            self.last["agentview_image"][:] = 255
            self.last["robot0_eef_pos"][:] = -999
            return super().capture_hold_label(state, steps, model_xml)
    provider = MutatingProvider()
    out = tmp_path / "audit"
    audit = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    data.validate_audit(audit, base_dir=out)
    for row in audit["rows"]:
        observation = load_observation_artifact(out, row["observation"])
        assert np.all(observation["agentview_image"] < 255)
        assert observation["robot0_eef_pos"][0] > 0
    class BadProvider(FakeProvider):
        def restore_demonstration(self, state, model_xml=None):
            value = super().restore_demonstration(state, model_xml)
            value["observation"]["role"] = "head_train"
            return value
    bad = BadProvider()
    failed = data.audit_demonstrations(config, out=tmp_path / "bad", provider_factory=lambda _: bad)
    assert failed["status"] == "insufficient" and bad.closed and not bad.hold_calls


def test_cross_head_group_raw_observation_duplicate_is_insufficient(tmp_path):
    config = make_assets(tmp_path / "assets")
    class DuplicatingProvider(FakeProvider):
        def restore_demonstration(self, state, model_xml=None):
            result = super().restore_demonstration(state, model_xml)
            result["observation"]["agentview_image"][:] = 0
            result["observation"]["robot0_eye_in_hand_image"][:] = 0
            result["observation"]["robot0_eef_pos"][:] = 0
            return result
    result = data.audit_demonstrations(config, out=tmp_path / "audit", provider_factory=lambda _: DuplicatingProvider())
    assert result["status"] == "insufficient"
    assert any("observation duplicate" in issue.get("message", "") for issue in result["issues"])


@pytest.mark.parametrize("fault", ["unknown_to_positive", "last_frame_positive", "missing_sample", "work_counts"])
def test_resigned_labels_and_coverage_still_recomputed(tmp_path, fault):
    out, audit, _ = make_audit(tmp_path)
    row = next(row for row in audit["rows"] if row["saved_state_index"] == 1)
    if fault == "unknown_to_positive":
        row["hold_evidence"] = None
    elif fault == "last_frame_positive":
        row["current"]["goals"] = [False, False]
    elif fault == "missing_sample":
        audit["rows"].pop()
    else:
        audit["work_counts"]["restore_attempts"] = 0
    with pytest.raises(ValueError):
        data.validate_audit(resign_audit(audit), base_dir=out)


@pytest.mark.parametrize("fault", ["all_negative", "hold_error", "close_error", "interrupted"])
def test_insufficient_and_partial_audits_preserve_evidence_and_close(tmp_path, fault):
    config = make_assets(tmp_path / "assets")
    class FailingProvider(FakeProvider):
        def restore_demonstration(self, state, model_xml=None):
            value = super().restore_demonstration(state, model_xml)
            if fault == "all_negative":
                value["goals"] = [False, False]
            return value
        def capture_hold_label(self, state, steps, model_xml=None):
            if fault == "hold_error":
                raise RuntimeError("synthetic hold failure")
            if fault == "interrupted":
                raise KeyboardInterrupt("synthetic interruption")
            return super().capture_hold_label(state, steps, model_xml)
        def close(self):
            super().close()
            if fault == "close_error":
                raise RuntimeError("synthetic close failure")
    provider, out = FailingProvider(), tmp_path / "audit"
    if fault == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
        result = data.read_json(out / "audit.json")
        assert result["status"] == "interrupted"
    else:
        result = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
        assert result["status"] == "insufficient"
    assert provider.closed
    if fault in {"hold_error", "interrupted"}:
        assert len(result["rows"]) == 2 and result["rows"][-1]["label"] is None
        load_observation_artifact(out, result["rows"][-1]["observation"])
    with pytest.raises(FileExistsError):
        data.audit_demonstrations(config, out=out, provider_factory=lambda _: pytest.fail("must not reuse output"))


def test_new_domain_audit_cannot_be_relabelled_as_legacy(tmp_path):
    out, audit, _ = make_audit(tmp_path)
    audit["schema_version"] = data.AUDIT_SCHEMA
    with pytest.raises(ValueError, match="legacy"):
        data.validate_audit(resign_audit(audit), base_dir=out)


@pytest.mark.parametrize("bad", [[], np.zeros(2), {"trace": np.zeros(2)}, {"value": float("nan")}])
def test_malformed_hold_return_keeps_partial_artifacts_and_close(tmp_path, bad):
    config = make_assets(tmp_path / "assets")
    class BadHold(FakeProvider):
        def capture_hold_label(self, *args, **kwargs):
            return bad
    provider, out = BadHold(), tmp_path / "audit"
    result = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert result["status"] == "insufficient" and provider.closed
    assert len(result["rows"]) == 2 and result["rows"][-1]["label"] is None
    assert result["rows"][-1]["hold_evidence"] is None
    assert data.read_json(out / "audit.json") == result
    load_observation_artifact(out, result["rows"][-1]["observation"])


def test_none_hold_stays_unknown_without_becoming_negative_or_breaking_partial_counts(tmp_path):
    config = make_assets(tmp_path / "assets")
    class UnknownHold(FakeProvider):
        def capture_hold_label(self, state, steps, model_xml=None):
            return None if state[0] == 1005 else super().capture_hold_label(state, steps, model_xml)
    out = tmp_path / "audit"
    result = data.audit_demonstrations(config, out=out, provider_factory=lambda _: UnknownHold())
    assert result["status"] == "ready_for_feature_export"
    row = next(row for row in result["rows"] if row["trajectory_id"] == "demo_5" and row["saved_state_index"] == 1)
    assert row["label"] is None and row["reason"] == "passive_hold_evidence_missing"
    assert result["work_counts"]["hold_attempts"] == 35 and result["work_counts"]["hold_branches"] == 34
    data.validate_audit(result, base_dir=out)


def test_non_json_release_evidence_is_structured_error_not_lost_audit(tmp_path):
    config = make_assets(tmp_path / "assets")
    class BadEvidence(FakeProvider):
        def restore_demonstration(self, state, model_xml=None):
            result = super().restore_demonstration(state, model_xml)
            result["release_evidence"] = {"not_json": np.zeros(2)}
            return result
    provider, out = BadEvidence(), tmp_path / "audit"
    result = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert result["status"] == "insufficient" and result["rows"] == [] and provider.closed
    assert data.read_json(out / "audit.json") == result
