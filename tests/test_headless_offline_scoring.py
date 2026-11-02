"""Task032 report-only derivation: no simulation, model or source mutation."""
from copy import deepcopy
import builtins
import hashlib
import importlib
import json

import pytest

from benchmark.remaining_goals.headless import planning, scoped_planning, workflow
from benchmark.remaining_goals.headless.metrics import _score_verified_episode, _summarize_scored
from tests.test_headless_scoped_planning import configuration031


def api():
    module = importlib.util.find_spec("benchmark.remaining_goals.headless.offline_scoring")
    assert module is not None, "Task032 offline scoring module is not implemented"
    return importlib.import_module(module.name)


def row(condition="10", **changes):
    value = dict(episode_id=f"basket_s000_{condition}", task_id="basket", suite="libero_10",
        initial_state_index=0, initial_mask=[condition == "10", False],
        classification="unknown", success=None, failure_reasons=[],
        unknown_reasons=["event_evidence_unknown"], n_steps=6, path_length_m=.6,
        path_complete=True, goal_confirmed_step=6, official_goals_achieved=True,
        execution_status="completed", exit_reason="goal_confirmed", error=None,
        event_unknown=[dict(step=0, event="table_drop", object="basket_1")],
        release_unknown_steps=[])
    value.update(changes)
    return value


@pytest.mark.parametrize("official,status,want", [
    (True, "completed", "success"), (False, "completed", "failure"),
    (None, "completed", "unknown"), (True, "runtime_error", "technical_error"),
    (None, "missing", "missing")])
def test_official00_ignores_release_unknown_but_never_imputes_missing_or_technical(official, status, want):
    old = row("00", official_goals_achieved=official, execution_status=status,
        classification="technical_error" if status == "runtime_error" else "missing" if status == "missing" else "unknown",
        unknown_reasons=["event_evidence_unknown", "completion_release_unknown"])
    before = deepcopy(old)
    new = api().derive_row(old, condition="00")
    assert new["classification"] == want
    assert new["success"] is (True if want == "success" else False if want == "failure" else None)
    assert new["legacy_classification"] == before["classification"]
    assert new["legacy_unknown_reasons"] == before["unknown_reasons"]
    assert old == before


@pytest.mark.parametrize("events,failures,other_unknown,want", [
    (["table_drop"], [], [], "success"),
    (["table_drop", "wrong_placement"], [], [], "unknown"),
    (["wrong_grasp"], [], [], "unknown"),
    (["table_drop"], ["table_drop"], [], "success"),
    (["table_drop"], ["wrong_grasp"], [], "failure"),
    (["table_drop"], ["goal_regression", "invariant_regression"], [], "failure"),
    (["table_drop"], [], ["completion_release_unknown"], "unknown"),
    (["table_drop", "wrong_placement"], ["goal_not_confirmed_by_horizon"], [], "failure")])
def test_mask10_only_removes_table_drop_and_keeps_failure_priority(events, failures, other_unknown, want):
    old = row(failure_reasons=failures, unknown_reasons=["event_evidence_unknown", *other_unknown],
        classification="failure" if failures else "unknown",
        event_unknown=[dict(step=0, event=event, object="object") for event in events])
    new = api().derive_row(old, condition="10", confirmed_events=[
        dict(event=event, object="object", start_step=0, confirmation_step=4)
        for event in failures if event in {"wrong_grasp", "table_drop"}])
    assert new["classification"] == want
    assert ("event_evidence_unknown" in new["unknown_reasons"]) == any(e != "table_drop" for e in events)
    assert new["failure_reasons"] == [e for e in failures if e != "table_drop"]
    assert new["legacy_event_unknown"] == old["event_unknown"]
    assert new["classification_changed"] == (old["classification"] != want)


def test_missing_event_detail_is_not_silently_removed():
    old = row(); del old["event_unknown"]
    with pytest.raises(ValueError, match="event_unknown"):
        api().derive_row(old, condition="10")


