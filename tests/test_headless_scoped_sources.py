"""CPU-only fixed-source acceptance and portable provenance regressions."""
from copy import deepcopy
import hashlib
import json
import re
import shutil

import numpy as np
import pytest

from tests.test_headless_source_acceptance import make_source, SyntheticAudit, HOLD, write
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.validation import validate_candidate, RGB_QUANTIZATION_AUDIT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def official_instruction(task):
    from benchmark.remaining_goals.task_catalog import TASKS
    return re.split(r"SCENE\d+_", TASKS[task]["name"], maxsplit=1)[1].replace("_", " ")


@pytest.fixture
def selected(tmp_path):
    mp, rp, manifest, report = make_source(tmp_path, "frypan_stove9")
    for e in manifest["episodes"]:
        e["instruction"] = official_instruction(e["task_id"])
    manifest["content_hash"] = manifest_hash(manifest)
    write(mp, manifest)
    report.update(source_manifest_sha256=sha(mp), source_content_hash=manifest["content_hash"])
    write(rp, report)
    origin = {"manifest": str(mp), "manifest_sha256": sha(mp), "content_hash": manifest["content_hash"],
              "candidate_replay": str(rp), "replay_sha256": sha(rp)}
    return mp, rp, manifest, report, origin


def normal_source(selected, *, later_failure=False):
    mp, rp, manifest, report, origin = selected
    e = next(e for e in manifest["episodes"] if e["episode_id"] == "frypan_stove9_s000_00")
    state = np.load(mp.parent / e["state_path"], allow_pickle=False)
    audit = validate_candidate(SyntheticAudit(state), e, steps=150 if later_failure else 0,
                               hold_action=HOLD, **RGB_QUANTIZATION_AUDIT)
    if later_failure:
        audit["trace"][7]["qvel"] = [.9]
        audit["technical_acceptance"] = audit["dynamic_stability"] = False
        audit["checks"]["velocities_below_limit"] = False
    write(mp.parent / e["construction"]["technical_audit"], audit)
    initialization = {"kind": "normal00_initialization_v1", "protocol": "normal00-control",
        "environment": manifest["environment"], "initialization_kind": "settled_base", "settle_steps": 80,
        "hold_action": HOLD, "groups": [{"task_id": e["task_id"], "initial_state_index": 0,
        "episode_id": e["episode_id"], "base_state_array_sha256": audit["trace"][0]["state_sha256"],
        "state_sha256": e["state_sha256"], "initial_observation_sha256": e["initial_observation"]["sha256"]}]}
    ip = mp.parent / "construction_report.json"
    write(ip, initialization)
    origin = {k: v for k, v in origin.items() if k not in ("candidate_replay", "replay_sha256")}
    origin.update(initialization=str(ip), initialization_sha256=sha(ip))
    return e, audit, origin


def api():
    from benchmark.remaining_goals.headless import scoped_sources
    return scoped_sources


