"""Unified evaluation lifecycle and candidate-pilot contracts, using CPU fakes."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmark.remaining_goals import cli, evaluation, package_audit, replay_candidates
from benchmark.remaining_goals.schema import load_manifest, manifest_hash, validate_manifest
from benchmark.remaining_goals.toy import build_toy_manifest


def fake_config():
    return {"model_id": "pi05", "policy_id": "test-only-toy", "suite": "toy",
            "policy_factory": "benchmark.remaining_goals.toy:make_policy", "mode": "reactive",
            "execution": {"max_chunk_steps": 1, "random_seed": 17},
            "runtime": {"python_executable": sys.executable},
            "adapter_options": {"suite": "toy", "checkpoint": "test/fake-checkpoint"}}


@pytest.mark.parametrize("field", ["execution", "runtime", "adapter_options"])
def test_static_check_reports_non_object_fields(field):
    config = fake_config()
    config[field] = ["not an object"]
    result = evaluation.check_config(config)
    assert not result["static_configuration_ready"]
    assert any(field in error for error in result["errors"])


def test_static_check_rejects_out_of_numpy_seed_range():
    config = fake_config()
    config["execution"]["random_seed"] = 2**32
    assert any("random_seed" in error for error in evaluation.check_config(config)["errors"])


@pytest.mark.parametrize("key", ["seed", "random_seed"])
def test_adapter_seed_cannot_diverge_from_recorded_execution_seed(key):
    config = fake_config()
    config["adapter_options"][key] = 99
    assert any(key in error for error in evaluation.check_config(config)["errors"])


def test_actual_module_cli_matrix_starts_real_subprocess(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(fake_config()))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"jobs": [{"id": "cpu_fixture", "config": "config.json", "manifest": str(manifest)}]}))
    output = tmp_path / "matrix"
    process = subprocess.run([sys.executable, "-m", "benchmark.remaining_goals.evaluation", "matrix",
                              "--plan", str(plan), "--out", str(output)],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr + (output / "cpu_fixture.log").read_text()
    result = json.loads((output / "cpu_fixture/summary.json").read_text())
    assert result["counts"]["completed"] == 4
    assert result["run_status"] == "finished" and result["release_authorized"] is False
    metadata = json.loads((output / "cpu_fixture/run.json").read_text())
    assert "policy_metadata" in metadata["model_runtime"]
    metadata["model_runtime"]["policy_metadata"]["substituted_repo"] = "another_commit"
    (output / "cpu_fixture/run.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="configuration hash mismatch"):
        cli.rescore(output / "cpu_fixture")


def test_parallel_gpu_overlap_cannot_hide_in_whitespace(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    for name, gpu in (("a", "0"), ("b", " 0 ")):
        config = fake_config()
        config["runtime"]["cuda_visible_devices"] = gpu
        (tmp_path / f"{name}.json").write_text(json.dumps(config))
    plan = {"jobs": [{"id": n, "config": f"{n}.json", "manifest": str(manifest)} for n in ("a", "b")]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="disjoint"):
        evaluation.matrix(path, tmp_path / "output", max_workers=2)
    assert not (tmp_path / "output").exists()


def candidate_fixture(tmp_path, monkeypatch, acceptance=True):
    path = build_toy_manifest(tmp_path / "fixture", scenes=1)
    manifest = load_manifest(path)
    for episode in manifest["episodes"]:
        episode["construction"]["legal"] = False
    manifest["content_hash"] = manifest_hash(manifest)
    path.write_text(json.dumps(manifest))
    replay = tmp_path / "passing-replay.json"
    replay.write_text(json.dumps({"fixture_only": True}))
    monkeypatch.setattr(replay_candidates, "_candidate_pack", lambda p: (deepcopy(manifest), [], {}, {}))
    monkeypatch.setattr(package_audit, "validate_replay_evidence", lambda *args: (set(), {"technical_acceptance": acceptance}))
    return path, manifest, replay


def test_candidate_pilot_never_changes_legal_flags_and_rescores(tmp_path, monkeypatch):
    path, manifest, replay = candidate_fixture(tmp_path, monkeypatch)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="legal"):
        load_manifest(path)
    output = tmp_path / "run"
    result = cli.evaluate(path, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                          policy_config={}, policy_id="test-only-toy", max_chunk_steps=1,
                          candidate_replay=replay)
    assert path.read_bytes() == before
    saved = json.loads((output / "manifest.json").read_text())
    assert saved == manifest and all(e["construction"]["legal"] is False for e in saved["episodes"])
    assert result["evaluation_kind"] == "candidate_pilot" and result["release_authorized"] is False
    assert cli.rescore(output) == result
    saved["episodes"][0]["construction"]["legal"] = True
    saved["content_hash"] = manifest_hash(saved)
    (output / "manifest.json").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="unreviewed"):
        cli.rescore(output)


def test_candidate_replay_failure_does_not_launch_or_create_run(tmp_path, monkeypatch):
    path, _, replay = candidate_fixture(tmp_path, monkeypatch, acceptance=False)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="passing independent replay"):
        cli.evaluate(path, output, policy_factory="nonexistent:factory", policy_config={},
                     policy_id="invalid", max_chunk_steps=1, candidate_replay=replay)
    assert not output.exists()


def test_candidate_gate_rejects_helper_that_mutated_review_flags(tmp_path, monkeypatch):
    path, manifest, replay = candidate_fixture(tmp_path, monkeypatch)
    manifest["episodes"][0]["construction"]["legal"] = True
    manifest["content_hash"] = manifest_hash(manifest)
    monkeypatch.setattr(replay_candidates, "_candidate_pack", lambda p: (manifest, [], {}, {}))
    with pytest.raises(ValueError, match="preserve unreviewed"):
        cli.evaluate(path, tmp_path / "run", policy_factory="nonexistent:factory", policy_config={},
                     policy_id="invalid", max_chunk_steps=1, candidate_replay=replay)


def test_cli_returns_failure_for_episode_runtime_error(tmp_path, monkeypatch):
    from benchmark.remaining_goals import toy
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    def bad_step(self, action):
        raise RuntimeError("fake step failure")
    monkeypatch.setattr(toy.ToyGoalEnv, "step", bad_step)
    code = cli.main(["run", "--manifest", str(manifest), "--out", str(tmp_path / "run"),
                     "--policy-factory", "benchmark.remaining_goals.toy:make_policy",
                     "--policy-id", "test-only-toy", "--max-chunk-steps", "1"])
    assert code == 1
    assert json.loads((tmp_path / "run/summary.json").read_text())["run_status"] == "finished_with_errors"