def test_new_raw_official_signal_includes_invariants_and_rejects_inconsistent_any():
    old = row("00", official_goals_achieved=False)
    result = dict(status="completed", protocol_version="nine-official-test", official_goals_achieved=False,
        n_steps=1, configuration={"horizon": 520, "confirmation_steps": 4}, exit_reason="horizon",
        trace=[dict(goals=[False, False], official_goal_values=[False, False, True], official_success=False),
               dict(goals=[True, True], official_goal_values=[True, True, False], official_success=False)],
        confirmed_events=[], event_unknown=old["event_unknown"])
    record = api().score_verified_result(old, result, condition="00", legacy_row=old)
    assert record["primary"]["classification"] == "failure"
    assert record["source"]["original_endpoint"]["exit_reason"] == "horizon"
    result["official_goals_achieved"] = True
    with pytest.raises(ValueError, match="official"):
        api().score_verified_result(old, result, condition="00", legacy_row=old)


def test_raw_official_success_must_agree_with_complete_goal_values():
    old = row("00")
    result = dict(status="completed", official_goals_achieved=True, n_steps=0,
        trace=[dict(goals=[True, True], official_goal_values=[True, True, False], official_success=True)])
    with pytest.raises(ValueError, match="official_success"):
        api().score_verified_result(old, result, condition="00", legacy_row=old)


