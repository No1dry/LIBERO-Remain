"""Independent review regressions: persist worker-attempt failures without reruns."""
from copy import deepcopy

import pytest

from benchmark.remaining_goals.headless import nine_planning as p, nine_workflow as w, workflow
from tests.test_headless_nine_planning import configuration033


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_worker_start_failure_is_technical_and_never_retried(tmp_path, monkeypatch, error_type):
    from benchmark.remaining_goals import cli
    monkeypatch.setattr(cli, "_source_hash", lambda: "d" * 64)
    config = configuration033(tmp_path / "config", monkeypatch)
    original = w.dry_plan
    chosen = p.budget_plan("nine-normal00")["selected"][0]["episode_id"]

    def one_ready(path):
        plan = original(path)
        for row in plan["sources"]:
            if row["episode_id"] == chosen:
                source = {"protocol": plan["protocol"], "episodes": [
                    {key: deepcopy(row[key]) for key in plan["expected"][0]}]}
                source["source_plan_sha256"] = p.canonical_hash(source)
                row.update(status="ready", error=None, source_plan=source)
        plan["ready_episodes"] = 1
        plan["plan_sha256"] = p.canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
        return plan

    calls = []

    def failing_worker(*args):
        calls.append("attempted")
        raise error_type("synthetic worker-start interruption")

    monkeypatch.setattr(w, "dry_plan", one_ready)
    monkeypatch.setattr(workflow, "make_policy", failing_worker)
    monkeypatch.setattr(workflow, "make_environment", lambda *a: pytest.fail("worker failed before native creation"))
    out = tmp_path / "run"
    if error_type is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            w.run_batch(config, out, allow_missing=True)
    else:
        w.run_batch(config, out, allow_missing=True)
    before = w.inspect_batch(out)
    assert before["episodes"][chosen]["primary"]["classification"] == "technical_error"
    assert "synthetic worker-start interruption" in repr(before["episodes"][chosen])
    assert before["conditions"]["00"]["classification_counts"]["technical_error"] == 1
    assert not (out / "episodes" / chosen).exists()
    w.run_batch(config, out, allow_missing=True, continue_run=True)
    assert calls == ["attempted"]
    after = w.inspect_batch(out)
    assert after["episodes"][chosen]["primary"]["classification"] == "technical_error"
    assert "synthetic worker-start interruption" in repr(after["episodes"][chosen])
    assert after["conditions"]["00"]["official_task_SR"]["percent"] is None


def test_mixed_model_identities_preserve_original_rows_and_disable_only_mixed_aggregate():
    from benchmark.remaining_goals.headless.offline_scoring import collect_reuse
    records = collect_reuse()["episodes"]
    names = ["basket_s000_00", "stove_s000_00"]
    for name, digest in zip(names, ("a" * 64, "b" * 64)):
        record = records[name]
        record["primary"].update(classification="success", success=True, execution_status="completed",
                                  official_goals_achieved=True, path_complete=True, path_length_m=1.)
        record["source"]["model_identity"] = {
            "unnorm_key": "libero_10_no_noops", "normalization_statistics_sha256": digest}
    original = deepcopy(records)
    report = w.make_report(records, protocols=["nine-normal00"])
    assert records == original
    assert all(report["episodes"][name]["primary"]["classification"] == "success" for name in names)
    assert len(report["model_identity_groups"]) == 2
    assert report["model_compatibility_issues"]
    assert report["conditions"]["00"]["official_task_SR"] is None
    assert report["conditions"]["00"]["tasks"][0]["official_task_SR"]["percent"] == 100.
