"""Independent source/replay admission tests; fake physics, real artifact checks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from benchmark.remaining_goals import cli, evaluation, package_audit, pilot, replay_candidates as replay
from .test_remaining_replay_candidates import pack, write_json


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def options(**overrides):
    return {"policy_config": {}, "policy_id": "SYNTHETIC-subset", "max_chunk_steps": 8,
            "masks": ["10", "01", "11"], "video_config": {"enabled": True}, **overrides}


@pytest.fixture
def candidate(pack):
    manifest_path, replay_directory, manifest, record = pack
    report = replay.replay(manifest_path, replay_directory, steps=150, repeats=2)
    assert report["technical_acceptance"] is True
    return manifest_path, replay_directory / "replay_report.json", manifest, record


def forbidden(*args, **kwargs):
    pytest.fail("dry planning/admission must not construct a policy")


def test_dry_plan_validates_complete_candidate_replay_without_factory_or_new_environment(candidate, monkeypatch):
    path, replay_path, manifest, record = candidate
    before = {file: file.read_bytes() for folder in (path.parent, replay_path.parent)
              for file in folder.rglob("*") if file.is_file()}
    instances = len(record.instances)
    monkeypatch.setattr(cli, "_factory", forbidden)
    plan = pilot.dry_plan(path, candidate_replay=replay_path, **options())
    assert plan["expected"] == 3 and plan["source_expected"] == 4
    assert plan["not_selected_ids"] == [manifest["episodes"][0]["episode_id"]]
    assert plan["weights_loaded"] is plan["simulation_created"] is False
    evidence = plan["candidate_replay_evidence"]
    assert evidence["summary"]["expected_records"] == evidence["summary"]["records"] == 8
    assert evidence["sha256"] == hashlib.sha256(replay_path.read_bytes()).hexdigest()
    assert len(record.instances) == instances
    assert all(file.read_bytes() == body for file, body in before.items())


def test_bad_unselected_00_state_is_not_hidden_by_mask_selection(candidate, monkeypatch):
    path, replay_path, manifest, _ = candidate
    normal = next(episode for episode in manifest["episodes"] if not any(episode["initial_mask"]))
    np.save(path.parent / normal["state_path"], np.array([99.]))
    monkeypatch.setattr(cli, "_factory", forbidden)
    with pytest.raises(ValueError):
        pilot.dry_plan(path, candidate_replay=replay_path, **options())


@pytest.mark.parametrize("tamper", ["omit_00", "duplicate", "wrong_source_hash", "false_pass"])
def test_source_requires_every_episode_repeat_and_true_replay_evidence(candidate, tamper, monkeypatch):
    path, replay_path, manifest, _ = candidate
    report = read_json(replay_path)
    if tamper == "omit_00":
        normal = manifest["episodes"][0]["episode_id"]
        report["episodes"] = [row for row in report["episodes"] if row["episode_id"] != normal]
    elif tamper == "duplicate":
        report["episodes"][-1] = deepcopy(report["episodes"][0])
    elif tamper == "wrong_source_hash":
        report["source_manifest_sha256"] = "f" * 64
    elif tamper == "false_pass":
        report["episodes"][0]["technical_acceptance"] = False
    write_json(replay_path, report)
    monkeypatch.setattr(cli, "_factory", forbidden)
    with pytest.raises(ValueError):
        pilot.dry_plan(path, candidate_replay=replay_path, **options())


def test_changed_unselected_00_audit_is_independently_rechecked(candidate):
    path, replay_path, manifest, _ = candidate
    report = read_json(replay_path)
    normal = manifest["episodes"][0]["episode_id"]
    row = next(row for row in report["episodes"] if row["episode_id"] == normal)
    audit_path = replay_path.parent / row["audit_path"]
    audit = read_json(audit_path)
    audit["trace"][1]["goals"] = [True, True]
    write_json(audit_path, audit)
    with pytest.raises(ValueError):
        pilot.dry_plan(path, candidate_replay=replay_path, **options())


@pytest.mark.parametrize("steps,repeats", [(1, 2), (150, 1)])
def test_pilot_replay_covers_at_least_source_retention_and_two_repeats(pack, steps, repeats):
    path, directory, _, _ = pack
    report = replay.replay(path, directory, steps=steps, repeats=repeats)
    assert report["technical_acceptance"] is True  # Valid shorter diagnostic, insufficient pilot admission.
    with pytest.raises(ValueError):
        pilot.dry_plan(path, candidate_replay=directory / "replay_report.json", **options())


def test_replay_bytes_cannot_change_between_validation_and_snapshot(candidate, monkeypatch):
    path, replay_path, _, _ = candidate
    actual = package_audit.validate_replay_evidence

    def mutate_after_validation(*args, **kwargs):
        result = actual(*args, **kwargs)
        replay_path.write_bytes(replay_path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(package_audit, "validate_replay_evidence", mutate_after_validation)
    with pytest.raises(ValueError, match="changed"):
        pilot.dry_plan(path, candidate_replay=replay_path, **options())


@pytest.mark.parametrize("tamper_file", ["manifest.json", "source/replay_report.json"])
def test_run_snapshots_preserve_source_bytes_and_offline_reader_rejects_tampering(candidate, tmp_path, monkeypatch, tamper_file):
    path, replay_path, _, _ = candidate

    def failed_factory(config):
        raise RuntimeError("SYNTHETIC model initialization failure; no policy loaded")

    monkeypatch.setattr(cli, "_factory", lambda _: failed_factory)
    output = tmp_path / "startup-error-run"
    summary = pilot.evaluate_subset(path, output, policy_factory="synthetic:failed_factory",
                                    candidate_replay=replay_path, **options())
    assert summary["run_status"] == "technical_paused"
    assert summary["counts"]["expected"] == 3
    assert summary["counts"]["runtime_error"] == 1 and summary["counts"]["missing"] == 2
    assert (output / "manifest.json").read_bytes() == path.read_bytes()
    assert (output / "source/replay_report.json").read_bytes() == replay_path.read_bytes()
    cli.read_run(output)
    target = output / tamper_file
    target.write_bytes(target.read_bytes() + b"\n")  # Semantically identical JSON still violates frozen byte evidence.
    with pytest.raises(ValueError, match="snapshot"):
        cli.read_run(output)


def test_public_dry_plan_creates_only_new_plan_and_never_resolves_policy_factory(candidate, tmp_path, monkeypatch):
    manifest_path, replay_path, _, record = candidate
    config = {"model_id": "openvla_oft", "policy_id": "SYNTHETIC-uninstalled",
              "policy_factory": "unavailable_model_module:make_policy", "suite": "libero_10",
              "execution": {"random_seed": 7, "max_chunk_steps": 8},
              "runtime": {"python_executable": sys.executable},
              "adapter_options": {"suite": "libero_10", "repo_path": "not-installed", "checkpoint": "not-downloaded"}}
    config_path = tmp_path / "model.json"
    write_json(config_path, config)
    monkeypatch.setattr(cli, "_factory", forbidden)
    before = len(record.instances)
    output = tmp_path / "new-plan.json"
    plan = evaluation.pilot(config_path, manifest_path, output, masks=["10", "01", "11"],
                            candidate_replay=replay_path, video_config={"enabled": True}, dry=True)
    assert output.is_file() and read_json(output) == plan
    assert plan["expected"] == 3 and plan["weights_loaded"] is False
    assert len(record.instances) == before
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        evaluation.pilot(config_path, manifest_path, output, masks=["10", "01", "11"],
                         candidate_replay=replay_path, video_config={"enabled": True}, dry=True)
    assert output.read_bytes() == original


def test_bom_candidate_bytes_survive_snapshot_and_offline_read(candidate, tmp_path, monkeypatch):
    path, replay_path, _, _ = candidate
    source_raw = b"\xef\xbb\xbf" + path.read_bytes()
    path.write_bytes(source_raw)
    report = read_json(replay_path)
    report["source_manifest_sha256"] = hashlib.sha256(source_raw).hexdigest()
    write_json(replay_path, report)

    def failed_factory(config):
        raise RuntimeError("SYNTHETIC startup failure; source evidence remains reviewable")

    monkeypatch.setattr(cli, "_factory", lambda _: failed_factory)
    output = tmp_path / "bom-run"
    pilot.evaluate_subset(path, output, policy_factory="synthetic:failed_factory",
                          candidate_replay=replay_path, **options())
    assert (output / "manifest.json").read_bytes() == source_raw
    metadata, manifest, results = cli.read_run(output)
    assert len(manifest["episodes"]) == 4 and len(results) == 1
    assert metadata["execution_selection"]["expected"] == 3
