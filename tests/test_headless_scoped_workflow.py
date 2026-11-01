"""Real file acceptance plus fake execution; never native/model jobs."""
from copy import deepcopy
import json
import pytest

from benchmark.remaining_goals.headless import scoped_planning, scoped_workflow, workflow
from benchmark.remaining_goals.headless.planning import read_json
from tests.test_headless_scoped_planning import configuration031
from tests.test_headless_scoped_sources import selected, normal_source
from tests.test_headless_source_acceptance import tree_hash
from tests.test_headless_workflow import execution
from tests.test_headless_normal00_runtime import NormalEnv, synthetic_measurements


def attach(config, protocol, entries):
    path = read_json(config)["sources"]
    workflow.write_json(path, {"schema_version": scoped_planning.SOURCES_SCHEMA, "protocol": protocol,
        "expected": scoped_planning.expected_episodes(protocol), "entries": entries}, update=True)


def test_selected_source_isolation_reuse_archive_tamper_and_explicit_continuation(selected, tmp_path, monkeypatch):
    config = configuration031(tmp_path / "config", monkeypatch, "selected-mask10", "missing-two")
    origin = selected[-1]
    entries = [{"task_id": "frypan_stove9", "initial_state_index": i, "origin": deepcopy(origin)} for i in (0, 1)]
    entries[1]["origin"]["replay_sha256"] = "f" * 64
    attach(config, "selected-mask10", entries)
    original = tree_hash(selected[0].parent)
    made, envs = execution(monkeypatch)
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="allow-missing"):
        scoped_workflow.run_batch(config, out)
    assert not out.exists() and not made
    batch = scoped_workflow.run_batch(config, out, allow_missing=True)
    assert batch["episodes"]["frypan_stove9_s000_10"]["status"] == "completed"
    assert batch["episodes"]["frypan_stove9_s001_10"]["status"] == "failed"
    assert len(made) == 1 and made[0].calls == 1 and len(envs) == 1
    assert tree_hash(selected[0].parent) == original
    summary = scoped_workflow.inspect_batch(out)
    assert summary["counts"]["expected"] == 20 and summary["counts"]["successes"] == 1
    assert summary["counts"]["classification_counts"]["missing"] == 19
    with pytest.raises(ValueError, match="continue"):
        scoped_workflow.run_batch(config, out, allow_missing=True)
    entries[1]["origin"] = origin
    attach(config, "selected-mask10", entries)
    scoped_workflow.run_batch(config, out, allow_missing=True, continue_run=True)
    assert sum(p.calls for p in made) == 2
    assert scoped_workflow.inspect_batch(out)["counts"]["successes"] == 2
    first = out / "episodes/frypan_stove9_s000_10"
    raw_before = tree_hash(first)
    scoped_workflow.run_batch(config, out, allow_missing=True, continue_run=True)
    assert tree_hash(first) == raw_before and sum(p.calls for p in made) == 2
    raw = next(first.glob("raw/*.json"))
    raw.write_bytes(raw.read_bytes() + b"tampered")
    summary = scoped_workflow.inspect_batch(out)
    assert summary["counts"]["successes"] == 1 and summary["unverified_task_artifacts"]
    continued = scoped_workflow.run_batch(config, out, allow_missing=True, continue_run=True)
    assert continued["episodes"]["frypan_stove9_s000_10"]["status"] == "artifact_error"
    assert sum(p.calls for p in made) == 2


def test_normal00_initial_only_roundtrip_video_na_and_offline_sources(selected, tmp_path, monkeypatch):
    _, _, origin = normal_source(selected, later_failure=True)
    config = configuration031(tmp_path / "config", monkeypatch, "normal00-control", "missing-two")
    attach(config, "normal00-control", [{"task_id": "frypan_stove9", "initial_state_index": 0, "origin": origin}])
    made, _ = execution(monkeypatch)
    envs = []
    def env(config):
        assert config["protocol"] == "normal00-control"
        value = NormalEnv(); value.close = lambda: None
        envs.append(value)
        return value
    monkeypatch.setattr(workflow, "make_environment", env)
    out = tmp_path / "normal"
    scoped_workflow.run_batch(config, out, allow_missing=True)
    summary = scoped_workflow.inspect_batch(out)
    assert not summary["unverified_task_artifacts"]
    assert summary["counts"]["expected"] == 100 and summary["counts"]["successes"] == 1
    raw = read_json(next(out.glob("episodes/*/raw/*.json")))
    assert raw["goal_regression"] is None and raw["preservation_applicable"] is False
    assert raw["configuration"] == {"horizon": 520, "confirmation_steps": 4, "max_chunk_steps": 8}
    assert raw["video"]["status"] == "saved" and made[0].calls == 1
    assert set(made[0].inputs[0][0]) == {"agentview_image", "robot0_eye_in_hand_image", "proprio"}
    # Make only synthetic original input unavailable; archive remains readable.
    selected[0].write_bytes(b"unavailable")
    summary = scoped_workflow.inspect_batch(out)
    assert summary["counts"]["successes"] == 1 and not summary["unverified_task_artifacts"]