@pytest.mark.parametrize("released", [False, None])
def test_new00_first_official_hit_does_not_claim_legacy_release_confirmation(released):
    original = row("00", classification="success", success=True, unknown_reasons=[], event_unknown=[])
    episode = {key: original[key] for key in ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")}
    result = {**deepcopy(original), "status": "completed", "protocol_version": "remaining-headless-nine-normal00-v1",
        "n_steps": 1, "path_length_m": .1, "goal_confirmed_step": 1, "goal_completion_step": 1,
        "goal_regression": None, "confirmed_events": [], "exit_reason": "official_success",
        "configuration": {"horizon": 520, "confirmation_steps": 4, "max_chunk_steps": 8},
        "trace": [dict(goals=[False, False], official_goal_values=[False, False], official_success=False, released=released),
                  dict(goals=[True, True], official_goal_values=[True, True], official_success=True, released=released)]}
    record = api().score_verified_result(episode, result, condition="00")
    assert record["primary"]["classification"] == "success"
    assert record["primary"]["goal_confirmed_step"] == 1
    assert record["legacy_diagnostic_available"] is False
    assert record["legacy"]["legacy_diagnostic_available"] is False
    assert record["legacy"]["success"] is None
    assert record["legacy"]["goal_confirmed_step"] is None
    assert record["source"]["original_endpoint"]["goal_confirmed_step"] == 1


@pytest.mark.parametrize("condition,regression,want", [("10", True, "failure"), ("00", None, "success")])
def test_nine_invariant_restoration_keeps_sticky10_reason_without_penalizing00(condition, regression, want):
    base = row(condition, episode_id=f"two_pots_s000_{condition}", task_id="two_pots", event_unknown=[], unknown_reasons=[])
    episode = {key: base[key] for key in ("episode_id", "task_id", "suite", "initial_state_index", "initial_mask")}
    last = 6 if condition == "10" else 2
    trace = []
    for step in range(last + 1):
        goals = [condition == "10" or step >= 2, step >= 2]
        invariants = [step != 1]  # stove switched off, then restored before final success
        trace.append(dict(goals=goals, invariant_values=invariants, official_goal_values=goals + invariants,
                          official_success=all(goals + invariants), released=True))
    result = {**base, "status": "completed", "protocol_version": f"remaining-headless-nine-{'mask10' if condition == '10' else 'normal00'}-v1",
        "n_steps": last, "goal_confirmed_step": last, "goal_completion_step": 2,
        "goal_regression": regression, "invariant_regression": regression, "confirmed_events": [],
        "exit_reason": "goal_confirmed" if condition == "10" else "official_success", "trace": trace,
        "configuration": {"horizon": 520, "confirmation_steps": 4, "max_chunk_steps": 8}}
    before = deepcopy(result)
    record = api().score_verified_result(episode, result, condition=condition)
    assert record["primary"]["classification"] == want
    assert record["legacy"]["invariant_regression"] is regression
    assert record["primary"]["invariant_regression"] is regression
    if condition == "10":
        assert "invariant_regression" in record["legacy"]["failure_reasons"]
        assert "invariant_regression" in record["primary"]["failure_reasons"]
    else:
        assert record["primary"]["failure_reasons"] == []
    assert result == before


def write(path, value):
    workflow.write_json(path, value, update=path.exists())


def tree_hash(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def normal_archive(tmp_path, monkeypatch, *, prior=None, population="existing-eight"):
    """Archived metadata/summary fixture; no fake rollout and no raw required."""
    config = configuration031(tmp_path / "config", monkeypatch, population=population)
    plan = scoped_planning.dry_plan(config)
    out = tmp_path / "run"
    old = row("00", unknown_reasons=["completion_release_unknown", "event_evidence_unknown"])
    ep = next(e for e in plan["expected"] if e["episode_id"] == old["episode_id"])
    model = {"policy_metadata": {"unnorm_key": "libero_10_no_noops", "checkpoint": "original-SOG10",
        "repo_commit": "638918f3d1c2e43a39a8a20772bdb8b91835e4b7", "normalization_statistics_sha256": "e" * 64}}
    source = dict(protocol="normal00-control", task_id="basket", episodes=[deepcopy(ep)],
        source={"manifest": "original.json", "manifest_sha256": "a" * 64},
        source_acceptance={"schema_version": "remaining-headless-normal00-source-acceptance-v1",
            "acceptance_scope": "initial-only", "selection_sha256": "b" * 64,
            "selected_episode_ids": [ep["episode_id"]], "evidence_sha256": "c" * 64})
    source["episodes"][0].update(state_sha256="a" * 64, model_xml_sha256="b" * 64, bddl_sha256="c" * 64,
                                  instruction="original instruction", seed=0)
    source["source_plan_sha256"] = planning.canonical_hash(source)
    if prior is None:
        selected = next(r for r in plan["sources"] if r["episode_id"] == ep["episode_id"])
        selected.update(status="ready", error=None, source_plan=source)
        plan["ready_episodes"] = 1
    plan["plan_sha256"] = planning.canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
    write(out / "plans/000.json", plan)
    batch = dict(schema_version="remaining-headless-scoped-batch-run-v1", protocol="normal00-control",
        protocol_version=plan["protocol_version"], identity=plan["identity"], batch_identity_sha256=plan["batch_identity_sha256"],
        expected=plan["expected"], selected_episode_ids=plan["selected_episode_ids"],
        episodes={old["episode_id"]: {"status": "completed", "error": None}} if prior is None else {},
        invocations=[{"plan": "plans/000.json", "sha256": planning.file_sha(out / "plans/000.json")}],
        prior_run=None if prior is None else {"directory": str(prior), "batch_sha256": planning.file_sha(prior / "batch.json")},
        loaded_model_identity=workflow.shared_model_identity(model))
    if prior is not None:
        # The true historical prior contract requires identical runtime paths.
        previous = planning.read_json(prior / "batch.json")
        batch["identity"]["runtime_configs"] = deepcopy(previous["identity"]["runtime_configs"])
        plan["identity"] = deepcopy(batch["identity"])
        batch["batch_identity_sha256"] = plan["batch_identity_sha256"] = planning.canonical_hash(batch["identity"])
        plan["plan_sha256"] = planning.canonical_hash({k: v for k, v in plan.items() if k != "plan_sha256"})
        write(out / "plans/000.json", plan)
        batch["invocations"][0]["sha256"] = planning.file_sha(out / "plans/000.json")
    write(out / "batch.json", batch)
    expected = plan["expected"]
    rows = [deepcopy(old) if e["episode_id"] == old["episode_id"] else _score_verified_episode(e, None, None) for e in expected]
    summary = _summarize_scored(expected, rows, protocol="normal00-control")
    summary.update(batch_identity_sha256=batch["batch_identity_sha256"], protocol="normal00-control",
        selected_count=len(batch["selected_episode_ids"]), unverified_task_artifacts=[], task_execution=batch["episodes"],
        prior_run=batch["prior_run"])
    write(out / "summary.json", summary)
    if prior is None:
        metadata = dict(schema_version="remaining-headless-scoped-source-run-v1", protocol_version=plan["protocol_version"],
            status="completed", error=None, run_id="archived-run", batch_identity_sha256=batch["batch_identity_sha256"],
            source_plan=source, runtime_config=batch["identity"]["runtime_configs"]["libero_10"], model_runtime=model,
            results=[{"episode_id": old["episode_id"], "path": f"raw/{old['episode_id']}.json", "sha256": "d" * 64,
                      "validation": "verified"}], missing=[])
        write(out / "episodes" / old["episode_id"] / "task_run.json", metadata)
    return out


def forbid_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline source reader started native/model or whole-run raw verification")
    for name in ("make_policy", "make_environment", "make_recorder", "_read_task"):
        monkeypatch.setattr(workflow, name, forbidden)
    original = builtins.__import__
    def guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "transformers", "libero", "robosuite", "mujoco", "mujoco_py"}
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guard)


