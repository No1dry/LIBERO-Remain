"""User-started, task-isolated reuse of existing construction and replay CLIs."""
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from .planning import COMMON_TEN_TASKS, TASK_TRACKS, TASKS, read_json, source_plan
from .workflow import write_json
from .preparation_worker import ledger_summary


def commands(task, data, reports, *, python=None):
    """All-mask state preparation is offline; model selection remains mask10."""
    python = sys.executable if python is None else python
    return [[python, "-m", "benchmark.remaining_goals.headless.preparation_worker", "--ledger",
             str(Path(reports) / task / "00.control_steps.json"), "build", "--out", str(Path(data) / task),
             "--tasks", task, "--scenes", "10", "--start-index", "0", "--split", "test"],
            [python, "-m", "benchmark.remaining_goals.headless.preparation_worker", "--ledger",
             str(Path(reports) / task / "01.control_steps.json"), "replay", "--manifest",
             str(Path(data) / task / "manifest.candidates.json"), "--out", str(Path(reports) / task / "replay"),
             "--steps", "150", "--repeats", "2"]]


def prepare(data, reports, *, track="all"):
    if track not in {"all", "primary", "extension"}:
        raise ValueError("select primary/extension/all")
    data, reports = Path(data).resolve(), Path(reports).resolve()
    if data == reports or data in reports.parents or reports in data.parents:
        raise ValueError("state and preparation report roots must be separate")
    report_path = reports / "preparation.json"
    identity = {"schema_version": "remaining-headless-preparation-v2", "data": str(data),
                "reports": str(reports), "tasks": list(COMMON_TEN_TASKS), "initial_state_indices": list(range(10)),
                "masks": ["00", "10", "01", "11"], "policy_called": False, "model_rollouts": 0}
    if report_path.exists():
        report = read_json(report_path)
        if report.get("identity") != identity:
            raise ValueError("preparation identity differs; no overwrite/retry")
    else:
        if data.exists() or reports.exists():
            raise ValueError("preparation roots must be new or belong to this recorded preparation")
        data.mkdir(parents=True)
        reports.mkdir(parents=True)
        report = {"identity": identity, "tasks": {}, "notice": "Real state construction/replay only; user starts this command. Construction physical steps and elapsed time remain separate from the 100 model rollouts."}
        write_json(report_path, report)
    selected = COMMON_TEN_TASKS if track == "all" else TASK_TRACKS[track]["tasks"]
    root = Path(__file__).resolve().parents[3]
    for task in selected:
        if task in report["tasks"]:
            # Preserve all prior errors and partial trees; no automatic retry.
            continue
        destination = reports / task
        destination.mkdir(exist_ok=False)
        source = {"manifest": str(data / task / "manifest.candidates.json"),
                  "candidate_replay": str(destination / "replay/replay_report.json")}
        row = {"task_id": task, "suite": TASKS[task]["suite"], "status": "starting",
               "started_at_utc": datetime.now(timezone.utc).isoformat(), "commands": [], "source": source}
        report["tasks"][task] = row
        write_json(report_path, report, update=True)
        started = perf_counter()
        try:
            for index, command in enumerate(commands(task, data, reports)):
                command_row = {"argv": command, "log": f"{task}/{index:02d}.log", "exit_code": None,
                               "control_ledger": f"{task}/{index:02d}.control_steps.json",
                               "control_steps": {"count_status": "unknown", "actual_control_steps": None}}
                row["commands"].append(command_row)
                write_json(report_path, report, update=True)
                command_started = perf_counter()
                try:
                    with (reports / command_row["log"]).open("x", encoding="utf-8") as log:
                        log.write("cwd: " + str(root) + "\nargv: " + repr(command) + "\n")
                        log.flush()
                        process = subprocess.Popen(command, cwd=root, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
                        try:
                            code = process.wait()
                        except BaseException:
                            process.terminate()
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=10)
                            command_row["exit_code"] = process.returncode
                            raise
                        command_row["exit_code"] = code
                        log.write(f"\ncommand_exit={code}\n")
                finally:
                    command_row["elapsed_seconds"] = perf_counter() - command_started
                    command_row["control_steps"] = ledger_summary(reports / command_row["control_ledger"],
                        command=command[5], argv=command[6:], exit_code=command_row["exit_code"])
                    write_json(report_path, report, update=True)
                if code:
                    raise RuntimeError(f"preparation command {index} failed with exit {code}")
                if command_row["control_steps"]["count_status"] != "complete":
                    raise RuntimeError(f"preparation command {index} lacks complete physical control-step evidence")
            bound = source_plan(task, source)
            row.update(status="ready", source_plan_sha256=bound["source_plan_sha256"],
                       independent_replay=bound["candidate_replay_evidence"]["summary"])
        except BaseException as error:
            row.update(status="preparation_error", error=f"{type(error).__name__}: {error}")
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            row["elapsed_seconds"] = perf_counter() - started
            write_json(report_path, report, update=True)
    return report
