"""Independent CPU integration checks; videos are synthetic byte placeholders.

These tests exercise artifact/selection contracts, not an encoder or robot/model
capability. The actual evidence recorder writes real lossless typed observations.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from benchmark.remaining_goals import cli, evaluation, pilot, pilot_evidence, toy
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from benchmark.remaining_goals.schema import load_manifest, write_manifest


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bytes(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in Path(directory).rglob("*") if path.is_file()}


def _bank(tmp_path, *, full_budget=False):
    path = toy.build_toy_manifest(tmp_path / "source", scenes=5)
    if full_budget:
        manifest = load_manifest(path)
        for episode in manifest["episodes"]:
            episode.update(horizon=520, retention_steps=150)
        write_manifest(manifest, path)
    # A construction reference is deliberately different from the live reset.
    np.savez(path.parent / "construction_reference.npz", proprio=np.zeros(8))
    return path


def _config():
    return {"model_id": "pi05", "policy_id": "synthetic-subset-test", "suite": "toy",
            "policy_factory": "benchmark.remaining_goals.toy:make_policy",
            "execution": {"max_chunk_steps": 3, "random_seed": 7},
            "runtime": {"python_executable": sys.executable},
            "adapter_options": {"suite": "toy", "checkpoint": "synthetic-only"}}


def _kwargs(**overrides):
    return {"policy_factory": "fixture:policy", "policy_config": _config(),
            "policy_id": "synthetic-subset-test", "max_chunk_steps": 3,
            "masks": ["10", "01", "11"], "video_config": {"enabled": True}, **overrides}


def _install_fakes(monkeypatch, *, failure=None, prediction="idle"):
    log = {"factory": [], "resets": [], "steps": [], "queries": [], "policy_resets": 0,
           "env_closed": 0, "policy_closed": 0, "recorders_closed": 0, "raw_observations": []}
    native_env = toy.ToyGoalEnv

    class Environment(native_env):
        def __init__(self, config):
            if failure == "env_init":
                raise RuntimeError("synthetic env initialization failure")
            super().__init__(config)

        def _observation(self):
            obs = super()._observation()
            obs["proprio"][0] = 31  # distinguish live reset from construction reference
            log["raw_observations"].append(obs)
            return obs

        def reset(self, episode):
            log["resets"].append(deepcopy(episode))
            log["current"] = episode["episode_id"]
            if failure == "env_reset":
                raise RuntimeError("synthetic restore failure")
            obs = super().reset(episode)
            if failure == "invalid_initial":
                self.values[:] = 0
            return obs

        def step(self, action):
            if failure == "env_step":
                raise RuntimeError("synthetic step failure")
            log["steps"].append((log["current"], np.asarray(action).copy()))
            return super().step(action)

        def close(self):
            log["env_closed"] += 1

    class Policy:
        def reset(self):
            log["policy_resets"] += 1
            if failure == "policy_reset":
                raise RuntimeError("synthetic policy reset failure")
            self.sequence = 0

        def predict(self, observation, instruction):
            self.sequence += 1
            log["queries"].append({"episode_id": log["current"], "sequence": self.sequence,
                                   "observation": deepcopy(observation), "instruction": instruction})
            if failure == "policy_predict" or (failure == "predict_after_chunk" and self.sequence == 2):
                raise RuntimeError("synthetic predict failure")
            assert set(observation) == {"images", "proprio"}
            assert set(observation["images"]) == {"front"}
            # Preprocessing may mutate its copies; evaluator/reset buffers must survive.
            observation["proprio"][0] = -99
            if prediction == "stop":
                return None
            return np.zeros((3, 7))

        def close(self):
            log["policy_closed"] += 1

    def factory(config):
        log["factory"].append(deepcopy(config))
        if failure == "model_load":
            raise RuntimeError("synthetic load failure")
        return Policy()

    class Recorder:
        def __init__(self, path, config, **kwargs):
            if failure == "video_setup":
                raise RuntimeError("synthetic video initialization failure")
            self.path, self.config, self.steps = Path(path), config, []

        def capture(self, observation, *, step):
            if failure == "video_capture":
                raise RuntimeError("synthetic encoder failure")
            self.steps.append(step)

        def close(self):
            log["recorders_closed"] += 1
            if failure != "video_missing":
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_bytes(b"SYNTHETIC VIDEO PLACEHOLDER; NOT AN ENCODED MOVIE")
            return {"status": "saved", "path": self.path.name, "frames": len(self.steps),
                    "frame_steps": self.steps, "fps": 20.0, "stride": 1,
                    "camera": "agentview", "synthetic": True}

    monkeypatch.setattr(toy, "ToyGoalEnv", Environment)
    monkeypatch.setattr(cli, "_factory", lambda _: factory)
    monkeypatch.setattr(pilot, "EpisodeVideoRecorder", Recorder)
    if failure == "actual_step0":
        def fail_initial(self, observation):
            raise OSError("synthetic actual step0 write failure")
        monkeypatch.setattr(pilot_evidence.EpisodeEvidence, "capture_initial", fail_initial)
    return log


@pytest.mark.parametrize("mode,masks,expected", [
    ("original", ["10", "01", "11"], 15),
    ("oracle-remaining-initial", ["10", "01"], 10),
])
def test_dry_plan_has_exact_ids_budgets_and_loads_no_runtime(tmp_path, monkeypatch, mode, masks, expected):
    path = _bank(tmp_path, full_budget=True)
    original = _bytes(path.parent)

    def forbidden(*args, **kwargs):
        raise AssertionError("dry-plan must not construct a model or simulator")

    monkeypatch.setattr(cli, "_factory", forbidden)
    monkeypatch.setattr(toy, "ToyGoalEnv", forbidden)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(_config()), encoding="utf-8")
    output = tmp_path / "plan.json"
    plan = evaluation.pilot(config_path, path, output, masks=masks, instruction_mode=mode,
                            dry=True, video_config={"enabled": True})

    assert plan["expected"] == expected and plan["source_expected"] == 20
    assert plan["weights_loaded"] is False and plan["simulation_created"] is False
    assert plan["planned_model_loads"] == 1 and plan["planned_policy_resets"] == expected
    assert plan["policy_config"]["execution"]["random_seed"] == 7
    assert plan["technical_failure_policy"] == "pause_remaining_selected"
    manifest = load_manifest(path)
    wanted = [episode for episode in manifest["episodes"] if episode["episode_id"][-2:] in masks]
    assert plan["execution_selection"]["selected_ids"] == [e["episode_id"] for e in wanted]
    assert {row["initial_state_index"] for row in plan["episodes"]} == set(range(5))
    for row in plan["episodes"]:
        assert row["seed"] == row["initial_state_index"]
        assert (row["horizon"], row["retention_steps"]) == (520, 150)
        assert row["scheduled_steps"] == (150 if row["mask"] == "11" else 670)
        assert row["original_instruction"] == "complete A and B"
        assert row["effective_instruction"] == ("complete A and B" if mode == "original"
                                                  else "complete B" if row["mask"] == "10" else "complete A")
    assert _bytes(path.parent) == original
    with pytest.raises(FileExistsError):
        evaluation.pilot(config_path, path, output, masks=masks, instruction_mode=mode,
                         dry=True, video_config={"enabled": True})


@pytest.mark.parametrize("masks", [["1"], ["10", "10"], [10], "10", [], ["12"], ["111"]])
def test_invalid_mask_selector_rejected_before_runtime_or_output(tmp_path, monkeypatch, masks):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch)
    with pytest.raises(ValueError):
        pilot.evaluate_subset(path, tmp_path / "run", **_kwargs(masks=masks))
    assert not log["factory"] and not (tmp_path / "run").exists()


def test_complete_source_validation_includes_unselected_00(tmp_path, monkeypatch):
    path = _bank(tmp_path)
    manifest = load_manifest(path)
    (path.parent / manifest["episodes"][0]["state_path"]).write_bytes(b"tampered unselected state")
    log = _install_fakes(monkeypatch)
    with pytest.raises(ValueError):
        pilot.evaluate_subset(path, tmp_path / "run", **_kwargs())
    assert not log["factory"] and not (tmp_path / "run").exists()


@pytest.mark.parametrize("mode,masks,expected", [
    ("original", ["10", "01", "11"], 15),
    ("oracle-remaining-initial", ["10", "01"], 10),
])
def test_complete_subset_preserves_source_and_integrates_saved_run_and_uir(
        tmp_path, monkeypatch, mode, masks, expected):
    path = _bank(tmp_path)
    before_source = _bytes(path.parent)
    log = _install_fakes(monkeypatch)
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs(masks=masks, instruction_mode=mode))
    metadata, manifest, results = cli.read_run(output)
    selected = metadata["execution_selection"]["selected_ids"]

    assert summary["run_status"] == "finished"
    assert summary["counts"]["expected"] == summary["counts"]["completed"] == expected
    assert summary["counts"]["missing"] == summary["counts"]["errors"] == 0
    assert summary["not_selected"]["count"] == 20 - expected
    assert metadata["runtime_counts"] == {"model_load_attempts": 1, "model_loads_completed": 1,
                                           "policy_reset_attempts": expected, "policy_resets_completed": expected}
    assert metadata["attempted_ids"] == selected
    assert [episode["episode_id"] for episode in log["resets"]] == selected
    assert all(not identifier.endswith("00") for identifier in selected)
    assert len(log["factory"]) == 1 and log["factory"][0] == _config()
    assert log["env_closed"] == log["policy_closed"] == 1
    assert log["recorders_closed"] == expected
    assert len(manifest["episodes"]) == 20
    assert (output / "manifest.json").read_bytes() == path.read_bytes()
    source_by_id = {episode["episode_id"]: episode for episode in manifest["episodes"]}
    query_by_id = {}
    for query in log["queries"]:
        query_by_id.setdefault(query["episode_id"], []).append(query)
        assert set(query["observation"]) == {"images", "proprio"}
        assert query["instruction"] == ("complete A and B" if mode == "original" else
                                         "complete B" if query["episode_id"].endswith("10") else "complete A")
    for result in results:
        identifier = result["episode_id"]
        episode = source_by_id[identifier]
        assert result["instruction"] == episode["instruction"] == "complete A and B"
        assert next(e for e in log["resets"] if e["episode_id"] == identifier) == episode
        assert result["n_steps"] == (3 if identifier.endswith("11") else 7)
        assert result["metrics"]["joint_success"] is identifier.endswith("11")
        assert query_by_id[identifier][0]["sequence"] == 1
        evidence = _json(output / result["execution_evidence"]["path"])
        archive = load_observation_artifact(output, result["execution_evidence"]["initial_observation"])
        assert archive["proprio"][0] == 31
        np.testing.assert_array_equal(archive["proprio"], query_by_id[identifier][0]["observation"]["proprio"])
        assert evidence["initial_observation_typed_sha256"] == pilot_evidence.observation_sha256(archive)
        assert [q["observation_step"] for q in evidence["queries"]] == ([0] if identifier.endswith("11") else [0, 3, 6])
        assert len(evidence["executed_actions"]) == result["n_steps"]
        if not identifier.endswith("11"):
            assert evidence["queries"][-1]["unexecuted_accepted_actions"] == 2
    assert all(obs["proprio"][0] == 31 for obs in log["raw_observations"])
    assert len(log["steps"]) == sum(result["n_steps"] for result in results)
    assert _bytes(path.parent) == before_source
    before_run = _bytes(output)
    assert cli.rescore(output) == summary
    assert _bytes(output) == before_run
    template_path = tmp_path / "annotations.json"
    template = cli.annotation_template(output, template_path)
    assert {row["episode_id"] for row in template["annotations"]} == set(selected)
    assert all(row["unnecessary_intervention"] is None for row in template["annotations"])
    assert template["selection_sha256"] == metadata["execution_selection"]["selection_sha256"]
    report = cli.derived_report(output, tmp_path / "derived", annotations_path=template_path)
    assert report["summary"]["counts"]["expected"] == expected
    assert {row["mask"] for row in report["display"]["main"]} == set(masks)
    assert all(row["unnecessary_intervention_rate"] is None for row in report["display"]["main"])
    assert report["display"]["diagnostic"] is (mode != "original")
    assert _bytes(output) == before_run and _bytes(path.parent) == before_source
    with pytest.raises(FileExistsError):
        pilot.evaluate_subset(path, output, **_kwargs(masks=masks, instruction_mode=mode))
    assert len(log["factory"]) == 1


@pytest.mark.parametrize("failure", ["model_load", "env_init", "env_reset", "invalid_initial",
                                      "policy_reset", "policy_predict", "env_step", "video_setup",
                                      "video_capture", "video_missing", "actual_step0"])
def test_technical_fault_pauses_with_fixed_expected_and_remaining_missing(tmp_path, monkeypatch, failure):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch, failure=failure)
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs())

    assert summary["run_status"] == "technical_paused"
    assert summary["counts"]["expected"] == 15 and summary["counts"]["missing"] == 14
    assert len(summary["missing_episode_ids"]) == 14
    metadata, _, results = cli.read_run(output)
    assert metadata["attempted_ids"] == ["toy_s000_10"]
    assert metadata["stop_reason"]["episode_id"] == "toy_s000_10"
    assert len(results) == 1 and results[0]["episode_id"] == "toy_s000_10"
    assert len(log["resets"]) <= 1 and len(log["factory"]) == 1
    assert log["policy_closed"] == (0 if failure == "model_load" else 1)
    assert log["env_closed"] == (0 if failure in ("model_load", "env_init") else 1)
    assert results[0]["status"] == ("invalid_initial_state" if failure == "invalid_initial" else
                                    "completed" if failure.startswith("video_") and failure != "video_setup" else "runtime_error")
    assert cli.rescore(output) == summary
    template = cli.annotation_template(output, tmp_path / "annotations.json")
    assert len(template["annotations"]) == 15
    assert sum(row["context"]["result_status"] == "missing" for row in template["annotations"]) == 14


def test_stop_is_retained_and_no_query_or_step_is_added_for_evidence(tmp_path, monkeypatch):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch, prediction="stop")
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs())
    _, _, results = cli.read_run(output)

    assert summary["counts"]["completed"] == 15
    assert len(log["queries"]) == log["policy_resets"] == len(log["resets"]) == 15
    assert len(log["steps"]) == 5 * (7 + 7 + 3)
    for result in results:
        evidence = _json(output / result["execution_evidence"]["path"])
        assert result["stop_step"] == 0 and result["policy_queries"] == 1
        assert evidence["queries"][0]["response"] == "stop"
        assert evidence["queries"][0]["execution_interval"] == [1, result["n_steps"]]
        assert all(action["stopped"] for action in evidence["executed_actions"])


@pytest.mark.parametrize("tamper", ["selector", "source_bytes", "effective_instruction", "evidence", "step0"])
def test_read_run_rejects_selection_source_instruction_and_actual_evidence_tampering(tmp_path, monkeypatch, tamper):
    path = _bank(tmp_path)
    _install_fakes(monkeypatch, prediction="stop")
    output = tmp_path / "run"
    pilot.evaluate_subset(path, output, **_kwargs())
    record = _json(output / "episodes/000000.json")
    if tamper == "selector":
        metadata = _json(output / "run.json")
        metadata["execution_selection"]["selected_ids"].pop()
        (output / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    elif tamper == "source_bytes":
        with (output / "manifest.json").open("ab") as file:
            file.write(b"\n ")
    elif tamper == "effective_instruction":
        record["effective_instruction"] = "another instruction"
        (output / "episodes/000000.json").write_text(json.dumps(record), encoding="utf-8")
    elif tamper == "evidence":
        with (output / record["execution_evidence"]["path"]).open("ab") as file:
            file.write(b" ")
    else:
        with (output / record["execution_evidence"]["initial_observation"]["path"]).open("ab") as file:
            file.write(b"tampered")
    before = _bytes(output)
    with pytest.raises(ValueError):
        cli.read_run(output)
    assert _bytes(output) == before


def test_oracle_11_and_missing_required_video_rejected_before_loading(tmp_path, monkeypatch):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch)
    for options in [{"instruction_mode": "oracle-remaining-initial"}, {"video_config": {"enabled": False}}]:
        with pytest.raises(ValueError):
            pilot.evaluate_subset(path, tmp_path / "run", **_kwargs(**options))
    assert not log["factory"] and not (tmp_path / "run").exists()


def test_later_predict_error_preserves_real_chunk_prefix_and_pauses(tmp_path, monkeypatch):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch, failure="predict_after_chunk")
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs())
    metadata, _, results = cli.read_run(output)
    result = results[0]
    evidence = _json(output / result["execution_evidence"]["path"])

    assert summary["counts"]["expected"] == 15 and summary["counts"]["missing"] == 14
    assert result["n_steps"] == len(log["steps"]) == 3
    assert result["policy_queries"] == len(log["queries"]) == 2
    assert result["error_phase"] == metadata["stop_reason"]["phase"] == "policy_predict"
    assert [row["observation_step"] for row in evidence["queries"]] == [0, 3]
    assert evidence["queries"][0]["execution_interval"] == [1, 3]
    assert evidence["queries"][1]["response"] == "error"
    assert evidence["queries"][1]["execution_interval"] is None
    assert result["video"]["frame_steps"] == [0, 1, 2, 3]


def test_evidence_setup_error_is_saved_as_one_failed_attempt_and_recorder_closed(tmp_path, monkeypatch):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch)

    def fail_evidence(*args, **kwargs):
        raise OSError("synthetic evidence setup failure")

    monkeypatch.setattr(pilot_evidence, "EpisodeEvidence", fail_evidence)
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs())

    assert summary["run_status"] == "technical_paused"
    assert summary["counts"]["expected"] == 15
    assert summary["counts"]["runtime_error"] == 1
    assert summary["counts"]["missing"] == 14
    metadata, _, results = cli.read_run(output)
    assert metadata["attempted_ids"] == ["toy_s000_10"] and len(results) == 1
    assert not log["resets"] and not log["queries"]
    assert log["recorders_closed"] == log["env_closed"] == log["policy_closed"] == 1


@pytest.mark.parametrize("bad_close", [[], {"status": "saved", "frames": np.array([1])}],
                         ids=["non-object", "non-json-array"])
def test_evidence_setup_and_malformed_video_close_keep_error_record(tmp_path, monkeypatch, bad_close):
    path = _bank(tmp_path)
    log = _install_fakes(monkeypatch)
    regular_recorder = pilot.EpisodeVideoRecorder

    class MalformedClose(regular_recorder):
        def close(self):
            super().close()
            return deepcopy(bad_close)

    def fail_evidence(*args, **kwargs):
        raise OSError("synthetic evidence setup failure")

    monkeypatch.setattr(pilot, "EpisodeVideoRecorder", MalformedClose)
    monkeypatch.setattr(pilot_evidence, "EpisodeEvidence", fail_evidence)
    output = tmp_path / "run"
    summary = pilot.evaluate_subset(path, output, **_kwargs())
    metadata, _, results = cli.read_run(output)

    assert summary["run_status"] == "technical_paused"
    assert summary["counts"]["runtime_error"] == 1 and summary["counts"]["missing"] == 14
    assert summary["counts"]["expected"] == 15
    assert metadata["attempted_ids"] == ["toy_s000_10"]
    assert metadata["stop_reason"]["phase"] == results[0]["error_phase"] == "evidence_setup"
    assert type(results[0]["video"]) is dict
    assert results[0]["video"]["status"] == "video_error"
    assert results[0]["video"]["error"]
    assert not log["resets"] and not log["queries"]
    assert log["recorders_closed"] == log["env_closed"] == log["policy_closed"] == 1