def test_normal_report_prior_union_keeps_original_identity_without_raw_or_execution(tmp_path, monkeypatch):
    prior = normal_archive(tmp_path / "first", monkeypatch)
    latest = normal_archive(tmp_path / "second", monkeypatch, prior=prior, population="missing-two")
    before = tree_hash(tmp_path)
    forbid_execution(monkeypatch)
    report = api().collect_reuse(normal00_run=latest, task_ids=("basket",))
    assert not report["issues"]
    assert len(report["episodes"]) == 20  # ten per condition, missing10 are explicit
    record = report["episodes"]["basket_s000_00"]
    assert record["primary"]["classification"] == "success"
    assert record["legacy"]["classification"] == "unknown"
    assert record["source"]["run_path"] == str(prior.resolve())
    assert record["source"]["source_harness_sha256"] == "d" * 64
    assert record["source"]["model_identity"]["policy_metadata"]["repo_commit"] == "638918f3d1c2e43a39a8a20772bdb8b91835e4b7"
    assert record["source"]["input_evidence_level"] == "summary_with_bound_metadata"
    assert record["source"]["raw"]["recorded_sha256"] == "d" * 64
    assert record["source"]["raw"]["verified_file_sha256"] is None
    verified = record["source"]["verified_files"]
    assert {r["kind"] for r in verified} >= {"batch", "plan", "task_run", "summary"}
    assert all(set(r) == {"path", "sha256", "kind"} for r in verified)
    assert not any("/raw/" in r["path"].replace("\\", "/") for r in verified)
    assert report["selected_episode_ids"]["00"] == [f"basket_s{i:03d}_00" for i in range(10)]
    assert tree_hash(tmp_path) == before


