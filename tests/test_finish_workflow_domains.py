"""Two-domain workflow/calibration contracts on synthetic CPU files only."""
from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals.finish import workflow as w
from benchmark.remaining_goals.finish.calibration import calibrate_threshold
from benchmark.remaining_goals.finish.data import LABEL_CONTRACT
from benchmark.remaining_goals.finish.data_registry import (build_source_registry, registry_members,
                                                           source_identity, validate_source_registry)
from benchmark.remaining_goals.finish.data_profiles import EVAL_DOMAIN, HEAD_DOMAIN
from tests.finish_domain_helpers import make_assets
from tests.test_finish_workflow import fake_prepare, FakeEnv, FakePolicy, TinyRecorder, tree_bytes
from tests.test_remaining_finish_calibration import population


def rehash(value, field):
    value.pop(field, None)
    value[field] = w.canonical_hash(value)
    return value


def fixture(tmp_path):
    config = make_assets(tmp_path/"assets")
    registry = build_source_registry(config)
    registry_path = tmp_path/"registry.json"
    w.write_json(registry_path, registry)
    initials = np.load(config["init_states_path"], allow_pickle=False)
    def prepare(task, index, out, **kw):
        report = fake_prepare(task, index, out, **kw)
        original = initials[index]
        typed = {"dtype": original.dtype.str, "shape": list(original.shape),
                 "sha256": hashlib.sha256(original.tobytes()).hexdigest()}
        provenance = report["provenance"]
        provenance["official_initial_state_file"]["sha256"] = config["expected_assets"]["init_states_sha256"]
        provenance["restored_official_state"] = typed
        provenance["selected_official_state"] = typed
        report["episode"]["bddl_sha256"] = provenance["bddl_sha256"] = config["expected_assets"]["bddl_sha256"]
        w.write_json(out/"preparation.json", report, update=True)
        return report
    bank = tmp_path/"bank"
    result = w.prepare_normal_bank(list(range(35, 50)), bank, prepare=prepare, source_registry=registry_path)
    assert result["status"] == "prepared", result["error"]
    head = tmp_path/"head"
    head.mkdir()
    (head/"head.npz").write_bytes(b"synthetic byte-bound head; no model loading")
    manifest = {"schema_version": "remaining-finish-head-v2",
                "weights": {"path": "head.npz", "sha256": w.file_sha(head/"head.npz")},
                "identities": {"split_identity": source_identity(registry),
                               "base_identity": {"checkpoint": "synthetic-only"},
                               "data_identity": {"audit_sha256": "9"*64, "assets": deepcopy(registry["assets"]),
                                                 "profile_sha256": registry["profile_sha256"],
                                                 "registry_sha256": registry["registry_sha256"]},
                               "label_contract": deepcopy(LABEL_CONTRACT)}}
    manifest["identity_sha256"] = {key: w.canonical_hash(value) for key, value in manifest["identities"].items()}
    rehash(manifest, "artifact_sha256")
    w.write_json(head/"head.json", manifest)
    runtime = tmp_path/"runtime.json"
    w.write_json(runtime, {"model_id": "openvla_oft", "suite": "libero_10",
                          "execution": {"max_chunk_steps": 8, "random_seed": 7}})
    job = {"schema_version": "remaining-finish-job-v2", "purpose": "validation_shadow",
           "source_registry": str(registry_path), "runtime_config": str(runtime), "head_artifact": str(head),
           "source": {"kind": "normal_bank", "manifest": str(bank/"normal_bank.json")}}
    return job, registry, prepare


def calibration_population(registry, *, scores=None):
    legacy, results = population(scores=scores)
    members = registry_members(registry, EVAL_DOMAIN, "normal_calibration")
    episodes = [{"episode_id": old["episode_id"], "initial_state_index": member["initial_state_index"],
                 "eval_source": member} for old, member in zip(legacy, members)]
    for ep, result in zip(episodes, results):
        result["initial_state_index"] = ep["initial_state_index"]
    return episodes, results


