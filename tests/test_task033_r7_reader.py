"""CPU-only R7 readers; generated audit data is not physical evidence."""
from copy import deepcopy

import numpy as np
import pytest

from benchmark.remaining_goals.headless import source_acceptance as reader
from benchmark.remaining_goals.headless import rgb_revalidation as rgb
from benchmark.remaining_goals.validation import validate_candidate, V6_PROFILE
from tests.test_headless_source_acceptance import SyntheticAudit, HOLD

PROFILE = "active-free-object-pose-stability-v7"


def legacy_audit():
    state = np.array([0., .4, 1., 0.])
    episode = {"episode_id": "legacy", "initial_mask": [True, False], "reference_robot_qpos": [.4]}
    audit = validate_candidate(SyntheticAudit(state), episode, steps=150, hold_action=HOLD,
                               observation_profile=V6_PROFILE)
    return episode, state, audit


def read(audit, episode, state):
    return reader._audit(audit, episode, state, steps=150,
        initial_hash=audit["trace"][0]["observation_check"]["returned_sha256"], fixed=True)


@pytest.mark.parametrize("profile", [PROFILE, "unknown-physical-profile"])
def test_legacy_v6_reader_rejects_physical_profile_even_when_active_velocity_is_low(profile):
    episode, state, audit = legacy_audit()
    audit["stability_profile"] = episode["stability_profile"] = profile
    with pytest.raises(ValueError):
        rgb.audit_v6(audit, episode, state, steps=150,
            initial_hash=audit["trace"][0]["observation_check"]["returned_sha256"], fixed=True)


@pytest.mark.parametrize("location", ["audit", "episode"])
def test_dispatch_rejects_unknown_stability_profile(location):
    episode, state, audit = legacy_audit()
    (audit if location == "audit" else episode)["stability_profile"] = "unknown-physical-profile"
    with pytest.raises(ValueError):
        read(audit, episode, state)


def test_original_v6_interpretation_remains_valid():
    episode, state, audit = legacy_audit()
    assert read(audit, episode, state)["technical_acceptance"] is True


def active_audit():
    from tests.test_task033_r7_stability import episode, run
    e, audit = episode(), run()
    return e, np.asarray(audit["trace"][0]["state"]), audit


def test_v7_high_active_qvel_recomputes_sign_equivalent_raw_pose_window():
    episode, state, audit = active_audit()
    result = read(audit, episode, state)
    assert result["technical_acceptance"] is True
    assert result["stability_profile"] == PROFILE
    assert result["observation_profile"] == V6_PROFILE
    assert result["stability_window"]["active_velocity_exceedance_fraction"] == 1.
    assert audit["trace"][1]["qvel"][9:15] == [.1] * 6


@pytest.mark.parametrize("fault", ["old_schema", "no_profile", "no_binding", "wrong_binding", "rgb_confusion",
    "missing_point", "position", "rotation", "non_active_velocity", "pose_cache", "velocity_cache",
    "predicate", "penetration", "robot", "observation", "qvel_binding", "position_binding"])
def test_v7_rejects_incomplete_changed_or_cross_profile_evidence(fault):
    episode, state, audit = active_audit()
    row = audit["trace"][70]
    if fault == "old_schema": audit["schema_version"] = "remaining-goals-validation-v1"
    elif fault == "no_profile": audit.pop("stability_profile")
    elif fault == "no_binding": audit.pop("stability_binding")
    elif fault == "wrong_binding": audit["stability_binding"]["model_xml_sha256"] = "b" * 64
    elif fault == "rgb_confusion": audit["observation_profile"] = PROFILE
    elif fault == "missing_point": audit["trace"].pop()
    elif fault == "position": row["state"][10] = .006
    elif fault == "rotation": row["state"][13:17] = [np.cos(.02), 0., 0., np.sin(.02)]
    elif fault == "non_active_velocity": row["state"][33] = row["qvel"][15] = .02
    elif fault == "pose_cache": row["stability_sample"]["active_pose_wxyz"][0] = .0001
    elif fault == "velocity_cache": row["stability_window"]["peak_abs_active_velocity"] = 0.
    elif fault == "predicate": row["required_open_values"] = [False]
    elif fault == "penetration": row["penetrations"] = [{"geom1":"cup", "geom2":"door", "depth":.003, "ignored":False}]
    elif fault == "robot": row["robot_qpos"][0] = .003
    elif fault == "observation": row["observation_check"]["fresh_non_rgb_sha256"] = "b" * 64
    elif fault == "qvel_binding": row["qvel"][9] = 0.
    elif fault == "position_binding": row["object_positions"]["white_yellow_mug_1"][0] = .001
    with pytest.raises(ValueError):
        read(audit, episode, state)


