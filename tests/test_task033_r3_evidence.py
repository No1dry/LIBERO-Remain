"""Pure file evidence revalidation; native/model work is forbidden."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals.validation import compare_observations, RGB_QUANTIZATION_AUDIT
from benchmark.remaining_goals.headless.scoped_sources import resolve_source, archive_source, inspect_candidate
from tests.test_headless_nine_integration import make_nine_source, _source_observation


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False), encoding="utf-8")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence(tmp_path, monkeypatch, *, incomplete=False, error=1, physical=False):
    origin = make_nine_source(tmp_path / "original", monkeypatch, "two_pots", "nine-mask10")
    report_path = Path(origin["candidate_replay"])
    report = json.loads(report_path.read_text())
    path = report_path.parent / report["episodes"][1]["audit_path"]
    audit = json.loads(path.read_text())
    if incomplete:
        audit.update(trace=[], completed_steps=0, static_acceptance=False,
            technical_acceptance=False, dynamic_stability=False,
            error={"phase":"restore_candidate", "type":"RuntimeError", "message":"old reset mismatch"})
        report["episodes"][1].update(technical_acceptance=False, error=audit["error"])
    else:
        row = audit["trace"][15]
        returned = _source_observation(np.asarray(row["state"]))
        fresh = deepcopy(returned)
        fresh["robot0_eye_in_hand_image"] += error
        row["observation_check"] = compare_observations(returned, fresh,
            refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
        row["checks"]["observation_matches_fresh"] = False
        audit["checks"]["observation_matches_fresh"] = False
        if physical:
            row["qvel"] = [.02]
            row["max_abs_velocity"] = .02
            row["checks"]["velocities_below_limit"] = False
            audit["checks"]["velocities_below_limit"] = False
        audit.update(technical_acceptance=False, dynamic_stability=False)
        report["episodes"][1].update(technical_acceptance=False, checks=audit["checks"])
    report["technical_acceptance"] = False
    _write(path, audit)
    _write(report_path, report)
    origin["replay_sha256"] = _sha(report_path)
    return origin


def test_complete_v4_failure_derives_v6_certificate_without_rewriting(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for p in (tmp_path / "original").rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        resolve_source("nine-mask10", "two_pots", 0, origin)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "ready" and result["required_native_steps"] == 0
    certificate = json.loads(Path(result["origin"]["rgb_certificate"]).read_text())
    assert certificate["recorded_diagnostics_revalidated"] is True
    assert certificate["new_native_steps"] == 0
    assert certificate["scope"] == "source"
    assert (tmp_path / "derived/derivation_report.json").is_file()
    plan = resolve_source("nine-mask10", "two_pots", 0, result["origin"])
    assert plan["status"] == "ready"
    archive_source(tmp_path / "derived_archive", plan)
    assert before == {str(p): p.read_bytes() for p in (tmp_path / "original").rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        resolve_source("nine-mask10", "two_pots", 0, origin)


def test_missing_second_window_requires_replay_not_file_only_ready(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch, incomplete=True)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "needs_replay" and result["required_native_steps"] == 300
    assert inspect_candidate("two_pots", 0, origin["manifest"], protocol="nine-mask10",
        rgb_certificate=result["origin"]["rgb_certificate"])["episode"]["initial_mask"] == [True, False]
    with pytest.raises(ValueError):
        resolve_source("nine-mask10", "two_pots", 0, result["origin"])


@pytest.mark.parametrize("options", [{"error": 2}, {"physical": True}])
def test_real_non_rgb_or_physical_failure_is_blocked(tmp_path, monkeypatch, options):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch, **options)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    assert result["status"] == "blocked" and "rgb_certificate" not in result["origin"]


def test_missing_artifact_and_bad_hash_are_distinct(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    missing = derive_source("two_pots", 9, {"manifest": str(tmp_path / "absent/missing.json")}, tmp_path / "missing")
    assert missing["status"] == "needs_build"
    origin = evidence(tmp_path, monkeypatch)
    origin["manifest_sha256"] = "0" * 64
    bad = derive_source("two_pots", 0, origin, tmp_path / "bad")
    assert bad["status"] == "blocked"


def test_derived_certificate_tamper_or_input_change_rejected(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin = evidence(tmp_path, monkeypatch)
    result = derive_source("two_pots", 0, origin, tmp_path / "derived")
    path = Path(result["origin"]["rgb_certificate"])
    cert = json.loads(path.read_text())
    cert["new_native_steps"] = 1
    _write(path, cert)
    with pytest.raises(ValueError):
        resolve_source("nine-mask10", "two_pots", 0, result["origin"])


def test_missing_replay_file_retains_complete_construction(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin=evidence(tmp_path,monkeypatch)
    report_path=Path(origin["candidate_replay"])
    report=json.loads(report_path.read_text())
    (report_path.parent/report["episodes"][1]["audit_path"]).unlink()
    result=derive_source("two_pots",0,origin,tmp_path/"derived")
    assert result["status"]=="needs_replay" and result["required_native_steps"]==300
    assert json.loads(Path(result["origin"]["rgb_certificate"]).read_text())["scope"]=="construction"


def test_native_v6_normal00_reader_keeps_initial_only_scope(tmp_path, monkeypatch):
    from benchmark.remaining_goals.validation import V6_PROFILE, validate_candidate, observation_profile_config
    from benchmark.remaining_goals.schema import manifest_hash
    from benchmark.remaining_goals.build import HOLD
    from tests.test_headless_nine_integration import SourceAudit
    from benchmark.remaining_goals.headless.rgb_revalidation import derive_source
    origin=make_nine_source(tmp_path/"v6_source",monkeypatch,"two_pots","nine-normal00")
    mp=Path(origin["manifest"])
    manifest=json.loads(mp.read_text())
    episode=manifest["episodes"][0]
    manifest["observation_profile"]=episode["observation_profile"]=V6_PROFILE
    state=np.load(mp.parent/episode["state_path"],allow_pickle=False)
    audit=validate_candidate(SourceAudit(state,episode["task_semantics"]),episode,
        steps=0,hold_action=HOLD,observation_profile=V6_PROFILE)
    _write(mp.parent/episode["construction"]["technical_audit"],audit)
    manifest["content_hash"]=manifest_hash(manifest)
    _write(mp,manifest)
    ip=Path(origin["initialization"])
    initial=json.loads(ip.read_text())
    config=observation_profile_config(V6_PROFILE)
    initial.update(observation_profile=V6_PROFILE,observation_audit_rule=config["rule"],observation_audit_limits=config["limits"])
    _write(ip,initial)
    origin.update(manifest_sha256=_sha(mp),content_hash=manifest["content_hash"],initialization_sha256=_sha(ip))
    plan=resolve_source("nine-normal00","two_pots",0,origin)
    assert plan["status"]=="ready"
    accepted=plan["source_acceptance"]
    assert accepted["acceptance_scope"]=="initial00" and accepted["dynamic_stability"] is None
    assert accepted["episodes"][0]["construction"]["steps"]==0
    assert accepted["episodes"][0]["replays"]==[]
    archive_source(tmp_path/"v6_initial_archive",plan)
    with pytest.raises(ValueError,match="nine-mask10"):
        derive_source("two_pots",0,origin,tmp_path/"forbidden_00_derivation",protocol="nine-normal00")
