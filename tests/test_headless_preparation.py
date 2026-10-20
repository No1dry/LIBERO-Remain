"""CPU-only command accounting; no native environment or policy is created."""
import json
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.headless import preparation as p
from benchmark.remaining_goals.headless import preparation_worker as worker


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def install_module(monkeypatch, command, main):
    module = SimpleNamespace()
    calls = []

    def step(*args, **kwargs):
        calls.append((args, kwargs))
        if kwargs.get("fail"):
            raise ValueError("failure after unknown physical progress")
        return args[-1] if args else "value"

    if command == "build":
        module._step = step
    else:
        module.ReplayAuditEnv = type("FakeReplay", (), {"step": step})
    module.main = lambda argv: main(module, argv)
    original = worker.importlib.import_module
    monkeypatch.setattr(worker.importlib, "import_module", lambda name: module if name == worker.MODULES[command] else original(name))
    return module, step, calls


@pytest.mark.parametrize("command", ["build", "replay"])
def test_success_counts_exact_original_calls_and_restores(monkeypatch, tmp_path, command):
    action = np.arange(7, dtype=np.float64)
    expected = action.copy()
    arguments = ["--out", "some unchanged path"]

    def main(module, argv):
        assert argv == arguments
        step = module._step if command == "build" else module.ReplayAuditEnv().step
        for _ in range(3):
            assert step(action) is action

    module, original, calls = install_module(monkeypatch, command, main)
    before_random, before_numpy = random.getstate(), np.random.get_state()
    path = tmp_path / "ledger.json"
    result = worker.run_command(command, arguments, path)
    assert random.getstate() == before_random
    after_numpy = np.random.get_state()
    assert after_numpy[0] == before_numpy[0] and np.array_equal(after_numpy[1], before_numpy[1])
    assert after_numpy[2:] == before_numpy[2:]
    assert np.array_equal(action, expected) and len(calls) == 3
    assert all(args[-1] is action for args, _ in calls)
    assert (module._step if command == "build" else module.ReplayAuditEnv.step) is original
    assert result["status"] == "completed" and result["finalized"]
    summary = worker.ledger_summary(path, command=command, argv=arguments, exit_code=0)
    assert summary["attempted"] == summary["completed"] == summary["actual_control_steps"] == 3
    assert summary["exception_calls"] == 0 and summary["count_status"] == "complete"
    assert summary["worker_elapsed_seconds"] >= 0


@pytest.mark.parametrize("error", [ValueError("bad"), KeyboardInterrupt(), SystemExit(3)])
def test_exception_retains_partial_counts_and_restores_hook(monkeypatch, tmp_path, error):
    module, original, calls = install_module(monkeypatch, "build", lambda *_: None)

    def original_step(action):
        calls.append(action)
        if len(calls) == 2:
            raise error
        return action

    module._step = original_step
    module.main = lambda argv: [module._step(i) for i in range(5)]
    path = tmp_path / "ledger.json"
    with pytest.raises(type(error)):
        worker.run_command("build", [], path)
    assert module._step is original_step and calls == [0, 1]
    result = read(path)
    assert result["hook_restored"] and result["finalized"]
    assert result["control_steps"]["attempted"] == 2
    assert result["control_steps"]["completed"] == result["control_steps"]["exception_calls"] == 1
    summary = worker.ledger_summary(path, command="build", argv=[], exit_code=result["exit_code"])
    assert summary["count_status"] == "partial_unknown" and summary["actual_control_steps"] is None


def test_caught_call_error_is_still_unknown_on_successful_cli(monkeypatch, tmp_path):
    def main(module, argv):
        module._step("a")
        try:
            module._step("b", fail=True)
        except ValueError:
            pass
        module._step("c")
    _, _, calls = install_module(monkeypatch, "build", main)
    result = worker.run_command("build", [], tmp_path / "ledger.json")
    assert len(calls) == 3 and result["exit_code"] == 0
    assert result["count_status"] == "partial_unknown" and result["actual_control_steps"] is None


@pytest.mark.parametrize("fault", ["missing", "running", "command", "arguments", "exit", "counts", "certainty"])
def test_unfinished_or_mismatched_ledger_cannot_claim_zero(monkeypatch, tmp_path, fault):
    install_module(monkeypatch, "build", lambda module, argv: module._step("a"))
    path = tmp_path / "ledger.json"
    value = worker.run_command("build", [], path)
    if fault == "missing":
        path.unlink()
    else:
        if fault == "running":
            value.update(finalized=False, status="running")
        elif fault == "command":
            value["command"] = "replay"
        elif fault == "arguments":
            value["arguments"] = ["--other"]
        elif fault == "exit":
            value["exit_code"] = 3
        elif fault == "counts":
            value["control_steps"]["attempted"] = 2
        else:
            value["actual_control_steps"] = 0
        path.write_text(json.dumps(value), encoding="utf-8")
    summary = worker.ledger_summary(path, command="build", argv=[], exit_code=0)
    assert summary["count_status"] == "unknown"
    assert summary["actual_control_steps"] is summary["attempted"] is summary["completed"] is None