def test_v7_cannot_be_regraded_by_v6_rgb_certificate_reader():
    episode, state, audit = active_audit()
    with pytest.raises(ValueError):
        reader._audit(audit, episode, state, steps=150, initial_hash=audit["trace"][0]["observation_check"]["returned_sha256"],
                      revalidate_profile=V6_PROFILE)


def active_source(tmp_path):
    import hashlib
    import json
    import re
    from benchmark.remaining_goals.schema import manifest_hash
    from benchmark.remaining_goals.nine_catalog import get_task
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.validation import compare_observations, observation_profile_config
    from tests.test_task033_r7_stability import episode, snapshots, FakeEnv
    from tests.test_headless_source_acceptance import write

    root, replay = tmp_path / "bank", tmp_path / "replay"
    root.mkdir(parents=True)
    e, rows = episode(), snapshots()
    task = "mug_microwave_close"
    e.update(episode_id=f"{task}_s000_10", source_id=f"{task}_official_0", seed=0, split="val",
        pose_id="cpu_fake", horizon=520, retention_steps=150, bddl_sha256="b" * 64,
        instruction=re.split(r"SCENE\d+_", get_task(task)["name"], maxsplit=1)[1].replace("_", " "))
    e["construction"].update(legal=False, method="cpu fake", reviewed_by="pending", technical_audit="validation/audit.json")
    np.save(root / "state.npy", rows[0]["state"])
    e.update(state_path="state.npy", state_sha256=hashlib.sha256((root / "state.npy").read_bytes()).hexdigest())
    obs = rows[0]["fresh_observation"]
    e["initial_observation"] = save_observation_artifact(root, "validation/initial_observation.npz", obs)
    audit = validate_candidate(FakeEnv(rows), e, steps=150, hold_action=HOLD,
                               observation_profile=V6_PROFILE, stability_profile=PROFILE)
    write(root / "validation/audit.json", audit)
    manifest = {"schema_version":"remaining-goals-v0.1", "environment":{"name":"libero", "fingerprint":"cpu fake"},
        "observation_profile":V6_PROFILE, "stability_profile":PROFILE, "stability_binding":deepcopy(e["stability_binding"]),
        "episodes":[e]}
    manifest["content_hash"] = manifest_hash(manifest)
    mp, rp = root / "manifest.candidates.json", replay / "replay_report.json"
    write(mp, manifest)
    config = observation_profile_config(V6_PROFILE)
    report = {"kind":"candidate_formal_adapter_replay", "protocol":"nine-mask10", "policy_called":False,
        "release_authorized":False, "source_manifest_sha256":hashlib.sha256(mp.read_bytes()).hexdigest(),
        "source_content_hash":manifest["content_hash"], "steps":150, "repeats":2, "technical_acceptance":True,
        "error":None, "observation_profile":V6_PROFILE, "observation_audit_rule":config["rule"],
        "observation_audit_limits":config["limits"], "stability_profile":PROFILE,
        "stability_binding":deepcopy(e["stability_binding"]), "episodes":[]}
    for repeat in range(2):
        ap = f"repeat_{repeat}/audit.json"
        comparison = compare_observations(obs, obs, atol=0, require_non_rgb_exact=True,
            refresh_state_unchanged=True, observation_profile=V6_PROFILE)
        reset = {"saved_state_exact":True, "initial_mask_exact":True,
            "construction_observation_matches":True, "initial_non_rgb_exact":True,
            "stability_binding_matches_compiled_model":True}
        repeated = deepcopy(audit)
        repeated.update(formal_reset_checks=reset, reset_observation_comparison=comparison,
            reset_initial_observation=save_observation_artifact(replay / f"repeat_{repeat}", "initial_observation.npz", obs),
            expected_reset_model_xml_sha256=e["model_xml_sha256"], post_restore_model_xml_sha256=e["model_xml_sha256"])
        write(replay / ap, repeated)
        report["episodes"].append({"episode_id":e["episode_id"], "repetition":repeat, "initial_mask":[True,False],
            "source_legal":False, "technical_acceptance":True, "reset_checks":reset, "checks":deepcopy(audit["checks"]),
            "error":None, "audit_path":ap})
    write(rp, report)
    origin = {"manifest":str(mp), "manifest_sha256":hashlib.sha256(mp.read_bytes()).hexdigest(),
        "content_hash":manifest["content_hash"], "candidate_replay":str(rp), "replay_sha256":hashlib.sha256(rp.read_bytes()).hexdigest()}
    return mp, rp, manifest, report, origin


