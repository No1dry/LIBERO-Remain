"""Bounded preparation orchestration, using CPU fakes at native boundaries."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


TASK = "frypan_stove9"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def setup_inventory(tmp_path, entries):
    from benchmark.remaining_goals.headless.scoped_planning import expected_episodes
    path = tmp_path / "inventory.json"
    write(path, {"schema_version": "remaining-headless-composite-sources-v1",
                 "protocol": "selected-mask10", "expected": expected_episodes("selected-mask10"), "entries": entries})
    return path


def entry(index, **origin):
    return {"task_id": TASK, "initial_state_index": index, "origin": origin or None}


def fake_sources(monkeypatch, module):
    def resolve(protocol, task, index, origin):
        if origin.get("ready"):
            return {"episodes": [{"episode_id": f"{task}_{index}"}], "source_acceptance": {"evidence_sha256": "a" * 64}}
        if origin.get("failed"):
            raise ValueError("selected replay explicitly failed")
        raise FileNotFoundError("missing replay")

    def inspect(task, index, manifest):
        if manifest == "failed":
            raise ValueError("construction explicitly failed")
        return {"episode": {"episode_id": f"{task}_{index}"}}

    monkeypatch.setattr(module, "_sources", lambda: SimpleNamespace(resolve_source=resolve, inspect_candidate=inspect))


def test_ready_has_zero_native_work_and_full_expected_twenty(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    monkeypatch.setattr(p, "_native", lambda *a, **k: pytest.fail("ready source invoked native work"))
    inventory = setup_inventory(tmp_path, [entry(3, manifest="old.json", ready=True)])
    report = p.prepare(inventory, tmp_path / "out", mode="prepare-missing", indices=[3], tasks=[TASK])
    assert len(report["expected"]) == 20
    assert report["sources"][0]["status"] == "ready"
    assert report["sources"][0]["actual_control_steps"] == 0
    assert json.loads((tmp_path / "out" / "sources.json").read_text())["entries"][0]["origin"]["ready"] is True


def test_missing_replay_reuses_original_manifest_without_build(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    calls = []

    def native(operation, task, index, origin, output, protocol):
        calls.append((operation, index, origin["manifest"]))
        return {**origin, "ready": True}, {"actual_control_steps": 300, "count_status": "complete"}

    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [entry(7, manifest="original.json")])
    report = p.prepare(inventory, tmp_path / "out", mode="prepare-missing", indices=[7], tasks=[TASK])
    assert calls == [("replay", 7, str(tmp_path / "original.json"))]
    assert report["sources"][0]["status"] == "ready"
    assert report["sources"][0]["candidate"] == "existing"
    assert report["sources"][0]["actual_control_steps"] == 300


def test_failed_existing_is_preserved_and_next_fixed_source_runs(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    calls = []

    def native(operation, task, index, origin, output, protocol):
        calls.append(index)
        return {"manifest": "new.json", "ready": True}, {"actual_control_steps": 450, "count_status": "complete"}

    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [entry(0, manifest="old.json", failed=True), entry(9)])
    report = p.prepare(inventory, tmp_path / "out", mode="prepare-missing", indices=[0, 9], tasks=[TASK])
    assert calls == [9]
    assert [r["status"] for r in report["sources"]] == ["failed", "ready"]
    assert report["sources"][0]["origin"]["manifest"] == str(tmp_path / "old.json")


def test_native_failure_isolated_and_unknown_not_zero(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)

    def native(operation, task, index, origin, output, protocol):
        if index == 1:
            raise RuntimeError("physical progress unknown")
        return {"manifest": "new.json", "ready": True}, {"actual_control_steps": 300, "count_status": "complete"}

    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    report = p.prepare(inventory, tmp_path / "out", mode="prepare-missing", indices=[1, 8], tasks=[TASK])
    assert [r["status"] for r in report["sources"]] == ["failed", "ready"]
    assert report["sources"][0]["actual_control_steps"] is None


@pytest.mark.parametrize("indices,tasks", [([10], [TASK]), ([-1], [TASK]), ([True], [TASK]), ([0, 0], [TASK]), ([0], ["basket"])])
def test_selection_cannot_escape_fixed_twenty(tmp_path, indices, tasks):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    with pytest.raises(ValueError):
        p.prepare(setup_inventory(tmp_path, []), tmp_path / "out", indices=indices, tasks=tasks)
    assert not (tmp_path / "out").exists()


def test_output_requires_explicit_continuation_and_does_not_repeat_attempt(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    calls = []

    def native(operation, task, index, origin, output, protocol):
        calls.append(index)
        raise RuntimeError("failed attempt")

    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    p.prepare(inventory, output, mode="prepare-missing", indices=[2], tasks=[TASK])
    with pytest.raises(FileExistsError):
        p.prepare(inventory, output, indices=[2], tasks=[TASK])
    p.prepare(inventory, output, mode="prepare-missing", indices=[2], tasks=[TASK], continuation=True)
    assert calls == [2]


def test_inspect_cli_does_not_import_native_modules(tmp_path):
    import subprocess
    import sys
    inventory = setup_inventory(tmp_path, [])
    code = """import sys