def test_import_failure_is_saved_and_existing_ledger_cannot_be_retried(monkeypatch, tmp_path):
    def fail(name):
        raise ImportError("native unavailable")
    monkeypatch.setattr(worker.importlib, "import_module", fail)
    path = tmp_path / "ledger.json"
    with pytest.raises(ImportError):
        worker.run_command("build", [], path)
    original = path.read_bytes()
    assert read(path)["count_status"] == "unknown"
    with pytest.raises(ValueError, match="overwrite"):
        worker.run_command("build", [], path)
    assert path.read_bytes() == original


def test_forced_child_exit_preserves_running_unknown_evidence(tmp_path):
    path = tmp_path / "killed.json"
    # A real child demonstrates that even abrupt termination cannot turn the
    # startup zero placeholders into a reported zero physical-step count.
    code = """import os, sys, types
from benchmark.remaining_goals.headless.preparation_worker import run_command
m = types.ModuleType('benchmark.remaining_goals.build')
m._step = lambda action: action
def main(argv):
    m._step(1)
    os._exit(9)
m.main = main
sys.modules[m.__name__] = m
run_command('build', [], sys.argv[1])
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(path)], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=30)
    assert result.returncode == 9, result.stderr
    assert read(path)["status"] == "running"
    summary = worker.ledger_summary(path, command="build", argv=[], exit_code=9)
    assert summary["count_status"] == "unknown" and summary["actual_control_steps"] is None


def test_commands_keep_existing_cli_arguments_and_fixed_offline_counts(tmp_path):
    command = p.commands("basket", tmp_path / "data", tmp_path / "reports", python="python3.10")
    assert command[0][:3] == ["python3.10", "-m", "benchmark.remaining_goals.headless.preparation_worker"]
    assert command[0][5:] == ["build", "--out", str(tmp_path / "data/basket"), "--tasks", "basket",
                              "--scenes", "10", "--start-index", "0", "--split", "test"]
    assert command[1][5:] == ["replay", "--manifest", str(tmp_path / "data/basket/manifest.candidates.json"),
                              "--out", str(tmp_path / "reports/basket/replay"), "--steps", "150", "--repeats", "2"]


@pytest.mark.parametrize("failed_mode", ["exit", "missing_ledger", "unknown_step"])
def test_prepare_task_isolation_no_retry_and_per_command_counts(monkeypatch, tmp_path, failed_mode):
    tasks = list(p.COMMON_TEN_TASKS[:2])
    monkeypatch.setattr(p, "COMMON_TEN_TASKS", tasks)
    monkeypatch.setattr(p, "source_plan", lambda *args: {"source_plan_sha256": "a" * 64,
                                                      "candidate_replay_evidence": {"summary": {"passed": True}}})
    launches = []

    class Process:
        def __init__(self, command, **kwargs):
            launches.append(command)
            task = Path(command[4]).parent.name
            kind, args = command[5], command[6:]
            self.returncode = 0
            if task == tasks[0] and failed_mode == "missing_ledger":
                return
            def main(module, argv):
                step = module._step if kind == "build" else module.ReplayAuditEnv().step
                for i in range(2 if kind == "build" else 3):
                    step(i)
                if task == tasks[0]:
                    if failed_mode == "exit":
                        raise SystemExit(2)
                    try:
                        step(9, fail=True)
                    except ValueError:
                        pass
            install_module(monkeypatch, kind, main)
            try:
                worker.run_command(kind, args, command[4])
            except SystemExit as error:
                self.returncode = error.code
        def wait(self):
            return self.returncode

    monkeypatch.setattr(p.subprocess, "Popen", Process)
    data, reports = tmp_path / "data", tmp_path / "reports"
    result = p.prepare(data, reports)
    assert result["tasks"][tasks[0]]["status"] == "preparation_error"
    assert result["tasks"][tasks[1]]["status"] == "ready"
    assert len(launches) == 3
    valid = result["tasks"][tasks[1]]["commands"]
    assert [row["control_steps"]["actual_control_steps"] for row in valid] == [2, 3]
    assert all(row["elapsed_seconds"] >= 0 for row in valid)
    assert read(reports / "preparation.json") == result
    previous = (reports / "preparation.json").read_bytes()
    assert p.prepare(data, reports) == result and len(launches) == 3
    assert (reports / "preparation.json").read_bytes() == previous


def test_worker_cli_delegates_without_changing_arguments(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(worker, "run_command", lambda *args: calls.append(args))
    path = tmp_path / "steps.json"
    worker.main(["--ledger", str(path), "build", "--out", "target", "--scenes", "10"])
    assert calls == [("build", ["--out", "target", "--scenes", "10"], path)]
