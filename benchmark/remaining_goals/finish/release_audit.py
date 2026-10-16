"""Task009: independently invoked, evaluator-only replay of a frozen prefix.

``plan`` verifies files only. ``run`` is a user-started native diagnostic, with
no policy, head, processor, FINISH, new release label or calibration path.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

from ..pilot_evidence import observation_sha256
from ..runner import _observation
from .schema import validate_evaluator_state
from .workflow import file_sha, write_json

SCHEMA = "remaining-release-observability-audit-v1"
FROZEN_IMPLEMENTATION = "3433f487d38efe0a08e4c814e87412aad5aba9fe"
_LEDGER_KEYS = {"step", "action", "action_kind", "hold_cause", "query_sequence", "chunk_index"}


def load_plan(path):
    from .release_audit_plan import load_plan as read
    return read(path)


def _default_env(config):
    from .environment import FinishLiberoEnv
    return FinishLiberoEnv(config)


def _default_monitor():
    from .release_audit_native import NativeCallMonitor
    return NativeCallMonitor()


def _default_recorder(env, output, *, backend):
    from .release_audit_native import NativeRecorder
    return NativeRecorder(env, output, backend=backend)


def _digest_array(value):
    array = np.asarray(value)
    return {"dtype": array.dtype.str, "shape": list(array.shape),
            "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest()}


def _difference(expected, actual, field):
    """Strict old JSON-value comparison, including signed zero float bits."""
    if type(expected) is not type(actual):
        return {"field": field, "expected": expected, "actual": actual}
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return {"field": field + ".keys", "expected": sorted(expected), "actual": sorted(actual)}
        for key in sorted(expected):
            mismatch = _difference(expected[key], actual[key], field + "." + key)
            if mismatch is not None:
                return mismatch
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return {"field": field + ".length", "expected": len(expected), "actual": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            mismatch = _difference(left, right, f"{field}[{index}]")
            if mismatch is not None:
                return mismatch
    elif isinstance(expected, float):
        if struct.pack("!d", expected) != struct.pack("!d", actual):
            return {"field": field, "expected": expected, "actual": actual,
                    "expected_float64_hex": struct.pack("!d", expected).hex(),
                    "actual_float64_hex": struct.pack("!d", actual).hex()}
    elif expected != actual:
        return {"field": field, "expected": expected, "actual": actual}
    return None


def _output_path(output, plan_path, context):
    out = Path(output).resolve()
    roots = [Path(plan_path).resolve().parent]
    plan = context["plan"]
    roots.extend(Path(value).resolve() for value in plan.get("protected_roots", []))
    if plan.get("source_run"):
        roots.append(Path(plan["source_run"]).resolve())
    if plan.get("source_bank"):
        roots.append(Path(plan["source_bank"]).resolve().parent)
    if any(out == root or root in out.parents for root in roots):
        raise ValueError("diagnostic output must be outside source run, bank and plan trees")
    out.mkdir(parents=True, exist_ok=False)
    return out


def _manifest(output):
    entries = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("diagnostic output contains a symlink")
        if path.is_file() and path.name != "manifest.json":
            entries.append({"path": path.relative_to(output).as_posix(),
                            "bytes": path.stat().st_size, "sha256": file_sha(path)})
    value = {"schema_version": SCHEMA, "files": entries,
             "scope": "all diagnostic files except this manifest itself; source files remain untouched"}
    write_json(output / "manifest.json", value)


def run(plan_path, output, *, env_factory=None, recorder_factory=None, monitor_factory=None):
    """USER native entry. Factory injection exists solely for CPU fake tests."""
    context = load_plan(plan_path)  # Recheck all frozen files before any native construction.
    plan = context["plan"]
    count = plan["max_action_steps"]
    if type(count) is not int or not 1 <= count <= 292:
        raise ValueError("task009 permits only a prefix of 1..292 original actions")
    actions = context["actions"]
    if (not isinstance(actions, np.ndarray) or actions.dtype != np.dtype("float64")
            or actions.shape != (count, 7) or not np.isfinite(actions).all()):
        raise ValueError("plan actions must be the original finite float64 (N,7) prefix")
    out = _output_path(output, plan_path, context)
    report = {"schema_version": SCHEMA, "status": "technical_error",
              "plan_sha256": plan["plan_sha256"], "source_implementation": FROZEN_IMPLEMENTATION,
              "episode_id": context["episode"]["episode_id"], "requested_action_steps": count,
              "attempted_action_steps": 0, "completed_action_steps": 0, "snapshot_count": 0,
              "query_comparisons": [], "first_mismatch": None, "error": None,
              "interrupted": False,
              "phase": "monitor_setup", "cleanup_errors": [], "native_calls": None,
              "forbidden_calls": {"vla_forward": 0, "head_inference": 0, "processor": 0},
              "physical_truth_comparisons": 0, "manifest": "manifest.json",
              "comparison": {"floats": "float64 bitwise, including signed zero", "atol": 0, "rtol": 0,
                             "observation": "original whitelisted raw array dtype/shape/bytes"},
              "scope": "new replay diagnostic snapshots; no new labels, score, threshold or original native-state claim"}
    write_json(out / "summary.json", report)
    write_json(out / "source_plan.json", plan)
    env = recorder = monitor = None
    monitor_entered = False
    env_factory = _default_env if env_factory is None else env_factory
    recorder_factory = _default_recorder if recorder_factory is None else recorder_factory
    monitor_factory = _default_monitor if monitor_factory is None else monitor_factory

    def checkpoint():
        write_json(out / "summary.json", report, update=True)

    def compare_frame(step, raw, action=None, action_error=None):
        # Preserve the frozen runner's ordering: reset validates observation
        # before evaluator; ordinary steps evaluate before observation validation.
        if step == 0:
            observation = _observation(raw)
            truth = validate_evaluator_state(env.evaluator_state(), len(context["episode"]["initial_mask"]))
        else:
            truth = validate_evaluator_state(env.evaluator_state(), len(context["episode"]["initial_mask"]))
            observation = _observation(raw)
        original = context["trace"][step]
        expected_truth = {key: deepcopy(value) for key, value in original.items() if key not in _LEDGER_KEYS}
        mismatch = action_error
        truth_difference = _difference(expected_truth, truth, "truth")
        if truth_difference is not None and mismatch is None:
            mismatch = {"kind": "truth", "step": step, **truth_difference}
        report["physical_truth_comparisons"] += 1
        actual_hash = observation_sha256(observation)
        if step == 0 and actual_hash != context["initial_observation_sha256"] and mismatch is None:
            mismatch = {"kind": "observation", "step": step, "field": "initial_observation_sha256",
                        "expected": context["initial_observation_sha256"], "actual": actual_hash}
        query = context["query_by_step"].get(step)
        query_reference = None
        if query is not None:
            query_reference = {key: query[key] for key in ("sequence", "observation_step", "observation_sha256")}
            comparison = {**query_reference, "actual_observation_sha256": actual_hash,
                          "matched": query["observation_sha256"] == actual_hash}
            report["query_comparisons"].append(comparison)
            if not comparison["matched"] and mismatch is None:
                mismatch = {"kind": "observation", "step": step, "field": "query.observation_sha256",
                            "expected": query["observation_sha256"], "actual": actual_hash}
        source_action = None if step == 0 else deepcopy(context["source_result"]["executed_actions"][step - 1])
        action_kind = "initial" if step == 0 else "policy"
        # Root owns the source ledger. Belonging to query37's action chunk at
        # step292 does not create a query or an observation comparison there.
        frame = {"schema_version": SCHEMA, "step": step, "action_kind": action_kind,
                 "source_action": source_action, "query_reference": query_reference,
                 "observation_sha256": actual_hash, "truth": truth, "mismatch": mismatch, "native": None}
        if mismatch is not None:
            report["first_mismatch"] = mismatch
        write_json(out / "frames" / f"{step:04d}.json", frame)
        report["phase"] = "recorder_capture"
        monitor.set_phase("recorder")
        frame["native"] = recorder.capture(step, action_kind=action_kind,
            query_index=query["sequence"] if query else None,
            action=None if action is None else action.copy(), truth=deepcopy(truth))
        write_json(out / "frames" / f"{step:04d}.json", frame, update=True)
        report["snapshot_count"] += 1
        if mismatch is not None:
            report.update(status="replay_mismatch", first_mismatch=mismatch, phase="comparison")
        checkpoint()
        return mismatch is None

    try:
        monitor = monitor_factory()
        monitor.__enter__()
        monitor_entered = True
        monitor.set_phase("initialization")
        report["phase"] = "environment_setup"
        env = env_factory(deepcopy(context["environment_config"]))
        report["phase"] = "reset"
        raw = env.reset(deepcopy(context["episode"]))
        report["phase"] = "recorder_setup"
        monitor.set_phase("recorder")
        recorder = recorder_factory(env, out, backend=monitor.backend)
        static = recorder.static()
        if static.get("compiled_model_xml_sha256") != context["episode"]["model_xml_sha256"]:
            raise ValueError("sidecar compiled model XML differs from the frozen episode")
        report["static"] = {"path": "static.json", "artifact": static.get("artifact"),
                            "compiled_model_xml_sha256": static["compiled_model_xml_sha256"],
                            "read_only": static.get("read_only")}
        report["phase"] = "initial_comparison"
        if compare_frame(0, raw):
            for step in range(1, count + 1):
                report["phase"] = "action_validation"
                original = context["source_result"]["executed_actions"][step - 1]
                action = actions[step - 1].copy()
                saved = np.asarray(original["action"], dtype=np.float64)
                expected_ledger = {"step": step, "action_kind": "policy", "hold_cause": None,
                                   "query_sequence": (step - 1) // 8 + 1, "chunk_index": (step - 1) % 8}
                actual_ledger = {key: original.get(key) for key in expected_ledger}
                difference = _difference(expected_ledger, actual_ledger, "action.ledger")
                if difference is None and (saved.shape != (7,) or action.tobytes() != saved.tobytes()):
                    difference = {"field": "action.bytes", "expected": _digest_array(saved), "actual": _digest_array(action)}
                if difference is not None:
                    report.update(status="replay_mismatch", first_mismatch={"kind": "action", "step": step, **difference})
                    break
                attempt = {"step": step, "source_action": deepcopy(original), "action": _digest_array(action),
                           "env_step_returned": False}
                write_json(out / "actions" / f"{step:04d}.json", attempt)
                report["attempted_action_steps"] = step
                report["phase"] = "action"
                checkpoint()
                monitor.set_phase("action")
                raw = env.step(action)
                report["completed_action_steps"] = step
                attempt["env_step_returned"] = True
                write_json(out / "actions" / f"{step:04d}.json", attempt, update=True)
                action_error = None
                if action.dtype != np.dtype("float64") or action.shape != (7,) or action.tobytes() != saved.tobytes():
                    action_error = {"kind": "action", "step": step, "field": "env.step.input_mutation",
                                    "expected": _digest_array(saved), "actual": _digest_array(action)}
                last_action = getattr(env, "_last_action", None)
                if last_action is not None and action_error is None:
                    actual = np.asarray(last_action)
                    if actual.dtype != np.dtype("float64") or actual.shape != (7,) or actual.tobytes() != saved.tobytes():
                        action_error = {"kind": "action", "step": step, "field": "env._last_action",
                                        "expected": _digest_array(saved), "actual": _digest_array(actual)}
                report["phase"] = "frame_comparison"
                monitor.set_phase("recorder")
                if not compare_frame(step, raw, saved, action_error):
                    break
            else:
                report.update(status="diagnostic_completed", phase="completed")
    except BaseException as error:
        report.update(status="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "technical_error",
                      interrupted=isinstance(error, (KeyboardInterrupt, SystemExit)),
                      error=f"{type(error).__name__}: {error}")
    finally:
        if monitor_entered:
            try:
                monitor.set_phase("cleanup")
            except BaseException as error:
                report["cleanup_errors"].append(f"monitor cleanup phase: {type(error).__name__}: {error}")
                report["interrupted"] = report["interrupted"] or isinstance(error, (KeyboardInterrupt, SystemExit))
        for name, resource in (("recorder", recorder), ("environment", env)):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    report["cleanup_errors"].append(f"{name} close: {type(error).__name__}: {error}")
                    report["interrupted"] = report["interrupted"] or isinstance(error, (KeyboardInterrupt, SystemExit))
        if monitor_entered:
            try:
                monitor.__exit__(None, None, None)
            except BaseException as error:
                report["cleanup_errors"].append(f"monitor close: {type(error).__name__}: {error}")
                report["interrupted"] = report["interrupted"] or isinstance(error, (KeyboardInterrupt, SystemExit))
        if monitor is not None:
            try:
                report["native_calls"] = monitor.summary()
            except BaseException as error:
                report["cleanup_errors"].append(f"monitor summary: {type(error).__name__}: {error}")
                report["interrupted"] = report["interrupted"] or isinstance(error, (KeyboardInterrupt, SystemExit))
        if report["cleanup_errors"]:
            report["status"] = "interrupted" if report["interrupted"] else "technical_error"
            report["error"] = report["error"] or report["cleanup_errors"][0]
        checkpoint()
        try:
            _manifest(out)
        except BaseException as error:
            report["interrupted"] = report["interrupted"] or isinstance(error, (KeyboardInterrupt, SystemExit))
            report.update(status="interrupted" if report["interrupted"] else "technical_error",
                          phase="manifest", manifest=None,
                          error=f"manifest: {type(error).__name__}: {error}")
            checkpoint()
    return report


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="pure-file verification of the fixed init35 source prefix")
    plan.add_argument("--source-run", required=True)
    plan.add_argument("--episode-id", default="basket_s035_00", choices=["basket_s035_00"])
    plan.add_argument("--max-action-steps", type=int, default=292)
    plan.add_argument("--out", required=True)
    native = commands.add_parser("run", help="USER native diagnostic from a frozen plan, no model inference")
    native.add_argument("--plan", required=True)
    native.add_argument("--out", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            from .release_audit_plan import create_plan
            result = create_plan(args.source_run, args.episode_id, args.max_action_steps, args.out)
        else:
            result = run(args.plan, args.out)
        status = result["status"]
        print(json.dumps({"status": status, "out": str(Path(args.out).resolve()),
                          "error": result.get("error"), "first_mismatch": result.get("first_mismatch")},
                         ensure_ascii=False, allow_nan=False))
        return 0 if status in {"plan_ready", "diagnostic_completed"} else 130 if status == "interrupted" else 2
    except (KeyboardInterrupt, SystemExit) as error:
        print(json.dumps({"status": "interrupted", "error": f"{type(error).__name__}: {error}"}))
        return 130
    except Exception as error:
        print(json.dumps({"status": "technical_error", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