def save_calibration(job, registry, directory):
    episodes, results = calibration_population(registry)
    head = w.head_manifest(job["head_artifact"])
    for result in results:
        for query in result["queries"]:
            query["head_identity"]["artifact_sha256"] = head["artifact_sha256"]
    report = calibrate_threshold(episodes, results, source_registry=registry, split_identity=source_identity(registry))
    report["binding"] = {"head_sha256": head["artifact_sha256"], "run_id": "synthetic",
                         "source_run_sha256": "0"*64}
    rehash(report, "calibration_sha256")
    path = directory/"calibration.json"
    w.write_json(path, report)
    job["calibration"] = str(path)
    return report


def test_new_dry_plan_uses_init_calibration_not_hdf_validation_and_keeps_bytes(tmp_path):
    job, registry, _ = fixture(tmp_path)
    before = tree_bytes(tmp_path)
    plan = w.dry_plan(job)
    assert plan["schema_version"] == "remaining-finish-plan-v2" and "split" not in plan
    assert plan["eval_domain"] == EVAL_DOMAIN and plan["eval_role"] == "normal_calibration"
    assert plan["expected"] == 5 and plan["maximum_physical_steps"] == 3350
    assert [e["initial_state_index"] for e in plan["episodes"]] == list(range(35, 40))
    assert plan["configuration"] == {"horizon": 520, "retention_steps": 150, "max_chunk_steps": 8}
    assert plan["source_identity"] == source_identity(registry)
    assert plan["ancestry_independence"] == "unproven"
    assert all(e["eval_source"]["source_key"].startswith("init:") for e in plan["episodes"])
    assert registry_members(registry, HEAD_DOMAIN, "head_validation")[0]["source_key"] != plan["eval_members"][0]["source_key"]
    assert tree_bytes(tmp_path) == before
    w._validate_plan_domains(plan)


def test_normal_active_and_remain_keep_exact_ten_and_fifteen_population(tmp_path, monkeypatch):
    job, registry, _ = fixture(tmp_path)
    save_calibration(job, registry, tmp_path)
    job["purpose"] = "normal_active"
    plan = w.dry_plan(job)
    assert plan["expected"] == 10 and plan["eval_role"] == "normal_test"
    assert [e["initial_state_index"] for e in plan["episodes"]] == list(range(40, 50))
    saved = w.load_source
    bank, _ = saved(job["source"])
    fake = {"environment": bank["environment"], "episodes": []}
    for index in range(5):
        for mask in ([False, False], [True, False], [False, True], [True, True]):
            item = deepcopy(bank["episodes"][0])
            item.update(episode_id=f"basket_{index}_{int(mask[0])}{int(mask[1])}", initial_mask=mask,
                        initial_state_index=index, seed=index, source_id=f"basket_official_{index}")
            fake["episodes"].append(item)
    fake_path = tmp_path/"synthetic_prevalidated_remain.json"
    w.write_json(fake_path, fake)
    monkeypatch.setattr(w, "load_source", lambda source: (deepcopy(fake), fake_path) if source["kind"] == "remain" else saved(source))
    job.update(purpose="remain_active", source={"kind": "remain", "manifest": str(fake_path)})
    plan = w.dry_plan(job)
    assert plan["expected"] == 15 and plan["maximum_physical_steps"] == 10050
    assert {tuple(e["initial_mask"]) for e in plan["episodes"]} == {(True, False), (False, True), (True, True)}
    assert {e["initial_state_index"] for e in plan["episodes"]} == set(range(5))
    assert "not a claim" in plan["source_binding_scope"]
    w._validate_plan_domains(plan)


@pytest.mark.parametrize("fault", ["legacy_head", "legacy_bank", "legacy_calibration", "wrong_head_registry", "wrong_calibration_domain", "wrong_calibration_members", "legacy_split", "changed_file",
                                  "head_data_profile", "head_data_registry", "head_data_asset", "head_identity_hash", "head_label_contract"])
