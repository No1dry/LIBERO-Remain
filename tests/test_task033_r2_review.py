"""Independent pure-CPU review reproductions; no native or model work."""
from copy import deepcopy

import pytest

from tests.test_task033_r2_repair_plan import fixture_inputs


def test_repair_continuation_visits_unattempted_sources_without_retrying_interruption(tmp_path, monkeypatch):
    repair, inventory, report = fixture_inputs(tmp_path, monkeypatch)

    def inspect(protocol, task, index, origin):
        ready = bool(origin and origin.get("fixture_ready"))
        return {"task_id": task, "initial_state_index": index, "origin": deepcopy(origin),
                "status": "ready" if ready else "failed", "phase": "complete" if ready else "candidate",
                "candidate": "existing" if ready else "missing", "constructed": False,
                "replayed": False, "operations": [], "actual_control_steps": 0,
                "count_status": "complete", "reason": None if ready else "original failure"}

    monkeypatch.setattr(repair.preparation, "_inspect", inspect)
    plan_dir = tmp_path / "plan"
    repair.plan_repairs(inventory, report, plan_dir)
    calls = []

    def native(operation, task, index, origin, output, protocol, **options):
        calls.append((task, index, operation))
        if len(calls) == 1:
            raise KeyboardInterrupt("synthetic interruption after persisted running intent")
        raise RuntimeError("synthetic failed first attempt; do not retry this source")

    monkeypatch.setattr(repair.preparation, "_native", native)
    output = tmp_path / "physical"
    with pytest.raises(KeyboardInterrupt):
        repair.prepare_repairs(plan_dir / "repair_plan.json", output)
    repair.prepare_repairs(plan_dir / "repair_plan.json", output, continuation=True)
    assert len(calls) == 20, "resume must visit the 19 never-attempted physical gaps exactly once"
    assert len(set(calls)) == 20, "interrupted/failed R2 attempts must not silently repeat"
    repair.prepare_repairs(plan_dir / "repair_plan.json", output, continuation=True)
    assert len(calls) == 20, "another continuation must not retry any failed or interrupted R2 attempt"