def test_file_only_all_missing_run_does_not_load_policy_or_native(tmp_path, monkeypatch):
    config = configuration031(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("file-only/missing sources must not initialize models or native")
    monkeypatch.setattr(workflow, "make_policy", forbidden)
    monkeypatch.setattr(workflow, "make_environment", forbidden)
    out = tmp_path / "empty"
    scoped_workflow.run_batch(config, out, allow_missing=True)
    summary = scoped_workflow.inspect_batch(out)
    assert summary["counts"]["classification_counts"]["missing"] == 100
    assert summary["attempted_count"] == 0


def test_second_phase_preserves_prior_missing_and_initialization_error_reasons(tmp_path, monkeypatch):
    config = configuration031(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("missing origins must not initialize anything")
    monkeypatch.setattr(workflow, "make_policy", forbidden)
    monkeypatch.setattr(workflow, "make_environment", forbidden)
    prior = tmp_path / "first80"
    batch = scoped_workflow.run_batch(config, prior, allow_missing=True)
    batch["episodes"]["basket_s000_00"] = {"status": "technical_error", "error": "policy initialization unavailable"}
    workflow.write_json(prior / "batch.json", batch, update=True)
    previous = scoped_workflow.inspect_batch(prior)
    config_value = read_json(config); config_value["population"] = "missing-two"
    workflow.write_json(config, config_value, update=True)
    out = tmp_path / "second20"
    scoped_workflow.run_batch(config, out, allow_missing=True, prior_run=prior)
    combined = scoped_workflow.inspect_batch(out)
    for name in ("basket_s000_00", "basket_s001_00"):
        assert combined["task_execution"][name] == previous["task_execution"][name]
        assert next(r["missing_reason"] for r in combined["episodes"] if r["episode_id"] == name) == next(
            r["missing_reason"] for r in previous["episodes"] if r["episode_id"] == name)


def test_one_runtime_failure_does_not_stop_other_fixed_source(selected, tmp_path, monkeypatch):
    config = configuration031(tmp_path / "config", monkeypatch, "selected-mask10", "missing-two")
    attach(config, "selected-mask10", [{"task_id": "frypan_stove9", "initial_state_index": i,
        "origin": selected[-1]} for i in (0, 1)])
    made, _ = execution(monkeypatch, fail_task=0)
    out = tmp_path / "isolated"
    scoped_workflow.run_batch(config, out, allow_missing=True)
    counts = scoped_workflow.inspect_batch(out)["counts"]["classification_counts"]
    assert counts == {"success": 1, "failure": 0, "unknown": 0, "technical_error": 1, "missing": 18}
    assert sum(p.calls for p in made) == 2
    continued = scoped_workflow.run_batch(config, out, allow_missing=True, continue_run=True)
    assert continued["episodes"]["frypan_stove9_s000_10"]["status"] == "technical_pause"
    assert sum(p.calls for p in made) == 2


def test_prior_normal_run_is_explicit_immutable_and_never_reexecutes(selected, tmp_path, monkeypatch):
    _, _, origin = normal_source(selected)
    config = configuration031(tmp_path / "config", monkeypatch, "normal00-control", "missing-two")
    attach(config, "normal00-control", [{"task_id": "frypan_stove9", "initial_state_index": 0, "origin": origin}])
    made, _ = execution(monkeypatch)
    def factory(config):
        value = NormalEnv(); value.close = lambda: None
        return value
    monkeypatch.setattr(workflow, "make_environment", factory)
    prior = tmp_path / "prior"
    scoped_workflow.run_batch(config, prior, allow_missing=True)
    value = read_json(config); value["population"] = "all"
    workflow.write_json(config, value, update=True)
    out = tmp_path / "combined"
    scoped_workflow.run_batch(config, out, allow_missing=True, prior_run=prior)
    assert sum(p.calls for p in made) == 1
    summary = scoped_workflow.inspect_batch(out)
    assert summary["counts"]["expected"] == 100 and summary["counts"]["successes"] == 1
    assert summary["attempted_count"] == 1
    inherited = scoped_workflow._collect(out)[0]
    assert "loaded_model_identity" not in read_json(out / "batch.json")
    assert inherited["loaded_model_identity"] == read_json(prior / "batch.json")["loaded_model_identity"]
    third = tmp_path / "third"
    scoped_workflow.run_batch(config, third, allow_missing=True, prior_run=out)
    assert scoped_workflow._collect(third)[0]["loaded_model_identity"] == inherited["loaded_model_identity"]
    # A later invocation may not claim another actual loaded model even if an
    # intermediate invocation reused all data and never loaded a policy.
    altered = read_json(third / "batch.json")
    altered["loaded_model_identity"] = {"changed_actual_assets": True}
    workflow.write_json(third / "batch.json", altered, update=True)
    with pytest.raises(ValueError, match="actual loaded model differs"):
        scoped_workflow.inspect_batch(third)
    (prior / "batch.json").write_bytes((prior / "batch.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="prior run changed"):
        scoped_workflow.inspect_batch(out)
