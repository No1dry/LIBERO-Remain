"""Independent R3 evidence-boundary regressions; CPU/fakes only."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals.headless.scoped_sources import _observation_binding, resolve_source
from benchmark.remaining_goals.validation import V6_PROFILE, compare_observations
from tests.test_task033_r3_profile import obs
from tests.test_task033_r3_queue import setup_r3
from tests.test_task033_r3_evidence import evidence, _write, _sha
from tests.test_headless_nine_integration import SourceAudit, _source_observation


@pytest.mark.parametrize("mutation", ["camera_hash", "camera_shape"])
def test_v6_initial_camera_diagnostics_bind_typed_artifact(mutation):
    original = obs()
    comparison = compare_observations(original, obs(1), observation_profile=V6_PROFILE,
                                      refresh_state_unchanged=True, require_non_rgb_exact=True)
    camera = comparison["image_diagnostics"]["observation.agentview_image"]
    if mutation == "camera_hash":
        camera["returned_sha256"] = "f" * 64
    else:
        camera["shape"] = [8, 32, 3]
    with pytest.raises(ValueError):
        _observation_binding(original, comparison, profile=V6_PROFILE)


def test_outer_dispatch_interruption_is_not_automatically_retried(tmp_path, monkeypatch):
    r3, inventory, report, _ = setup_r3(tmp_path, monkeypatch)
    r3.plan_repairs(inventory, report, tmp_path / "plan")
    called = []
    def interrupted(*args, **options):
        called.append((options["tasks"][0], options["indices"][0]))
        raise KeyboardInterrupt("interruption before child ledger exists")
    monkeypatch.setattr(r3.preparation, "prepare", interrupted)
    with pytest.raises(KeyboardInterrupt):
        r3.prepare_repairs(tmp_path / "plan/repair_plan.json", tmp_path / "prepared")
    first = called[0]
    def remaining(*args, **options):
        key = options["tasks"][0], options["indices"][0]
        called.append(key)
        return {"sources": [{"task_id": key[0], "initial_state_index": key[1],
                              "status": "failed", "origin": None, "actual_control_steps": None}]}
    monkeypatch.setattr(r3.preparation, "prepare", remaining)
    result = r3.prepare_repairs(tmp_path / "plan/repair_plan.json", tmp_path / "prepared", continuation=True)
    assert called.count(first) == 1
    interrupted_row = next(row for row in result["sources"]
                           if (row["task_id"], row["initial_state_index"]) == first)
    assert interrupted_row["status"] != "ready"


@pytest.mark.parametrize("target", ["manifest", "episode", "report"])
def test_legacy_derived_evidence_rejects_foreign_envelope_profile(tmp_path, monkeypatch, target):
    from benchmark.remaining_goals.schema import manifest_hash
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch)
    manifest_path, report_path = Path(origin["manifest"]), Path(origin["candidate_replay"])
    manifest = json.loads(manifest_path.read_text())
    report = json.loads(report_path.read_text())
    if target == "report":
        report["observation_profile"] = "foreign-v7"
    else:
        envelope = manifest if target == "manifest" else manifest["episodes"][0]
        envelope["observation_profile"] = "foreign-v7"
        manifest["content_hash"] = manifest_hash(manifest)
        _write(manifest_path, manifest)
        origin.update(manifest_sha256=_sha(manifest_path), content_hash=manifest["content_hash"])
        report.update(source_manifest_sha256=origin["manifest_sha256"], source_content_hash=origin["content_hash"])
    _write(report_path, report)
    origin["replay_sha256"] = _sha(report_path)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "blocked"
    assert "rgb_certificate" not in result.get("origin", {})


def test_candidate_certificate_remains_readable_after_v6_paired_replay_and_archive(tmp_path, monkeypatch):
    from benchmark.remaining_goals import selected_replay, replay_candidates
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    from benchmark.remaining_goals.headless.scoped_sources import archive_source, validate_snapshot
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    origin = evidence(tmp_path, monkeypatch, incomplete=True)
    old_bytes = {str(p): p.read_bytes() for p in (tmp_path / "original").rglob("*") if p.is_file()}
    derived = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert derived["status"] == "needs_replay" and derived["required_native_steps"] == 300
    manifest = json.loads(Path(origin["manifest"]).read_text())
    semantics = manifest["episodes"][0]["task_semantics"]
    calls = []
    def changed(state):
        value = _source_observation(state)
        value["robot0_eye_in_hand_image"] += 1
        return value
    class Replay(SourceAudit):
        def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir, observation_profile):
            assert observation_profile == V6_PROFILE
            super().__init__(state, semantics)
            actual, frozen = changed(state), _source_observation(state)
            self.reset_checks = {"saved_state_exact": True, "initial_mask_exact": True,
                "construction_observation_matches": True, "initial_non_rgb_exact": True}
            self.reset_observation_comparison = compare_observations(actual, frozen, atol=0,
                require_non_rgb_exact=True, refresh_state_unchanged=True, observation_profile=observation_profile)
            self.reset_initial_observation = save_observation_artifact(frames_dir, "initial_observation.npz", actual)
            self.post_restore_xml_sha256 = "c" * 64
        def restore_candidate(self, episode):
            super().restore_candidate(episode)
            return changed(self.state)
        def step(self, action):
            super().step(action)
            calls.append(1)
            return changed(self.state)
    monkeypatch.setattr(replay_candidates, "ReplayAuditEnv", Replay)
    directory = tmp_path / "new_replay"
    replay = selected_replay.replay(origin["manifest"], directory, task="two_pots", index=0,
        protocol="nine-mask10", observation_profile=V6_PROFILE,
        rgb_certificate=derived["origin"]["rgb_certificate"])
    assert replay["technical_acceptance"] is True and len(calls) == 300
    replay_path = directory / "replay_report.json"
    combined = {**derived["origin"], "candidate_replay": str(replay_path), "replay_sha256": _sha(replay_path)}
    plan = resolve_source("nine-mask10", "two_pots", 0, combined)
    assert plan["status"] == "ready"
    archive_source(tmp_path / "archive", plan)
    validate_snapshot(tmp_path / "archive", plan)
    assert old_bytes == {str(p): p.read_bytes() for p in (tmp_path / "original").rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["missing_hash", "changed_state", "camera_identity", "nonrgb_failure", "comparison_profile"])
def test_recorded_diagnostics_cannot_derive_through_invalid_bindings(tmp_path, monkeypatch, mutation):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    from benchmark.remaining_goals.validation import RGB_QUANTIZATION_AUDIT
    origin = evidence(tmp_path, monkeypatch)
    report_path = Path(origin["candidate_replay"])
    report = json.loads(report_path.read_text())
    audit_path = report_path.parent / report["episodes"][1]["audit_path"]
    audit = json.loads(audit_path.read_text())
    row = audit["trace"][15]
    check = row["observation_check"]
    if mutation == "missing_hash":
        del check["fresh_sha256"]
    elif mutation == "changed_state":
        check["rgb_allowance_state_verified"] = False
    elif mutation == "camera_identity":
        camera = check["image_diagnostics"].pop("observation.robot0_eye_in_hand_image")
        check["image_diagnostics"]["observation.images.foreign"] = camera
        check["mismatched_fields"] = ["observation.images.foreign"]
    elif mutation == "comparison_profile":
        check["observation_profile"] = "foreign-v7"
    else:
        returned = _source_observation(np.asarray(row["state"]))
        fresh = deepcopy(returned)
        fresh["robot0_eye_in_hand_image"] += 1
        # A saved non-RGB value outside the existing 1e-8 requirement.
        for key in fresh:
            if not key.endswith("_image"):
                fresh[key] = np.asarray(fresh[key], dtype=float) + 2e-8
                break
        row["observation_check"] = compare_observations(returned, fresh,
            refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    _write(audit_path, audit)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "blocked"
    assert "rgb_certificate" not in result.get("origin", {})


@pytest.mark.parametrize("mutation", ["missing", "foreign"])
def test_source_origin_requires_certificate_raw_hash(tmp_path, monkeypatch, mutation):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "ready"
    chosen = deepcopy(result["origin"])
    if mutation == "missing":
        del chosen["rgb_certificate_sha256"]
    else:
        chosen["rgb_certificate_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        resolve_source("nine-mask10", "two_pots", 0, chosen)


def test_recorded_dynamic_nonrgb_within_original_tolerance_stays_eligible(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    from benchmark.remaining_goals.validation import RGB_QUANTIZATION_AUDIT
    origin = evidence(tmp_path, monkeypatch)
    report_path = Path(origin["candidate_replay"])
    report = json.loads(report_path.read_text())
    audit_path = report_path.parent / report["episodes"][1]["audit_path"]
    audit = json.loads(audit_path.read_text())
    row = audit["trace"][15]
    returned = _source_observation(np.asarray(row["state"]))
    fresh = deepcopy(returned)
    fresh["robot0_eye_in_hand_image"] += 1
    key = next(key for key in fresh if not key.endswith("_image"))
    fresh[key] = np.asarray(fresh[key], dtype=float) + 1e-9
    row["observation_check"] = compare_observations(returned, fresh,
        refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    assert row["observation_check"]["non_rgb_bit_exact"] is False
    assert row["observation_check"]["mismatched_fields"] == ["observation.robot0_eye_in_hand_image"]
    _write(audit_path, audit)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "ready", result
    resolve_source("nine-mask10", "two_pots", 0, result["origin"])


def test_plan_rejects_changed_candidate_certificate_before_any_native_dispatch(tmp_path, monkeypatch):
    r3, inventory, report, _ = setup_r3(tmp_path, monkeypatch)
    derive = r3._derive_source
    certificate_path = None
    def with_certificate(task, index, origin, output, **options):
        nonlocal certificate_path
        result = derive(task, index, origin, output, **options)
        if index == 7:
            certificate_path = Path(output) / "certificate.json"
            certificate_path.write_text('{"synthetic":true}', encoding="utf-8")
            result["origin"].update(rgb_certificate=str(certificate_path), rgb_certificate_sha256=_sha(certificate_path))
            _write(Path(output) / "derivation_report.json", result)
        return result
    monkeypatch.setattr(r3, "_derive_source", with_certificate)
    r3.plan_repairs(inventory, report, tmp_path / "plan")
    certificate_path.write_text(certificate_path.read_text() + "\n", encoding="utf-8")
    calls = []
    def prepare(*args, **options):
        key = options["tasks"][0], options["indices"][0]
        calls.append(key)
        return {"sources": [{"task_id": key[0], "initial_state_index": key[1],
                              "status": "failed", "origin": None, "actual_control_steps": None}]}
    monkeypatch.setattr(r3.preparation, "prepare", prepare)
    with pytest.raises(ValueError, match="certificate"):
        r3.prepare_repairs(tmp_path / "plan/repair_plan.json", tmp_path / "prepared")
    assert calls == []