@pytest.mark.parametrize("fault", ["summary_identity", "task_runtime", "model", "prior_hash", "missing_model"])
def test_normal_report_rejects_broken_provenance_without_changing_to_model_failure(tmp_path, monkeypatch, fault):
    prior = normal_archive(tmp_path / "first", monkeypatch)
    latest = normal_archive(tmp_path / "second", monkeypatch, prior=prior, population="missing-two")
    if fault == "summary_identity":
        path = prior / "summary.json"; data = planning.read_json(path); data["batch_identity_sha256"] = "0" * 64
    elif fault in {"task_runtime", "model", "missing_model"}:
        path = prior / "episodes/basket_s000_00/task_run.json"; data = planning.read_json(path)
        if fault == "task_runtime": data["runtime_config"]["policy_id"] = "different"
        elif fault == "model": data["model_runtime"]["policy_metadata"]["normalization_statistics_sha256"] = "0" * 64
        else: data["model_runtime"] = None
    else:
        path = prior / "batch.json"; data = planning.read_json(path); data["changed"] = True
    write(path, data)
    report = api().collect_reuse(normal00_run=latest, task_ids=("basket",))
    assert report["issues"]
    assert report["episodes"]["basket_s000_00"]["primary"]["classification"] == "missing"


def test_normal_report_cannot_claim_recorded_success_without_a_source_directory(tmp_path, monkeypatch):
    original = normal_archive(tmp_path, monkeypatch)
    directory = original / "episodes/basket_s000_00"
    directory.rename(original / "preserved_unbound_source")
    report = api().collect_reuse(normal00_run=original, task_ids=("basket",))
    assert report["issues"]
    assert report["episodes"]["basket_s000_00"]["primary"]["classification"] == "missing"


def test_normal_summary_invalid_path_cannot_enter_success_conditional_efficiency(tmp_path, monkeypatch):
    original = normal_archive(tmp_path, monkeypatch)
    summary = planning.read_json(original / "summary.json")
    summary["episodes"][0]["path_length_m"] = None
    write(original / "summary.json", summary)
    report = api().collect_reuse(normal00_run=original, task_ids=("basket",))
    assert report["issues"]
    assert report["episodes"]["basket_s000_00"]["primary"]["classification"] == "missing"


@pytest.mark.parametrize("missing", ["signal", "summary"])
def test_normal_report_falls_back_only_to_needed_raw_when_summary_facts_absent(tmp_path, monkeypatch, missing):
    import sys
    from types import ModuleType
    from benchmark.remaining_goals.headless.runner import run_normal00_episode
    from benchmark.remaining_goals.headless.evidence import HeadlessEvidence
    from tests.test_headless_normal00_runtime import NormalEnv
    from tests.test_headless_runner import Policy
    original = normal_archive(tmp_path, monkeypatch)
    directory = original / "episodes/basket_s000_00"
    metadata = planning.read_json(directory / "task_run.json")
    episode = metadata["source_plan"]["episodes"][0]
    fake = ModuleType("benchmark.remaining_goals.headless.environment")
    fake.validate_measurement_static = lambda value, **kwargs: deepcopy(value)
    fake.validate_evaluator_evidence = lambda facts, frozen: deepcopy(facts)
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    identity = workflow.evidence_identity(metadata, episode)
    evidence = HeadlessEvidence(directory / "evidence" / episode["episode_id"], identity)
    raw = run_normal00_episode(NormalEnv(), Policy(), episode, identity=identity, evidence=evidence)
    path = directory / metadata["results"][0]["path"]
    write(path, raw)
    metadata["results"][0]["sha256"] = planning.file_sha(path)
    write(directory / "task_run.json", metadata)
    summary_path = original / "summary.json"
    if missing == "summary":
        summary_path.unlink()
    else:
        summary = planning.read_json(summary_path)
        del next(r for r in summary["episodes"] if r["episode_id"] == episode["episode_id"])["official_goals_achieved"]
        write(summary_path, summary)
    before = tree_hash(tmp_path)
    forbid_execution(monkeypatch)
    report = api().collect_reuse(normal00_run=original, task_ids=("basket",))
    assert not report["issues"]
    record = report["episodes"][episode["episode_id"]]
    assert record["primary"]["classification"] == "success"
    assert record["source"]["input_evidence_level"] == "raw_and_execution_evidence_verified"
    assert len([ref for ref in report["source_files"] if ref["kind"] == "raw"]) == 1
    assert tree_hash(tmp_path) == before