def test_per_index_selected_ignores_other_source_failure_and_archives(selected, tmp_path):
    mp, rp, manifest, report, origin = selected
    bad = next(e for e in manifest["episodes"] if e["episode_id"] == "frypan_stove9_s001_10")
    (mp.parent / bad["state_path"]).unlink()
    module = api()
    candidate = module.inspect_candidate("frypan_stove9", 0, mp)
    assert candidate["construction"]["steps"] == 150
    assert candidate["episode"]["episode_id"] == "frypan_stove9_s000_10"
    plan = module.resolve_source("selected-mask10", "frypan_stove9", 0, origin)
    assert len(plan["episodes"]) == 1
    assert len(plan["source_acceptance"]["episodes"][0]["replays"]) == 2
    archive = tmp_path / "snapshot"
    root = module.archive_source(archive, plan)
    assert root == archive / "source" / "manifest_files"
    assert mp.parent.resolve().is_relative_to(tmp_path.resolve())
    assert rp.parent.resolve().is_relative_to(tmp_path.resolve())
    shutil.rmtree(mp.parent)
    shutil.rmtree(rp.parent)
    assert module.validate_snapshot(archive, plan) == root
    (root / plan["episodes"][0]["state_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError): module.validate_snapshot(archive, plan)


def test_normal_initial_scope_retains_failed_original_hold(selected, tmp_path):
    e, audit, origin = normal_source(selected, later_failure=True)
    module = api()
    plan = module.resolve_source("normal00-control", "frypan_stove9", 0, origin)
    evidence = plan["source_acceptance"]
    assert evidence["acceptance_scope"] == "initial00"
    assert evidence["episodes"][0]["construction"]["steps"] == 0
    assert evidence["original_audit_diagnostic"]["technical_acceptance"] is False
    assert evidence["initialization"]["settle_steps"] == 80
    root = module.archive_source(tmp_path / "normal", plan)
    assert module.validate_snapshot(tmp_path / "normal", plan) == root


@pytest.mark.parametrize("fault", ["velocity", "goals", "state", "contact", "fresh_hash", "cached_numeric", "observation", "instruction", "settle", "initialization_hash"])
def test_normal_initial_invalidity_or_unbound_provenance_rejected(selected, fault):
    mp, _, manifest, _, _ = selected
    e, audit, origin = normal_source(selected)
    if fault == "velocity": audit["trace"][0]["qvel"] = [.2]
    elif fault == "goals": audit["trace"][0]["goals"] = [True, False]
    elif fault == "state": audit["trace"][0]["state"][0] = -.1
    elif fault == "contact": audit["trace"][0]["penetrations"] = [{"geom1": "a", "geom2": "b", "depth": .1, "ignored": False}]
    elif fault == "fresh_hash": audit["trace"][0]["observation_check"]["fresh_non_rgb_sha256"] = "a" * 64
    elif fault == "cached_numeric": audit["trace"][0]["max_abs_velocity"] = .0001
    elif fault == "observation": (mp.parent / e["initial_observation"]["path"]).write_bytes(b"bad")
    elif fault == "instruction":
        e["instruction"] = "only turn on stove"
        manifest["content_hash"] = manifest_hash(manifest)
        write(mp, manifest)
        origin.update(manifest_sha256=sha(mp), content_hash=manifest["content_hash"])
    elif fault == "settle":
        ip = mp.parent / "construction_report.json"
        init = json.loads(ip.read_text())
        init.pop("settle_steps")
        write(ip, init)
        origin["initialization_sha256"] = sha(ip)
    else: origin["initialization_sha256"] = "f" * 64
    write(mp.parent / e["construction"]["technical_audit"], audit)
    with pytest.raises(ValueError): api().resolve_source("normal00-control", "frypan_stove9", 0, origin)


@pytest.mark.parametrize("fault", ["limit", "hold", "ignored", "replay_binding", "repeat", "wrong_manifest_hash", "wrong_index"])
def test_selected_fixed_contract_and_origin_binding(selected, fault):
    mp, rp, manifest, report, origin = selected
    e = next(e for e in manifest["episodes"] if e["episode_id"] == "frypan_stove9_s000_10")
    ap = mp.parent / e["construction"]["technical_audit"]
    audit = json.loads(ap.read_text())
    if fault == "limit": audit["limits"]["velocity_tolerance"] = 1.
    elif fault == "hold": audit["hold_action"][-1] = 1.
    elif fault == "ignored": audit["ignored_contact_pairs"] = [["a", "b"]]
    elif fault == "replay_binding": report["source_manifest_sha256"] = "f" * 64
    elif fault == "repeat": report["episodes"] = [r for r in report["episodes"] if not (r["episode_id"] == e["episode_id"] and r["repetition"] == 1)]
    elif fault == "wrong_manifest_hash": origin["manifest_sha256"] = "f" * 64
    write(ap, audit)
    write(rp, report)
    origin["replay_sha256"] = sha(rp)
    expected = api().MissingSourceError if fault == "repeat" else ValueError
    with pytest.raises(expected): api().resolve_source("selected-mask10", "frypan_stove9", 10 if fault == "wrong_index" else 0, origin)


def test_candidate_missing_failed_and_missing_replay_are_distinct(selected):
    mp, _, manifest, _, origin = selected
    module = api()
    missing = {k:v for k,v in origin.items() if k not in ("candidate_replay", "replay_sha256")}
    assert module.inspect_candidate("frypan_stove9", 0, mp)["construction"]["steps"] == 150
    with pytest.raises(module.MissingSourceError): module.resolve_source("selected-mask10", "frypan_stove9", 0, missing)
    e = next(e for e in manifest["episodes"] if e["episode_id"] == "frypan_stove9_s000_10")
    ap = mp.parent / e["construction"]["technical_audit"]
    audit = json.loads(ap.read_text())
    audit["technical_acceptance"] = False
    write(ap, audit)
    with pytest.raises(module.FailedSourceError): module.inspect_candidate("frypan_stove9", 0, mp)
    ap.unlink()
    with pytest.raises(module.MissingSourceError): module.inspect_candidate("frypan_stove9", 0, mp)



def test_snapshot_never_falls_back_to_live_initialization(selected, tmp_path, monkeypatch):
    from pathlib import Path
    from benchmark.remaining_goals.headless.source_acceptance import _canonical
    _, _, origin = normal_source(selected)
    module = api()
    plan = module.resolve_source("normal00-control", "frypan_stove9", 0, origin)
    archive = tmp_path / "portable"
    module.archive_source(archive, plan)
    plan["source_snapshot_files"].pop("initialization")
    plan["source_plan_sha256"] = _canonical({k:v for k,v in plan.items() if k != "source_plan_sha256"})
    original = Path.read_bytes
    def archived_only(path):
        assert path.resolve().is_relative_to(archive.resolve()), "snapshot attempted live-origin read"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", archived_only)
    with pytest.raises(ValueError): module.validate_snapshot(archive, plan)


def test_partial_selected_replay_is_missing_evidence(selected):
    _, rp, _, report, origin = selected
    report["episodes"] = [r for r in report["episodes"] if not (
        r["episode_id"] == "frypan_stove9_s000_10" and r["repetition"] == 1)]
    write(rp, report)
    origin["replay_sha256"] = sha(rp)
    with pytest.raises(api().MissingSourceError):
        api().resolve_source("selected-mask10", "frypan_stove9", 0, origin)


def test_normal_explicit_failed_static_is_not_promoted(selected):
    mp = selected[0]
    e, audit, origin = normal_source(selected)
    audit["static_acceptance"] = False
    write(mp.parent / e["construction"]["technical_audit"], audit)
    with pytest.raises(api().FailedSourceError):
        api().resolve_source("normal00-control", "frypan_stove9", 0, origin)


@pytest.mark.parametrize("fault", ["typed_non_rgb", "camera_geometry"])
def test_initial_recorded_correspondence_binds_typed_artifact(selected, fault):
    mp = selected[0]
    e, audit, origin = normal_source(selected)
    comparison = audit["trace"][0]["observation_check"]
    if fault == "typed_non_rgb":
        comparison["returned_non_rgb_sha256"] = comparison["fresh_non_rgb_sha256"] = "c" * 64
    else:
        comparison["image_diagnostics"]["observation.agentview_image"]["total_pixels"] = 16
    write(mp.parent / e["construction"]["technical_audit"], audit)
    with pytest.raises(ValueError): api().resolve_source("normal00-control", "frypan_stove9", 0, origin)


@pytest.mark.parametrize("kind", ["original", "raw_official"])
def test_initialization_original_or_explicit_raw_provenance(selected, kind):
    from benchmark.remaining_goals.task_catalog import TASKS
    mp, _, manifest, _, _ = selected
    e, audit, origin = normal_source(selected)
    ip = mp.parent / "construction_report.json"
    report = json.loads(ip.read_text())
    if kind == "original":
        report.update(kind="real_libero_candidate_construction", task_catalog={e["task_id"]: TASKS[e["task_id"]]})
        report["groups"][0].update(suite=e["suite"],task_name=e["task_name"],reset_model_xml_sha256=e["model_xml_sha256"])
    else:
        report.update(initialization_kind="raw_official", settle_steps=0)
        report["groups"][0]["raw_official_state_array_sha256"] = report["groups"][0]["base_state_array_sha256"]
    write(ip, report)
    origin["initialization_sha256"] = sha(ip)
    plan = api().resolve_source("normal00-control", "frypan_stove9", 0, origin)
    assert plan["source_acceptance"]["initialization"]["settle_steps"] == (0 if kind == "raw_official" else 80)


def test_wrong_source_partial_replay_is_malformed_not_missing(selected):
    _, rp, _, report, origin = selected
    report["episodes"] = []
    report["source_manifest_sha256"] = "d" * 64
    write(rp, report)
    origin["replay_sha256"] = sha(rp)
    with pytest.raises(ValueError): api().resolve_source("selected-mask10", "frypan_stove9", 0, origin)


@pytest.mark.parametrize("reuse", ["audit", "reset_artifact"])
def test_selected_replay_repetitions_require_distinct_evidence_files(selected, reuse):
    _, rp, _, report, origin = selected
    rows = [r for r in report["episodes"] if r["episode_id"] == "frypan_stove9_s000_10"]
    if reuse == "audit":
        rows[1]["audit_path"] = rows[0]["audit_path"]
    else:
        # Separate audit documents may still point at the same typed reset
        # observation when both live in one directory. That is one capture.
        first = rp.parent / rows[0]["audit_path"]
        second = rp.parent / rows[1]["audit_path"]
        shared_dir_audit = first.parent / "second_audit.json"
        shared_dir_audit.write_bytes(second.read_bytes())
        rows[1]["audit_path"] = shared_dir_audit.relative_to(rp.parent).as_posix()
    write(rp, report)
    origin["replay_sha256"] = sha(rp)
    with pytest.raises(ValueError, match="distinct|reused"):
        api().resolve_source("selected-mask10", "frypan_stove9", 0, origin)


def test_distinct_replay_files_with_identical_bytes_remain_valid(selected):
    _, rp, _, report, origin = selected
    rows = [r for r in report["episodes"] if r["episode_id"] == "frypan_stove9_s000_10"]
    first, second = [rp.parent / r["audit_path"] for r in rows]
    assert first != second and first.read_bytes() == second.read_bytes()
    assert api().resolve_source("selected-mask10", "frypan_stove9", 0, origin)["status"] == "ready"