from benchmark.remaining_goals.headless.selected_preparation import prepare
prepare(sys.argv[1],sys.argv[2],indices=[0],tasks=['frypan_stove9'])
assert not any(n.startswith(('libero','torch','robosuite')) for n in sys.modules)
assert 'benchmark.remaining_goals.build' not in sys.modules
assert 'benchmark.remaining_goals.replay_candidates' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code, str(inventory), str(tmp_path / "out")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_build_only_can_continue_with_replay_without_repeating_build(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    calls = []
    def native(operation, task, index, origin, output, protocol):
        calls.append(operation)
        return {"manifest": "new.json", "ready": operation == "replay"}, {"actual_control_steps": 230 if operation == "build" else 300, "count_status": "complete"}
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    first = p.prepare(inventory, output, mode="build-missing", tasks=[TASK], indices=[0])
    assert first["sources"][0]["phase"] == "replay"
    result = p.prepare(inventory, output, mode="replay-missing", tasks=[TASK], indices=[0], continuation=True)
    assert calls == ["build", "replay"]
    assert result["sources"][0]["status"] == "ready"
    assert result["sources"][0]["actual_control_steps"] == 530


def test_explicit_failed_replay_retry_keeps_passing_candidate(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    calls = []
    def native(operation, task, index, origin, output, protocol):
        calls.append(operation)
        return {**origin, "ready": True, "failed": False}, {"actual_control_steps": 300, "count_status": "complete"}
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [entry(1, manifest="old.json", failed=True)])
    result = p.prepare(inventory, tmp_path / "out", mode="prepare-missing", tasks=[TASK], indices=[1], allow_failed_retry=True)
    assert calls == ["replay"]
    assert result["sources"][0]["candidate"] == "existing"
    assert result["sources"][0]["previous_attempts"][0]["status"] == "failed"


def test_preparation_composite_is_consumable_by_scoped_planner(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    from benchmark.remaining_goals.headless.scoped_planning import read_composite
    p.prepare(setup_inventory(tmp_path, []), tmp_path / "out", tasks=[TASK], indices=[0])
    value, entries = read_composite(tmp_path / "out/sources.json", "selected-mask10")
    assert len(value["expected"]) == 20 and entries == {}


@pytest.mark.parametrize("status,wanted", [("ready", 0), ("missing", 2), ("failed", 2)])
def test_preparation_cli_exit_status_exposes_unready_source(monkeypatch, tmp_path, status, wanted):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    monkeypatch.setattr(p, "prepare", lambda *args, **kwargs: {"sources": [{"task_id": TASK, "initial_state_index": 0, "status": status}]})
    assert p.main(["--inventory", str(tmp_path / "inventory.json"), "--output", str(tmp_path / "out")]) == wanted


def test_noncontiguous_continuation_retains_previously_prepared_origin(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    def native(operation, task, index, origin, output, protocol):
        return {"manifest": f"new_{index}.json", "ready": True}, {"actual_control_steps": 450, "count_status": "complete"}
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[1])
    p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[8], continuation=True)
    composite = json.loads((output / "sources.json").read_text())
    assert {row["initial_state_index"] for row in composite["entries"]} == {1, 8}


def test_unreadable_source_does_not_stop_next_source(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    source = p._sources()
    original = source.resolve_source
    def resolve(protocol, task, index, origin):
        if index == 0:
            raise PermissionError("source audit unreadable")
        return original(protocol, task, index, origin)
    source.resolve_source = resolve
    monkeypatch.setattr(p, "_sources", lambda: source)
    inventory = setup_inventory(tmp_path, [entry(0, manifest="old.json"), entry(1, manifest="ready.json", ready=True)])
    report = p.prepare(inventory, tmp_path / "out", tasks=[TASK], indices=[0, 1])
    assert [row["status"] for row in report["sources"]] == ["failed", "ready"]


@pytest.mark.parametrize("change,status,exit_code", [("changed", "failed", 2), ("deleted", "missing", 2), ("unchanged", "ready", 0)])
@pytest.mark.parametrize("mode", ["inspect", "prepare-missing"])
def test_continuation_revalidates_ready_dependency_without_native_retry(monkeypatch, tmp_path, change, status, exit_code, mode):
    import hashlib
    from copy import deepcopy
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    dependency = tmp_path / "prepared_manifest.json"
    native_calls = []

    def resolve(protocol, task, index, origin):
        raw = Path(origin["manifest"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != origin["manifest_sha256"]:
            raise ValueError("original manifest hash binding mismatch")
        return {"episodes": [{"episode_id": f"{task}_{index}"}], "source_acceptance": {"evidence_sha256": "a" * 64}}

    def inspect(task, index, path):
        Path(path).read_bytes()
        return {"episode": {"episode_id": f"{task}_{index}"}}

    def native(operation, task, index, origin, output, protocol):
        native_calls.append(operation)
        dependency.write_bytes(b"prepared original evidence")
        return {"manifest": str(dependency), "manifest_sha256": hashlib.sha256(dependency.read_bytes()).hexdigest()}, {"actual_control_steps": 450, "count_status": "complete"}

    monkeypatch.setattr(p, "_sources", lambda: SimpleNamespace(resolve_source=resolve, inspect_candidate=inspect))
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    before = deepcopy(p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[0])["sources"][0])
    assert before["status"] == "ready"
    if change == "changed":
        dependency.write_bytes(b"modified evidence")
    elif change == "deleted":
        dependency.unlink()
    result = p.prepare(inventory, output, mode=mode, tasks=[TASK], indices=[0], continuation=True)
    row = result["sources"][0]
    assert row["status"] == status
    assert row["operations"] == before["operations"]
    assert row["actual_control_steps"] == 450 and row["count_status"] == "complete"
    assert row["previous_attempts"] == before["previous_attempts"]
    assert native_calls == ["build"]
    if change != "unchanged":
        assert "acceptance" not in row
        assert row["readiness_history"][-1]["acceptance"] == before["acceptance"]
    assert p.main(["--inventory", str(inventory), "--output", str(output), "--continue", "--mode", "inspect",
                   "--tasks", TASK, "--indices", "0"]) == exit_code
    assert native_calls == ["build"]


def test_continuation_revalidates_unselected_retained_ready_origin(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    native_calls = []
    def native(operation, task, index, origin, output, protocol):
        native_calls.append(index)
        return {"manifest": "prepared.json", "ready": True}, {"actual_control_steps": 450, "count_status": "complete"}
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[1])
    source = p._sources()
    source.resolve_source = lambda *args: (_ for _ in ()).throw(FileNotFoundError("deleted evidence"))
    source.inspect_candidate = lambda *args: (_ for _ in ()).throw(FileNotFoundError("deleted state"))
    monkeypatch.setattr(p, "_sources", lambda: source)
    result = p.prepare(inventory, output, tasks=[TASK], indices=[8], continuation=True)
    assert result["sources"][0]["initial_state_index"] == 1
    assert result["sources"][0]["status"] == "missing"
    assert result["sources"][0]["actual_control_steps"] == 450
    assert native_calls == [1]


def test_invalidated_ready_candidate_does_not_trigger_implicit_replay(monkeypatch, tmp_path):
    p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    fake_sources(monkeypatch, p)
    native_calls = []
    def native(operation, task, index, origin, output, protocol):
        native_calls.append(operation)
        return {"manifest": "prepared.json", "ready": True}, {"actual_control_steps": 450, "count_status": "complete"}
    monkeypatch.setattr(p, "_native", native)
    inventory = setup_inventory(tmp_path, [])
    output = tmp_path / "out"
    p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[1])
    source = p._sources()
    source.resolve_source = lambda *args: (_ for _ in ()).throw(FileNotFoundError("deleted independent replay"))
    monkeypatch.setattr(p, "_sources", lambda: source)
    result = p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[1], continuation=True)
    assert result["sources"][0]["status"] == "missing"
    assert result["sources"][0]["phase"] == "replay"
    assert result["sources"][0]["candidate"] == "existing"
    assert native_calls == ["build"]