def test_013_derived_reports_are_hash_bound_and_original_root_can_relocate(tmp_path, monkeypatch):
    from tests.test_headless_support_rescore import make_old_batch
    from benchmark.remaining_goals.headless import rescore
    original = make_old_batch(tmp_path, monkeypatch)
    derived = tmp_path / "derived"
    rescore.rescore_batch(original, derived)
    summary = planning.read_json(derived / "summary.json")
    summary["source"]["batch_path"] = str(tmp_path / "no-longer-mounted")
    write(derived / "summary.json", summary)
    before = tree_hash(tmp_path)
    forbid_execution(monkeypatch)
    report = api().collect_reuse(mask10_rescore=derived, mask10_run=original, task_ids=("basket",))
    assert not report["issues"]
    dropped = report["episodes"]["basket_s001_10"]
    assert dropped["legacy"]["classification"] == "failure"
    assert dropped["primary"]["classification"] == "success"
    assert dropped["source"]["input_evidence_level"] == "support_v2_report_with_bound_metadata"
    assert dropped["primary"]["legacy_confirmed_events"][0]["event"] == "table_drop"
    assert {r["kind"] for r in dropped["source"]["verified_files"]} >= {
        "batch", "plan", "task_run", "support_v2_summary", "support_v2_episode"}
    assert report["episodes"]["basket_s002_10"]["primary"]["failure_reasons"] == ["wrong_grasp"]
    assert tree_hash(tmp_path) == before
    artifact = derived / next(ref["path"] for ref in summary["derived_episodes"] if ref["episode_id"] == "basket_s001_10")
    artifact.write_bytes(artifact.read_bytes() + b" ")
    rejected = api().collect_reuse(mask10_rescore=derived, mask10_run=original, task_ids=("basket",))
    assert rejected["episodes"]["basket_s001_10"]["primary"]["classification"] == "missing"
    assert rejected["issues"]


def test_raw_only_reuse_verifies_episode_evidence_and_exposes_its_file_dependencies(tmp_path, monkeypatch):
    from tests.test_headless_support_rescore import make_old_batch
    original = make_old_batch(tmp_path, monkeypatch)
    before = tree_hash(tmp_path)
    forbid_execution(monkeypatch)
    report = api().collect_reuse(mask10_run=original, task_ids=("basket",))
    assert not report["issues"]
    record = report["episodes"]["basket_s000_10"]
    assert record["primary"]["classification"] == "success"
    assert record["source"]["raw"]["recorded_sha256"] == record["source"]["raw"]["verified_file_sha256"]
    assert {ref["kind"] for ref in record["source"]["verified_files"]} >= {"raw", "execution_evidence", "observation"}
    assert tree_hash(tmp_path) == before


def test_013_relocation_cannot_select_another_batch(tmp_path, monkeypatch):
    from tests.test_headless_support_rescore import make_old_batch
    from benchmark.remaining_goals.headless import rescore
    original = make_old_batch(tmp_path, monkeypatch)
    derived = tmp_path / "derived"
    rescore.rescore_batch(original, derived)
    different = tmp_path / "different"
    write(different / "batch.json", {"different": "run"})
    report = api().collect_reuse(mask10_rescore=derived, mask10_run=different, task_ids=("basket",))
    assert report["issues"] and "hash" in report["issues"][0]["reason"]
    assert all(r["primary"]["classification"] == "missing" for r in report["episodes"].values())


def test_reuse_inventory_never_contains_removed_tasks_or_new_executable_tasks():
    report = api().collect_reuse()
    assert len(report["episodes"]) == 120
    assert {r["primary"]["task_id"] for r in report["episodes"].values()} == {
        "basket", "basket_cheese_butter", "stove", "dual_mugs", "mug_pudding", "basket_soup_cheese"}
    assert all(r["primary"]["classification"] == "missing" for r in report["episodes"].values())
    with pytest.raises(ValueError, match="historical"):
        api().collect_reuse(task_ids=("frypan_stove3",))
