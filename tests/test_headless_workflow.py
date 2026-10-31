"""File and fake execution integration; no native environment/research model."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmark.remaining_goals.headless import planning, workflow
from benchmark.remaining_goals import pilot
from benchmark.remaining_goals.adapters import openvla_oft
from tests.test_remaining_oft_transfer import configs, fake_load
from tests.test_headless_runner import (Env, Policy, Video, episode,
                                       synthetic_measurement_validator)


def configuration(tmp_path, monkeypatch):
    from benchmark.remaining_goals import cli
    # Stable fixture revision while other test modules/source files may be
    # authored concurrently; production still fingerprints the entire harness.
    monkeypatch.setattr(cli, "_source_hash", lambda: "d" * 64)
    primary, _ = configs(tmp_path)
    runtime = tmp_path / "runtime.json"
    workflow.write_json(runtime, primary)
    sources = {}
    for task in planning.COMMON_TEN_TASKS:
        directory = tmp_path / "sources" / task
        rows = [episode(episode_id=f"{task}_s{index:03d}_{mask}", task_id=task,
                        suite=planning.TASKS[task]["suite"], task_name=planning.TASKS[task]["name"],
                        goal_specs=planning.TASKS[task]["goals"], initial_state_index=index, seed=index,
                        initial_mask=[mask[0] == "1", mask[1] == "1"])
                for index in range(10) for mask in ("00", "10", "01", "11")]
        workflow.write_json(directory / "manifest.json", {"environment": "libero", "episodes": rows})
        workflow.write_json(directory / "replay.json", {"synthetic": True})
        sources[task] = {"manifest": str(directory / "manifest.json"), "candidate_replay": str(directory / "replay.json")}
    def source(manifest, replay):
        raw, replay_raw = Path(manifest).read_bytes(), Path(replay).read_bytes()
        return json.loads(raw), raw, replay_raw, {"synthetic": True, "summary": {"accepted": True}}
    # Independent native state/replay validation already has its own tests.
    # This fixture replaces only the source-bank reader, not headless planning,
    # evidence binding, model metadata validation, execution, video or summary.
    monkeypatch.setattr(pilot, "_source", source)
    path = tmp_path / "batch.json"
    from benchmark.remaining_goals.adapters.oft_transfer import TRANSFER
    workflow.write_json(path, {"schema_version": planning.CONFIG_SCHEMA, "runtime_config": str(runtime),
                              "extension_transfer": TRANSFER, "sources": sources})
    return path


def execution(monkeypatch, *, fail_task=None, changed_model_task=None, interrupt=False):
    made, environments = [], []
    monkeypatch.setattr(openvla_oft, "_load_upstream", fake_load)
    def factory(config):
        original = openvla_oft.make_policy(config)
        metadata = deepcopy(original.metadata)
        original.close()
        value = Policy()
        value.provenance = {"policy_metadata": metadata, "checkpoint_bytes_verified": False}
        value.close = lambda: None
        if changed_model_task is not None and len(made) == changed_model_task:
            metadata["normalization_statistics_sha256"] = "f" * 64
        made.append(value)
        return value
    def environment(config):
        value = Env(fail=("interrupt" if interrupt else "step", 1) if len(environments) == fail_task else None)
        value.close = lambda: None
        environments.append(value)
        return value
    class Recorder(Video):
        def __init__(self, path):
            super().__init__(); self.path = path
        def close(self):
            result = super().close()
            self.path.parent.mkdir(exist_ok=True)
            self.path.write_bytes(b"synthetic video: " + repr(result["frame_steps"]).encode())
            return result
    monkeypatch.setattr(workflow, "make_policy", factory)
    monkeypatch.setattr(workflow, "make_environment", environment)
    monkeypatch.setattr(workflow, "make_recorder", lambda path, ep: Recorder(path))
    return made, environments


def test_exact_hundred_two_track_execution_and_read_only_resume(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    made, environments = execution(monkeypatch)
    out = tmp_path / "run"
    workflow.run_batch(path, out, track="primary")
    summary = workflow.inspect_batch(out)
    assert summary["counts"]["expected"] == 100
    assert summary["counts"]["classification_counts"] == {"success": 60, "failure": 0, "unknown": 0, "technical_error": 0, "missing": 40}
    workflow.run_batch(path, out, track="extension")
    summary = workflow.inspect_batch(out, tmp_path / "derived")
    assert summary["counts"]["successes"] == 100 and not summary["unverified_task_artifacts"]
    assert sum(model.calls for model in made) == 100
    assert sum(model.resets for model in made) == 100
    assert sum(len(env.actions) for env in environments) == 600
    assert [track["expected"] for track in summary["tracks"]] == [60, 40]
    assert all(row["n_steps"] == 6 and row["path_length_m"] == pytest.approx(.6) for row in summary["episodes"])
    assert len(list(out.glob("tasks/*/videos/*.mp4"))) == 100
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("tasks/**/*") if p.is_file()}
    workflow.run_batch(path, out)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("tasks/**/*") if p.is_file()}
    assert before == after and len(made) == 10
    assert (tmp_path / "derived/report.md").is_file() and (tmp_path / "derived/episodes.csv").is_file()
    with pytest.raises(ValueError, match="outside"):
        workflow.inspect_batch(out, out / "derived")


def test_task_failure_pauses_only_that_task_and_never_retries(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    made, _ = execution(monkeypatch, fail_task=0)
    out = tmp_path / "run"
    workflow.run_batch(path, out)
    summary = workflow.inspect_batch(out)
    assert summary["counts"]["classification_counts"] == {"success": 90, "failure": 0, "unknown": 0, "technical_error": 1, "missing": 9}
    assert not summary["unverified_task_artifacts"]
    assert sum(model.calls for model in made) == 91
    workflow.run_batch(path, out)
    assert len(made) == 10 and sum(model.calls for model in made) == 91
    assert "synthetic control failure" in json.dumps(summary)


def test_unready_sources_keep_fixed_denominator_can_be_prepared_later(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    made, _ = execution(monkeypatch)
    original = planning.source_plan
    monkeypatch.setattr(planning, "source_plan", lambda task, source: (_ for _ in ()).throw(ValueError("unready")) if task == "basket" else original(task, source))
    out = tmp_path / "run"
    workflow.run_batch(path, out)
    summary = workflow.inspect_batch(out)
    assert summary["counts"]["successes"] == 90 and summary["counts"]["classification_counts"]["missing"] == 10
    assert not (out / "tasks/basket").exists()
    monkeypatch.setattr(planning, "source_plan", original)
    workflow.run_batch(path, out)
    assert workflow.inspect_batch(out)["counts"]["successes"] == 100 and len(made) == 10


def test_changed_actual_statistics_rejected_before_task_actions(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    made, environments = execution(monkeypatch, changed_model_task=1)
    out = tmp_path / "run"
    workflow.run_batch(path, out, track="primary")
    assert made[1].calls == made[1].resets == 0 and len(environments) == 5
    report = workflow.inspect_batch(out)
    assert report["counts"]["successes"] == 50
    assert "model/source/statistics changed" in json.dumps(report)


@pytest.mark.parametrize("artifact", ["video", "raw", "manifest", "query", "runtime"])
def test_offline_tampering_is_visible_and_completed_task_not_reexecuted(tmp_path, monkeypatch, artifact):
    path = configuration(tmp_path, monkeypatch)
    made, _ = execution(monkeypatch)
    out = tmp_path / "run"
    workflow.run_batch(path, out, track="primary")
    directory = out / "tasks/basket"
    if artifact == "runtime":
        meta = planning.read_json(directory / "task_run.json")
        meta["runtime_config"]["policy_id"] += "-changed"
        workflow.write_json(directory / "task_run.json", meta, update=True)
    else:
        patterns = {"video": "videos/*.mp4", "raw": "raw/*.json", "manifest": "source/manifest.json", "query": "evidence/*/query*.npz"}
        target = next(directory.glob(patterns[artifact]))
        target.write_bytes(target.read_bytes() + b"tampered")
    report = workflow.inspect_batch(out)
    assert report["unverified_task_artifacts"][0]["task_id"] == "basket"
    assert report["counts"]["successes"] == (50 if artifact in {"manifest", "runtime"} else 59)
    workflow.run_batch(path, out, track="primary")
    assert len(made) == 6


def test_user_interruption_saves_partial_result_and_stops_entire_batch(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    made, _ = execution(monkeypatch, fail_task=0, interrupt=True)
    out = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        workflow.run_batch(path, out)
    assert len(made) == 1 and made[0].calls == 1
    summary = workflow.inspect_batch(out)
    assert summary["counts"]["classification_counts"]["technical_error"] == 1
    assert summary["counts"]["classification_counts"]["missing"] == 99
    assert not summary["unverified_task_artifacts"]


def test_recording_failure_retains_technical_record_and_prior_valid_episodes(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.evidence import HeadlessEvidence
    path = configuration(tmp_path, monkeypatch)
    made, _ = execution(monkeypatch)
    original = HeadlessEvidence.capture_query_input
    def capture(self, observation, **kwargs):
        if self.identity["episode_id"] == "basket_s001_10":
            raise OSError("synthetic query recording failure")
        return original(self, observation, **kwargs)
    monkeypatch.setattr(HeadlessEvidence, "capture_query_input", capture)
    out = tmp_path / "run"
    workflow.run_batch(path, out, track="primary")
    summary = workflow.inspect_batch(out)
    assert summary["counts"]["classification_counts"] == {"success": 51, "failure": 0, "unknown": 0, "technical_error": 1, "missing": 48}
    assert not summary["unverified_task_artifacts"]
    metadata = planning.read_json(out / "tasks/basket/task_run.json")
    assert metadata["results"][0]["validation"] == "verified"
    assert metadata["results"][1]["validation"] == "partial_evidence"
    workflow.run_batch(path, out, track="primary")
    assert len(made) == 6


def test_fixed_plan_and_source_selection_reject_missing_or_substituted_index(tmp_path, monkeypatch):
    path = configuration(tmp_path, monkeypatch)
    config, _ = planning.load_config(path)
    budget = planning.budget_plan()
    assert len(budget["episodes"]) == 100 and budget["maximum_policy_steps"] == 52000
    assert sum(row["development_source"] for row in budget["episodes"]) == 5
    source = config["sources"]["basket"]
    manifest = planning.read_json(source["manifest"])
    for row in manifest["episodes"]:
        if row["initial_state_index"] == 9: row["initial_state_index"] = 10
    workflow.write_json(source["manifest"], manifest, update=True)
    plan = planning.dry_plan(path)
    assert plan["ready_episodes"] == 90 and plan["tasks"][0]["status"] == "preparation_error"
    assert planning.validate_plan(plan)["expected"] == budget["episodes"]


def test_budget_and_help_import_no_native_or_model():
    code = '''import builtins, sys
original = builtins.__import__
def guard(name,*args,**kwargs):
    if name.split('.')[0] in {'torch','transformers','libero','robosuite','mujoco','mujoco_py'}: raise AssertionError(name)
    return original(name,*args,**kwargs)
builtins.__import__=guard
from benchmark.remaining_goals.headless.cli import main
raise SystemExit(main(sys.argv[1:]))
'''
    for args in (["--help"], ["budget-plan"]):
        result = subprocess.run([sys.executable, "-B", "-c", code, *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