def test_new_jobs_reject_mixed_or_substituted_artifacts_even_rehashed(tmp_path, fault):
    job, registry, _ = fixture(tmp_path)
    save_calibration(job, registry, tmp_path)
    job["purpose"] = "normal_active"
    if fault in {"legacy_head", "wrong_head_registry"} or fault.startswith("head_"):
        path = Path(job["head_artifact"])/"head.json"
        value = w.read_json(path)
        if fault == "legacy_head":
            value["schema_version"] = "remaining-finish-head-v1"
        elif fault == "wrong_head_registry":
            value["identities"]["split_identity"]["registry_sha256"] = "1"*64
        elif fault == "head_data_profile":
            value["identities"]["data_identity"]["profile_sha256"] = "2"*64
        elif fault == "head_data_registry":
            value["identities"]["data_identity"]["registry_sha256"] = "2"*64
        elif fault == "head_data_asset":
            value["identities"]["data_identity"]["assets"]["init_states_path"]["sha256"] = "2"*64
        elif fault == "head_label_contract":
            value["identities"]["label_contract"] = {"future_frame_is_positive": True}
        else:
            value["identity_sha256"]["data_identity"] = "2"*64
        if fault != "head_identity_hash":
            value["identity_sha256"] = {key: w.canonical_hash(item) for key, item in value["identities"].items()}
        rehash(value, "artifact_sha256")
        w.write_json(path, value, update=True)
    elif fault == "legacy_bank":
        path = Path(job["source"]["manifest"])
        value = w.read_json(path)
        value["schema_version"] = w.BANK_SCHEMA
        rehash(value, "content_hash")
        w.write_json(path, value, update=True)
    elif fault.startswith("legacy_calibration") or fault.startswith("wrong_calibration"):
        path = Path(job["calibration"])
        value = w.read_json(path)
        if fault == "legacy_calibration":
            value["schema_version"] = "remaining-finish-calibration-v1"
        elif fault == "wrong_calibration_domain":
            value["calibration_domain"] = HEAD_DOMAIN
        else:
            value["calibration_members"] = registry_members(registry, HEAD_DOMAIN, "head_validation")
        rehash(value, "calibration_sha256")
        w.write_json(path, value, update=True)
    elif fault == "legacy_split":
        job["split"] = {"validation": list(range(35, 40))}
    else:
        Path(registry["assets"]["init_states_path"]["path"]).write_bytes(b"same path, replaced bytes")
    with pytest.raises(ValueError):
        w.dry_plan(job)


@pytest.mark.parametrize("fault", ["init_file", "init_state", "index"])
def test_new_bank_preparation_must_bind_actual_registered_initial_not_settled_state(tmp_path, fault):
    job, registry, prepare = fixture(tmp_path)
    def invalid(task, index, out, **kw):
        report = prepare(task, index, out, **kw)
        if fault == "init_file":
            report["provenance"]["official_initial_state_file"]["sha256"] = "0"*64
        elif fault == "init_state":
            report["provenance"]["restored_official_state"] = report["provenance"]["settled_base_state"]
        else:
            report["provenance"]["initial_state_index"] = index+1
        w.write_json(out/"preparation.json", report, update=True)
        return report
    out = tmp_path/"bad-bank"
    report = w.prepare_normal_bank([35, 36], out, prepare=invalid, source_registry=registry)
    assert report["schema_version"] == w.BANK_SCHEMA_V2 and report["status"] == "preparation_error"
    assert report["expected_indices"] == [35, 36] and report["episodes"] == []
    assert len(report["preparations"]) == 1 and (out/"sources/035/preparation.json").is_file()
    with pytest.raises(ValueError, match="incomplete"):
        w.load_source({"kind": "normal_bank", "manifest": str(out/"normal_bank.json")})


def test_calibration_v2_uses_only_eval_members_and_preserves_first_hit_rules(tmp_path):
    registry = build_source_registry(make_assets(tmp_path))
    episodes, results = calibration_population(registry, scores={0: .8, 8: .95, 16: .98})
    report = calibrate_threshold(episodes, results, source_registry=registry, split_identity=source_identity(registry), thresholds=[.5, .9])
    assert report["schema_version"] == "remaining-finish-calibration-v2" and report["calibrated"]
    assert report["calibration_role"] == "normal_calibration" and report["calibration_domain"] == EVAL_DOMAIN
    assert report["candidates"][0]["premature"] == 5 and report["selected_threshold"] == .9
    assert report["ancestry_independence"] == "unproven" and not report["ordinary_stopping_capability_established"]
    episodes, results = calibration_population(registry, scores={0: .01, 8: .01, 16: .01})
    report = calibrate_threshold(episodes, results[:-1], source_registry=registry, split_identity=source_identity(registry))
    assert report["expected"] == 5 and report["missing"] == 1 and not report["calibrated"]


