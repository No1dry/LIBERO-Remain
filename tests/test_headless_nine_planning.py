"""Fixed nine-task model population and reuse-only legacy rows."""
from copy import deepcopy
from pathlib import Path
import importlib
import json

import pytest


def test_nine_budget_is_90_with_only_new_three_executable():
    p = importlib.import_module("benchmark.remaining_goals.headless.nine_planning")
    for protocol in ("nine-normal00", "nine-mask10"):
        budget = p.budget_plan(protocol)
        assert len(budget["expected"]) == 90 and len(budget["selected"]) == 30
        assert len(budget["reuse_only"]) == 60
        assert [e["libero_task_id"] for e in budget["expected"]][::10] == [0, 1, 2, 3, 4, 6, 7, 8, 9]
        assert {e["libero_task_id"] for e in budget["selected"]} == {3, 8, 9}
        assert {e["suite"] for e in budget["expected"]} == {"libero_10"}
        assert budget["new_model_episode_target_all_conditions"] == 60
        assert budget["maximum_policy_steps"] == 30 * 520
        with pytest.raises(ValueError):
            p.budget_plan(protocol, "all")
        with pytest.raises(ValueError):
            p.budget_plan(protocol, "reuse-six")


def configuration033(tmp_path, monkeypatch, protocol="nine-normal00"):
    from benchmark.remaining_goals.headless import nine_planning as p, workflow
    from benchmark.remaining_goals.headless.offline_scoring import collect_reuse
    import benchmark.remaining_goals.evaluation as evaluation
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(evaluation, "check_config", lambda *a, **k: {"errors": [], "warnings": []})
    runtime = json.loads(Path("configs/remaining_goals/runtime/openvla_oft_sog10.json").read_text())
    workflow.write_json(tmp_path / "runtime.json", runtime)
    workflow.write_json(tmp_path / "sources.json", p.sources_template(protocol))
    reuse = collect_reuse()
    workflow.write_json(tmp_path / "reuse.json", p.reuse_index(reuse))
    config = tmp_path / "config.json"
    workflow.write_json(config, {"schema_version": p.CONFIG_SCHEMA, "protocol": protocol,
        "population": "new-three", "runtime_config": "runtime.json", "sources": "sources.json", "reuse_manifest": "reuse.json"})
    return config


def test_nine_plan_does_not_promote_missing_reuse_to_execution(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import nine_planning as p
    plan = p.validate_plan(p.dry_plan(configuration033(tmp_path, monkeypatch)))
    assert len(plan["selected_episode_ids"]) == 30
    assert len(plan["expected"]) == 90
    assert sum(row["execution_kind"] == "reuse_only" for row in plan["sources"]) == 60
    assert plan["ready_episodes"] == 0
    assert not plan["simulation_created"] and not plan["weights_loaded"]
    forged = deepcopy(plan)
    forged["selected_episode_ids"].append("basket_s000_00")
    forged["plan_sha256"] = p.canonical_hash({k: v for k, v in forged.items() if k != "plan_sha256"})
    with pytest.raises(ValueError):
        p.validate_plan(forged)


@pytest.mark.parametrize("fault", ["suite", "normalization", "checkpoint", "population", "foreign_source"])
def test_nine_plan_rejects_scope_and_runtime_drift(tmp_path, monkeypatch, fault):
    from benchmark.remaining_goals.headless import nine_planning as p
    config = configuration033(tmp_path, monkeypatch)
    value = json.loads(config.read_text())
    runtime = json.loads((tmp_path / "runtime.json").read_text())
    if fault == "suite":
        runtime["suite"] = runtime["adapter_options"]["suite"] = "libero_90"
    elif fault == "normalization":
        runtime["adapter_options"]["suite_transfer"] = {"normalization_suite": "libero_90"}
    elif fault == "checkpoint":
        runtime["checkpoint_source"]["revision"] = "0" * 40
    elif fault == "population":
        value["population"] = "all"
    else:
        source = p.sources_template("nine-normal00")
        source["entries"].append({"task_id": "frypan_stove9", "initial_state_index": 0, "origin": None})
        (tmp_path / "sources.json").write_text(json.dumps(source))
    config.write_text(json.dumps(value))
    (tmp_path / "runtime.json").write_text(json.dumps(runtime))
    with pytest.raises(ValueError):
        p.dry_plan(config)
