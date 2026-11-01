"""Task031 file-only selection and fixed budget; no native/model imports."""
import pytest

from benchmark.remaining_goals.headless import scoped_planning as planning
from benchmark.remaining_goals.headless.workflow import write_json
from tests.test_headless_workflow import configuration


def configuration031(tmp_path, monkeypatch, protocol="normal00-control", population="existing-eight"):
    from benchmark.remaining_goals.headless.planning import read_json
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy = read_json(configuration(tmp_path, monkeypatch))
    sources = tmp_path / "composite.json"
    write_json(sources, {"schema_version": planning.SOURCES_SCHEMA, "protocol": protocol,
                        "expected": planning.expected_episodes(protocol), "entries": []})
    config = tmp_path / "scoped.json"
    write_json(config, {"schema_version": planning.CONFIG_SCHEMA, "protocol": protocol,
        "population": population, "runtime_config": legacy["runtime_config"],
        "extension_transfer": legacy["extension_transfer"], "sources": str(sources)})
    return config


def test_budgets_do_not_authorize_old_eighty_mask10():
    assert len(planning.expected_episodes("normal00-control")) == 100
    assert len(planning.expected_episodes("selected-mask10")) == 20
    assert planning.budget_plan("normal00-control", "existing-eight")["selected_count"] == 80
    assert planning.budget_plan("normal00-control", "missing-two")["selected_count"] == 20
    budget = planning.budget_plan("selected-mask10", "missing-two")
    assert budget["maximum_policy_steps"] == 20 * 520
    assert budget["new_model_episode_target_all_phases"] == 120
    assert {e["task_id"] for e in budget["selected"]} == set(planning.MISSING_TASKS)
    with pytest.raises(ValueError):
        planning.budget_plan("selected-mask10", "all")


def test_file_only_plan_retains_missing_full_denominator(tmp_path, monkeypatch):
    config = configuration031(tmp_path, monkeypatch)
    plan = planning.validate_plan(planning.dry_plan(config))
    assert len(plan["expected"]) == 100 and len(plan["selected_episode_ids"]) == 80
    assert plan["ready_episodes"] == 0
    assert sum(row["status"] == "missing" for row in plan["sources"]) == 80
    assert sum(row["status"] == "not_selected" for row in plan["sources"]) == 20
    assert plan["simulation_created"] is plan["weights_loaded"] is False
    plan["expected"].pop()
    with pytest.raises(ValueError):
        planning.validate_plan(plan)


def test_composite_wrong_and_duplicate_source_rejected(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless.planning import read_json
    config = configuration031(tmp_path, monkeypatch, "selected-mask10", "missing-two")
    path = tmp_path / "composite.json"
    value = read_json(path)
    value["entries"] = [{"task_id": "basket", "initial_state_index": 0, "origin": None}]
    write_json(path, value, update=True)
    with pytest.raises(ValueError, match="unplanned"):
        planning.dry_plan(config)
    value["entries"] = [{"task_id": planning.MISSING_TASKS[0], "initial_state_index": 0, "origin": None}] * 2
    write_json(path, value, update=True)
    with pytest.raises(ValueError, match="duplicate"):
        planning.dry_plan(config)