@pytest.mark.parametrize("fault", ["head_validation", "normal_test", "remain", "legacy_episode", "legacy_identity", "no_registry", "no_identity", "same_suffix_wrong_key"])
def test_calibration_rejects_wrong_domain_role_or_old_unified_contract(tmp_path, fault):
    registry = build_source_registry(make_assets(tmp_path))
    episodes, results = calibration_population(registry)
    kwargs = {"source_registry": registry, "split_identity": source_identity(registry)}
    if fault == "head_validation":
        episodes[0]["eval_source"] = registry_members(registry, HEAD_DOMAIN, "head_validation")[0]
    elif fault in {"normal_test", "remain"}:
        episodes[0]["eval_source"] = registry_members(registry, EVAL_DOMAIN, "normal_test" if fault == "normal_test" else "remain_test")[0]
    elif fault == "legacy_episode":
        episodes[0].update(source_index=35, split="validation")
    elif fault == "legacy_identity":
        kwargs["split_identity"] = {"split": {"validation": list(range(35, 40))}}
    elif fault == "no_registry":
        kwargs.pop("source_registry")
    elif fault == "no_identity":
        kwargs.pop("split_identity")
    else:
        episodes[0]["eval_source"]["source_key"] = registry_members(registry, HEAD_DOMAIN, "head_validation")[0]["source_key"]
    with pytest.raises(ValueError):
        calibrate_threshold(episodes, results, **kwargs)


def test_v2_fake_run_read_calibration_and_rescore_are_self_contained_readonly(tmp_path, monkeypatch):
    job, registry, _ = fixture(tmp_path)
    plan = w.dry_plan(job)
    # CPU fake budget only; never present this diagnostic as physical validation.
    plan["configuration"] = {"horizon": 9, "retention_steps": 4, "max_chunk_steps": 8}
    for ep in plan["episodes"]:
        ep.update(horizon=9, retention_steps=4)
    plan["head_sha256"] = "b"*64
    rehash(plan, "plan_sha256")
    monkeypatch.setattr(w, "dry_plan", lambda _: deepcopy(plan))
    out = tmp_path/"run"
    env, policy = FakeEnv(), FakePolicy()
    metadata = w.run({}, out, policy_factory=lambda _: policy, env_factory=lambda _: env, recorder_factory=TinyRecorder)
    assert metadata["schema_version"] == w.RUN_SCHEMA_V2 and metadata["status"] == "completed"
    before = tree_bytes(out)
    # Offline run verification/calibration uses the immutable registry snapshot,
    # never today's external file path nor an HDF numeric-suffix mapping.
    Path(job["source_registry"]).write_text("registry subsequently moved", encoding="utf-8")
    assert len(w.read_run(out)[1]) == 5
    report = w.calibrate(out, tmp_path/"cal")
    assert report["schema_version"] == "remaining-finish-calibration-v2" and not report["calibrated"]
    assert report["calibration_source_keys"] == [row["source_key"] for row in plan["eval_members"]]
    summary = w.rescore(out, tmp_path/"derived")
    assert summary["counts"]["expected"] == 5 and summary["counts"]["successful"] is None
    assert tree_bytes(out) == before
    assert env.closed == policy.closed == 1
    metadata["plan"]["eval_members"][0]["role"] = "head_validation"
    rehash(metadata["plan"], "plan_sha256")
    metadata["run_config_sha256"] = metadata["plan"]["plan_sha256"]
    w.write_json(out/"run.json", metadata, update=True)
    with pytest.raises(ValueError):
        w.read_run(out)


def test_legacy_run_and_calibration_tests_remain_explicit_v1():
    episodes, results = population()
    report = calibrate_threshold(episodes, results)
    assert report["schema_version"] == "remaining-finish-calibration-v1"
    assert "calibration_domain" not in report and "source_identity" not in report
