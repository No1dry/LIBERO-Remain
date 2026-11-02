"""Bounded execution and read-only reporting under the nine-task plan."""
from copy import deepcopy
import importlib

import pytest

from benchmark.remaining_goals.headless import nine_planning as p, workflow
from tests.test_headless_nine_planning import configuration033


def test_missing_reuse_and_new_sources_never_load_model(tmp_path, monkeypatch):
    w = importlib.import_module("benchmark.remaining_goals.headless.nine_workflow")
    config = configuration033(tmp_path / "config", monkeypatch)
    monkeypatch.setattr(workflow, "make_policy", lambda *a: pytest.fail("missing/reuse-only must not load model"))
    monkeypatch.setattr(workflow, "make_environment", lambda *a: pytest.fail("missing/reuse-only must not create native"))
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="allow-missing"):
        w.run_batch(config, out)
    assert not out.exists()
    batch = w.run_batch(config, out, allow_missing=True)
    assert len(batch["episodes"]) == 30 and all("basket" not in key for key in batch["episodes"])
    report = w.inspect_batch(out)
    assert report["conditions"]["00"]["expected"] == 90
    assert report["conditions"]["00"]["coverage"]["numerator"] == 0
    assert report["conditions"]["00"]["official_task_SR"]["percent"] is None
    assert report["conditions"]["00"]["classification_counts"]["missing"] == 90


@pytest.mark.parametrize("missing_artifact", [False, True])
def test_queue_contains_exactly_new_sixty_and_continuation_cannot_repeat(tmp_path, monkeypatch, missing_artifact):
    w = importlib.import_module("benchmark.remaining_goals.headless.nine_workflow")
    calls, loaded = [], []
    class Policy:
        def close(self): pass
    monkeypatch.setattr(workflow, "make_policy", lambda *a: loaded.append(Policy()) or loaded[-1])
    def run_task(directory, source, runtime, identity, bind, **kwargs):
        directory.mkdir(parents=True)
        ep = source["episodes"][0]
        calls.append(ep["episode_id"])
        return {"status": "completed", "error": None}
    monkeypatch.setattr(workflow, "_run_task", run_task)
    monkeypatch.setattr(workflow, "_read_task", lambda *a, **k: ({"status": "completed", "error": None}, []))
    real_plan = w.dry_plan
    def ready_plan(config):
        plan = real_plan(config)
        for row in plan["sources"]:
            if row["selected"]:
                source = {"protocol": plan["protocol"], "episodes": [{k: deepcopy(row[k]) for k in plan["expected"][0]}]}
                source["source_plan_sha256"] = p.canonical_hash(source)
                row.update(status="ready", error=None, source_plan=source)
        plan["ready_episodes"] = 30
        plan["plan_sha256"] = p.canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
        return plan
    monkeypatch.setattr(w, "dry_plan", ready_plan)
    for protocol in ("nine-normal00", "nine-mask10"):
        config = configuration033(tmp_path / protocol, monkeypatch, protocol)
        out = tmp_path / (protocol + "-run")
        w.run_batch(config, out)
        if missing_artifact:
            (out / "episodes" / calls[-30]).rmdir()  # Deliberately remove one empty fake evidence directory.
        w.run_batch(config, out, continue_run=True)
    assert len(calls) == len(set(calls)) == 60 and len(loaded) == 2
    assert {name.rsplit("_s", 1)[0] for name in calls} == {"bowl_drawer_close", "two_pots", "mug_microwave_close"}


def test_report_keeps_90_population_and_mixed00_endpoint_paths_separate():
    w = importlib.import_module("benchmark.remaining_goals.headless.nine_workflow")
    from benchmark.remaining_goals.headless.offline_scoring import collect_reuse
    records = collect_reuse()["episodes"]
    old = records["basket_s000_00"]
    old["primary"].update(classification="success", success=True, execution_status="completed",
        official_goals_achieved=True, path_complete=True, path_length_m=9.0)
    old["source"]["original_protocol"] = "remaining-headless-normal00-control-v1"
    expected = next(e for e in p.expected_episodes("nine-normal00") if e["task_id"] == "two_pots")
    new = deepcopy(old)
    new["primary"].update(expected, path_length_m=1.0)
    new["legacy"].update(expected)
    new["source"]["original_protocol"] = "remaining-headless-nine-normal00-v1"
    records[expected["episode_id"]] = new
    report = w.make_report(records, protocols=["nine-normal00", "nine-mask10"])
    assert report["conditions"]["00"]["expected"] == 90
    assert report["conditions"]["10"]["expected"] == 90
    assert report["conditions"]["00"]["official_task_SR"]["numerator"] == 2
    assert report["conditions"]["00"]["official_task_SR"]["denominator"] == 2
    assert report["conditions"]["00"]["success_conditional_mean_path_m"] is None
    assert len(report["conditions"]["00"]["path_by_endpoint"]) == 2


def test_reuse_model_comparison_allows_relocation_and_harness_but_not_statistics():
    w = importlib.import_module("benchmark.remaining_goals.headless.nine_workflow")
    from benchmark.remaining_goals.headless.offline_scoring import collect_reuse
    records = collect_reuse()
    row = records["episodes"]["basket_s000_00"]
    row["primary"].update(classification="success", execution_status="completed")
    model = {"checkpoint": "/new/weights", "unnorm_key": "libero_10_no_noops",
             "normalization_statistics_sha256": "a" * 64}
    row["source"].update(model_identity={**model, "checkpoint": "/old/weights"},
                         source_harness_sha256="b" * 64)
    w._check_reuse_model(records, model)
    model["normalization_statistics_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="differ from reused episode"):
        w._check_reuse_model(records, model)
