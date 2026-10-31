"""Offline rescore integration with synthetic recorded geometry, never native."""
from copy import deepcopy
import builtins
import csv
import hashlib
import json

import pytest

from benchmark.remaining_goals.headless import environment, planning, workflow
from tests.test_headless_runner import observation
from tests.test_headless_workflow import configuration, execution
from tests.test_headless_support_versions import make_legacy_observer, numeric_native, TOP_Z as TABLE_Z


def tree_hash(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


class LegacyRecordedEnvironment:
    """Produce complete legacy evidence from native-shaped arrays, not physics."""
    def __init__(self):
        self.steps = 0

    def reset(self, episode):
        self.episode, self.steps = deepcopy(episode), 0
        native = self.native = numeric_native("basket")
        self.observer = make_legacy_observer(native, "basket")
        self.observer.static["source_reset_model_xml_sha256"] = episode["model_xml_sha256"]
        static = self.observer.static
        static["static_sha256"] = environment.geo.canonical_hash({key: value for key, value in static.items()
                                                               if key != "static_sha256"})
        environment.validate_measurement_static(static, episode=episode)
        assert static["schema_version"] == environment.LEGACY_SCHEMA
        assert static["initial_objects"]["basket_1"]["table_support"]["eligible"] is None
        return observation(0)

    def measurement_static(self):
        return self.observer.measurement_static()

    def evaluator_state(self):
        complete = self.episode["initial_state_index"] != 3 and self.steps >= 2
        return self.observer.evaluator_state([True, complete])

    def step(self, action):
        self.steps += 1
        index = self.episode["initial_state_index"]
        if index == 1:
            # A whole collision box ends 3cm below the table, beyond the
            # unchanged 2cm threshold, for five consecutive recorded frames.
            self.native.move("basket_1", [.1, 0., TABLE_Z - .04])
        elif index == 2:
            self.native.move("distractor_1", [.1, 0., TABLE_Z + .05])
            self.native.grasped.add("distractor_1_geom")
        elif index == 4:
            # Whole-group upper bound is only 1.9cm below the plane: no drop.
            self.native.move("basket_1", [.1 + self.steps * .001, 0., TABLE_Z - .029])
        self.native.sim.data.site_xpos[0] = [self.steps * .1, 0., 0.]
        return observation(self.steps)

    def close(self):
        pass


def make_old_batch(tmp_path, monkeypatch):
    config_path = configuration(tmp_path, monkeypatch)
    original_source = planning.source_plan
    def basket_only(task, source, **kwargs):
        if task != "basket":
            raise ValueError("synthetic not-yet-prepared source")
        return original_source(task, source, **kwargs)
    monkeypatch.setattr(planning, "source_plan", basket_only)
    execution(monkeypatch)
    monkeypatch.setattr(workflow, "make_environment", lambda config: LegacyRecordedEnvironment())
    monkeypatch.setattr(environment, "_callback_status", lambda: "absent")
    # A CPU fixture's short horizon makes the unchanged incomplete-task branch
    # testable without generating 520 synthetic geometry frames. Production
    # defaults and the fixed 100-entry source population are unchanged.
    monkeypatch.setattr(workflow, "HORIZON", 8)
    output = tmp_path / "original_batch"
    workflow.run_batch(config_path, output)
    return output


def test_file_only_rescore_preserves_raw_and_legacy_reader_with_fixed_population(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import rescore

    original = make_old_batch(tmp_path, monkeypatch)
    before_summary = workflow.inspect_batch(original)
    old_counts = {"success": 0, "failure": 2, "unknown": 8, "technical_error": 0, "missing": 90}
    assert before_summary["counts"]["classification_counts"] == old_counts
    assert not before_summary["unverified_task_artifacts"]
    original_hashes = tree_hash(original)
    source_hashes = tree_hash(tmp_path / "sources")
    config_bytes = (tmp_path / "batch.json").read_bytes()
    raw = {row["episode_id"]: row for path in (original / "tasks/basket/raw").glob("*.json")
           for row in [json.loads(path.read_text(encoding="utf-8"))]}
    assert len(raw) == 10

    def forbidden(*args, **kwargs):
        pytest.fail("offline rescoring must not initialize an environment, policy or recorder")
    for name in ("make_environment", "make_policy", "make_recorder"):
        monkeypatch.setattr(workflow, name, forbidden)
    original_import = builtins.__import__
    def file_only_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "transformers", "libero", "robosuite", "mujoco", "mujoco_py"}, name
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", file_only_import)

    output = tmp_path / "derived"
    summary = rescore.rescore_batch(original, output)
    assert summary["schema_version"] == rescore.SCHEMA
    assert summary["derived_only"] is True and summary["new_execution"] is False
    assert not summary["unverified_task_artifacts"]
    assert summary["old_summary"]["counts"]["classification_counts"] == old_counts
    assert summary["new_summary"]["counts"]["classification_counts"] == {
        "success": 7, "failure": 3, "unknown": 0, "technical_error": 0, "missing": 90}
    assert len(summary["expected"]) == len(summary["new_summary"]["episodes"]) == 100
    assert sorted(row["expected"] for row in summary["new_summary"]["tracks"]) == [40, 60]
    coverage = summary["comparison"]["new"]
    assert (coverage["planned"], coverage["recorded"], coverage["executed"]) == (100, 10, 10)
    assert coverage["success_among_executed"] == {"numerator": 7, "denominator": 10, "percent": 70.}
    assert coverage["success_over_plan"] == {"numerator": 7, "denominator": 100, "percent": 7.}

    artifacts = {}
    assert len(summary["derived_episodes"]) == 10
    for reference in summary["derived_episodes"]:
        path = output / reference["path"]
        assert planning.file_sha(path) == reference["sha256"]
        derived = artifacts[reference["episode_id"]] = planning.read_json(path)
        previous = raw[reference["episode_id"]]
        assert derived["schema_version"] == rescore.EPISODE_SCHEMA
        assert derived["derived_only"] is True and derived["new_execution"] is False
        assert derived["source"]["raw_sha256"] == planning.file_sha(original / derived["source"]["raw_path"])
        assert derived["source"]["original_identity_sha256"] == previous["identity_sha256"]
        assert derived["source"]["original_measurement_static_sha256"] == previous["measurement_static"]["static_sha256"]
        assert derived["source"]["original_execution_evidence"] == previous["execution_evidence"]
        assert derived["preserved"] == {key: previous[key] for key in derived["preserved"]}
        assert derived["preserved"]["configuration"]["confirmation_steps"] == 4
        assert derived["preserved_actions_sha256"] == planning.canonical_hash(previous["executed_actions"])
        assert derived["preserved_queries_sha256"] == planning.canonical_hash(previous["queries"])
        assert derived["old"]["path_length_m"] == derived["new"]["path_length_m"] == previous["path_length_m"]
        assert derived["old"]["n_steps"] == derived["new"]["n_steps"] == previous["n_steps"]
        assert derived["measurement_static"]["schema_version"] == environment.SCHEMA
        assert derived["measurement_static"]["support_rule"] == environment.SUPPORT_RULE
        assert derived["measurement_static"]["initial_objects"]["basket_1"]["table_support"]["eligible"] is True
        assert previous["measurement_static"]["schema_version"] == environment.LEGACY_SCHEMA
        assert previous["measurement_static"]["initial_objects"]["basket_1"]["table_support"]["eligible"] is None
        assert len(derived["table_drop_trace"]) == previous["n_steps"] + 1
        assert all(row["evidence"]["basket_1"]["minimum_drop_m"] == .02 for row in derived["table_drop_trace"])

    dropped = artifacts["basket_s001_10"]
    assert dropped["old"]["classification"] == "unknown" and dropped["new"]["classification"] == "failure"
    assert dropped["new"]["failure_reasons"] == ["table_drop"]
    assert dropped["confirmed_events"] == [{"event": "table_drop", "object": "basket_1",
                                             "start_step": 1, "confirmation_step": 5}]
    assert not dropped["table_drop_trace"][4]["confirmed_events"]
    assert dropped["table_drop_trace"][5]["confirmed_events"] == dropped["confirmed_events"]
    assert all(row["candidates"]["basket_1"] is True for row in dropped["table_drop_trace"][1:])
    shallow = artifacts["basket_s004_10"]
    assert shallow["new"]["classification"] == "success"
    assert all(row["candidates"]["basket_1"] is False for row in shallow["table_drop_trace"])
    assert shallow["confirmed_events"] == []
    grasped = artifacts["basket_s002_10"]
    assert grasped["old"]["failure_reasons"] == grasped["new"]["failure_reasons"] == ["wrong_grasp"]
    assert grasped["confirmed_events"] == raw["basket_s002_10"]["confirmed_events"]
    unfinished = artifacts["basket_s003_10"]
    assert unfinished["old"]["failure_reasons"] == unfinished["new"]["failure_reasons"] == ["goal_not_confirmed_by_horizon"]
    assert unfinished["preserved"]["n_steps"] == 8
    with (output / "episodes.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 100 and sum(row["new_classification"] == "missing" for row in rows) == 90

    # Re-reading originals retains the old interpretation; no in-place schema,
    # score, video, observation, source, or execution-evidence rewrite occurred.
    assert workflow.inspect_batch(original) == before_summary
    assert tree_hash(original) == original_hashes
    assert tree_hash(tmp_path / "sources") == source_hashes
    assert (tmp_path / "batch.json").read_bytes() == config_bytes
    for invalid in (original, original / "nested", output):
        with pytest.raises(ValueError, match="new independent directory"):
            rescore.rescore_batch(original, invalid)
    assert tree_hash(original) == original_hashes


def test_rescore_cli_forwards_paths_and_reports_unverified_sources(tmp_path, monkeypatch, capsys):
    from benchmark.remaining_goals.headless import cli, rescore
    calls = []
    def derive(directory, output):
        calls.append((directory, output))
        return {"schema_version": rescore.SCHEMA, "derived_only": True, "new_execution": False,
                "unverified_task_artifacts": [{"task_id": "basket", "reason": "invalid original SHA"}]}
    monkeypatch.setattr(rescore, "rescore_batch", derive)
    source, target = tmp_path / "old", tmp_path / "new"
    assert cli.main(["rescore", "--run", str(source), "--out", str(target)]) == 2
    assert calls == [(source, target)]
    printed = json.loads(capsys.readouterr().out)
    assert printed["derived_only"] is True and printed["new_execution"] is False
    assert printed["unverified_task_artifacts"][0]["reason"] == "invalid original SHA"
