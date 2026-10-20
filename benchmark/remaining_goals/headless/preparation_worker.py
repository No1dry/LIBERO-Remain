"""Count existing offline preparation control calls without changing their work.

This process invokes the existing CLI directly. A successful wrapped call is one
completed control step. A raised call may have advanced physics before raising;
its physical completion is unknown. Counts do not include reset/forward calls
or simulator integration substeps. An unfinished ledger is never a zero count.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import argparse
import hashlib
import importlib
from pathlib import Path
from time import perf_counter

from .planning import read_json
from .workflow import write_json


SCHEMA = "remaining-headless-preparation-control-ledger-v1"
MODULES = {"build": "benchmark.remaining_goals.build",
           "replay": "benchmark.remaining_goals.replay_candidates"}
SCOPE = ("Existing build._step or ReplayAuditEnv.step calls only; one normally "
         "returned call is one completed physical control step. Exceptions may "
         "occur before or after physics, so their completion is unknown. Native "
         "integration substeps and reset/forward calls are not control steps.")


@contextmanager
def count_calls(owner, attribute, counters):
    """Delegate exactly once with the original arguments; restore on every exit."""
    original = getattr(owner, attribute)

    @wraps(original)
    def counted(*args, **kwargs):
        counters["attempted"] += 1
        started = perf_counter()
        try:
            result = original(*args, **kwargs)
        except BaseException:
            counters["exception_calls"] += 1
            raise
        else:
            counters["completed"] += 1
            return result
        finally:
            counters["elapsed_seconds"] += perf_counter() - started

    setattr(owner, attribute, counted)
    try:
        yield
    finally:
        setattr(owner, attribute, original)


def run_command(command, argv, ledger_path):
    """Run an unchanged builder/replayer CLI and persist final partial counts."""
    if command not in MODULES or not isinstance(argv, list) or any(not isinstance(x, str) for x in argv):
        raise ValueError("select build/replay and a string argument list")
    ledger_path = Path(ledger_path)
    report = {"schema_version": SCHEMA, "command": command, "module": MODULES[command],
              "arguments": list(argv), "status": "running", "finalized": False,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "policy_called": False, "model_rollouts": 0, "scope": SCOPE,
              "hook_installed": False, "hook_restored": False, "exit_code": None,
              "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "control_steps": {"attempted": 0, "completed": 0, "exception_calls": 0,
                                "elapsed_seconds": 0.0},
              "count_status": "unknown", "actual_control_steps": None}
    # A preexisting ledger is evidence, not permission to retry or overwrite.
    write_json(ledger_path, report)
    started = perf_counter()
    try:
        module = importlib.import_module(MODULES[command])
        owner, attribute = (module, "_step") if command == "build" else (module.ReplayAuditEnv, "step")
        with count_calls(owner, attribute, report["control_steps"]):
            report["hook_installed"] = True
            module.main(list(argv))
        report.update(status="completed", exit_code=0)
    except BaseException as error:
        code = error.code if isinstance(error, SystemExit) else 1
        code = 0 if code is None else code if isinstance(code, int) else 1
        report.update(status="completed" if code == 0 else "failed", exit_code=code,
                      error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["hook_restored"] = report["hook_installed"]
        report["finalized"] = True
        report["elapsed_seconds"] = perf_counter() - started
        counters = report["control_steps"]
        if report["hook_installed"]:
            report["count_status"] = "partial_unknown" if counters["exception_calls"] else "complete"
            if not counters["exception_calls"]:
                report["actual_control_steps"] = counters["completed"]
        write_json(ledger_path, report, update=True)
    return report


def ledger_summary(path, *, command, argv, exit_code):
    """Do not treat missing, interrupted, or mismatched child evidence as zero."""
    path = Path(path)
    unknown = {"count_status": "unknown", "actual_control_steps": None,
               "attempted": None, "completed": None, "exception_calls": None}
    try:
        value = read_json(path)
        if (value.get("schema_version") != SCHEMA or value.get("command") != command
                or value.get("module") != MODULES[command] or value.get("arguments") != argv
                or value.get("finalized") is not True or value.get("hook_installed") is not True
                or value.get("hook_restored") is not True or value.get("exit_code") != exit_code):
            raise ValueError("ledger is unfinished or does not bind this command exit")
        counts = value["control_steps"]
        if (any(type(counts.get(key)) is not int or counts[key] < 0
                for key in ("attempted", "completed", "exception_calls"))
                or counts["attempted"] != counts["completed"] + counts["exception_calls"]):
            raise ValueError("ledger control counts are inconsistent")
        expected = "partial_unknown" if counts["exception_calls"] else "complete"
        actual = None if counts["exception_calls"] else counts["completed"]
        if value.get("count_status") != expected or value.get("actual_control_steps") != actual:
            raise ValueError("ledger misstates certainty")
        return {"count_status": expected, "actual_control_steps": actual,
                **{key: counts[key] for key in ("attempted", "completed", "exception_calls")},
                "ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "worker_elapsed_seconds": value["elapsed_seconds"], "scope": SCOPE}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {**unknown, "reason": f"{type(error).__name__}: {error}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("command", choices=MODULES)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    run_command(args.command, args.arguments, args.ledger)


if __name__ == "__main__":
    main()