def test_new_v7_source_and_archive_use_bound_file_only_reader(tmp_path):
    from benchmark.remaining_goals.headless.scoped_sources import inspect_candidate, resolve_source, archive_source, validate_snapshot
    mp, rp, manifest, report, origin = active_source(tmp_path)
    before = {p:p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    candidate = inspect_candidate("mug_microwave_close", 0, mp, protocol="nine-mask10", stability_profile=PROFILE)
    assert candidate["construction"]["stability_profile"] == PROFILE
    plan = resolve_source("nine-mask10", "mug_microwave_close", 0, origin)
    evidence = plan["source_acceptance"]["episodes"][0]
    assert [r["steps"] for r in evidence["replays"]] == [150, 150]
    archive = tmp_path / "archive"
    archive_source(archive, plan)
    validate_snapshot(archive, plan)
    assert before == {p:p.read_bytes() for p in before}


@pytest.mark.parametrize("fault", ["manifest_profile", "manifest_binding", "report_profile", "report_binding",
                                   "repeat", "reused_audit", "wrong_requested_profile"])
def test_v7_file_chain_requires_complete_consistent_physical_provenance(tmp_path, fault):
    import hashlib
    from benchmark.remaining_goals.schema import manifest_hash
    from benchmark.remaining_goals.headless.scoped_sources import resolve_source, inspect_candidate
    from tests.test_headless_source_acceptance import write
    mp, rp, manifest, report, origin = active_source(tmp_path)
    if fault == "manifest_profile": manifest.pop("stability_profile")
    elif fault == "manifest_binding": manifest["stability_binding"]["model_xml_sha256"] = "c" * 64
    elif fault == "report_profile": report.pop("stability_profile")
    elif fault == "report_binding": report["stability_binding"]["model_xml_sha256"] = "c" * 64
    elif fault == "repeat": report["episodes"].pop()
    elif fault == "reused_audit": report["episodes"][1]["audit_path"] = report["episodes"][0]["audit_path"]
    else:
        with pytest.raises(ValueError):
            inspect_candidate("mug_microwave_close", 0, mp, protocol="nine-mask10", stability_profile="unknown")
        return
    manifest["content_hash"] = manifest_hash(manifest)
    write(mp, manifest)
    report.update(source_manifest_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(), source_content_hash=manifest["content_hash"])
    write(rp, report)
    origin.update(manifest_sha256=report["source_manifest_sha256"], content_hash=manifest["content_hash"],
                  replay_sha256=hashlib.sha256(rp.read_bytes()).hexdigest())
    with pytest.raises((ValueError, FileNotFoundError)):
        resolve_source("nine-mask10", "mug_microwave_close", 0, origin)


@pytest.mark.parametrize("fault", ["translation", "rotation", "non_active_velocity"])
def test_complete_raw_generated_failures_cannot_be_reclassified_ready(fault):
    from tests.test_task033_r7_stability import episode, snapshots, FakeEnv
    rows, e = snapshots(), episode()
    if fault == "translation":
        rows[70]["state"][10] = rows[70]["object_positions"]["white_yellow_mug_1"][0] = .0051
    elif fault == "rotation":
        angle = np.deg2rad(1.01) / 2
        rows[70]["state"][13:17] = [np.cos(angle), 0., 0., np.sin(angle)]
    else:
        rows[70]["state"][33] = rows[70]["qvel"][15] = .0101
    rows[70]["state_before_refresh"] = rows[70]["state"].copy()
    audit = validate_candidate(FakeEnv(rows), e, steps=150, hold_action=HOLD,
                               observation_profile=V6_PROFILE, stability_profile=PROFILE)
    assert audit["technical_acceptance"] is False
    assert len(audit["trace"]) == 151
    with pytest.raises(ValueError):
        read(audit, e, rows[0]["state"])


def test_low_a_velocity_does_not_allow_v7_old_schema_downgrade():
    from tests.test_task033_r7_stability import episode, snapshots, FakeEnv
    e, rows = episode(), snapshots()
    for row in rows:
        row["state"][27:33] = row["qvel"][9:15] = 0.
        row["state_before_refresh"] = row["state"].copy()
    audit = validate_candidate(FakeEnv(rows), e, steps=150, hold_action=HOLD,
                               observation_profile=V6_PROFILE, stability_profile=PROFILE)
    assert audit["technical_acceptance"] is True
    audit["schema_version"] = "remaining-goals-validation-v1"
    with pytest.raises(ValueError):
        read(audit, e, rows[0]["state"])


@pytest.mark.parametrize("physical_field", ["stability_profile", "stability_binding"])
def test_v6_certificate_cannot_carry_physical_admission_metadata(tmp_path, physical_field):
    import json
    cert = {"schema_version":rgb.SCHEMA, "observation_profile":V6_PROFILE,
        "protocol":"nine-mask10", "task_id":"mug_microwave_close", "initial_state_index":0,
        "scope":"construction", "recorded_diagnostics_revalidated":True, "new_native_steps":0,
        "raw_rgb_recomputed":False, "limitation":rgb.LIMITATION, physical_field:PROFILE}
    cert["certificate_sha256"] = reader._canonical(cert)
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(cert), encoding="utf-8")
    with pytest.raises(ValueError):
        rgb._read_certificate("mug_microwave_close", 0, tmp_path / "absent.json", path, "nine-mask10")
