"""Explicit, bounded offline preparation for the two task031 missing tasks.

The default is file-only inspection. Non-inspect modes are native preparation
commands, never policy evaluation. Every physical operation uses a new path.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from time import perf_counter
from ..nine_catalog import NEW_TASKS, NINE_PROTOCOLS

SCHEMA = "remaining-headless-composite-sources-v1"
REPORT_SCHEMA = "remaining-headless-selected-preparation-v1"
TASKS = ("frypan_stove9", "cabinet_close_top_bowl")
PROTOCOLS = ("selected-mask10", "normal00-control", *NINE_PROTOCOLS)
MODES = ("inspect", "build-missing", "replay-missing", "prepare-missing")
R2_METHOD = "selected_A_only_bounded_settle_component_transplant_v2"
R5_METHOD = "microwave_gravity_support_pose_transplant_v3"


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sources():
    from . import scoped_sources
    return scoped_sources


def _selection(tasks, indices, protocol=None):
    allowed = NEW_TASKS if protocol in NINE_PROTOCOLS else TASKS
    tasks = list(allowed if tasks is None else tasks)
    indices = list(range(10) if indices is None else indices)
    if (not tasks or len(set(tasks)) != len(tasks) or any(task not in allowed for task in tasks)
            or not indices or any(type(index) is not int or not 0 <= index < 10 for index in indices)
            or len(set(indices)) != len(indices)):
        raise ValueError("preparation is restricted to the protocol's new fixed tasks and unique indices 0..9")
    return tasks, indices


def _origin(origin, base):
    if origin is None:
        return None
    if not isinstance(origin, dict):
        raise ValueError("source origin must be an object or null")
    result = deepcopy(origin)
    for key in ("manifest", "candidate_replay", "initialization", "rgb_certificate"):
        if key in result:
            if not isinstance(result[key], str) or not result[key]:
                raise ValueError(f"origin {key} must be a path")
            result[key] = str((base / result[key]).resolve())
    return result


def _inspect(protocol, task, index, origin):
    row = {"task_id": task, "initial_state_index": index, "origin": origin,
           "status": "missing", "phase": "candidate", "candidate": "missing",
           "constructed": False, "replayed": False, "operations": [],
           "actual_control_steps": 0, "count_status": "complete"}
    if not origin:
        row["reason"] = "no chosen source origin"
        return row
    sources = _sources()
    try:
        plan = sources.resolve_source(protocol, task, index, origin)
    except FileNotFoundError as error:
        row["reason"] = f"{type(error).__name__}: {error}"
    except (OSError, ValueError, KeyError, TypeError) as error:
        row.update(status="failed", reason=f"{type(error).__name__}: {error}")
    else:
        row.update(status="ready", phase="complete", candidate="existing",
                   episode_id=plan["episodes"][0]["episode_id"], acceptance=plan["source_acceptance"])
        return row
    if protocol in ("selected-mask10", "nine-mask10"):
        try:
            options = {"protocol": protocol} if protocol in NINE_PROTOCOLS else {}
            if origin.get("rgb_certificate"):
                options["rgb_certificate"] = origin["rgb_certificate"]
            candidate = sources.inspect_candidate(task, index, origin["manifest"], **options)
        except FileNotFoundError:
            return row
        except (OSError, ValueError, KeyError, TypeError) as error:
            row.update(status="failed", reason=f"{type(error).__name__}: {error}")
        else:
            row.update(candidate="existing", episode_id=candidate["episode"]["episode_id"], phase="replay")
    return row


def _run_counted(function, owner, attribute, path, identity):
    """Count physical calls, retaining unknown progress after any raised call."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite control ledger {path}")
    report = {"schema_version": "remaining-headless-selected-control-ledger-v1", **identity,
              "finalized": False, "hook_installed": False, "hook_restored": False,
              "attempted": 0, "completed": 0, "exception_calls": 0,
              "count_status": "unknown", "actual_control_steps": None,
              "policy_called": False, "model_rollouts": 0,
              "scope": "Control calls only; reset/forward and native integration substeps excluded.",
              "worker_sha256": _hash(Path(__file__).read_bytes())}
    _write(path, report)
    started = perf_counter()
    original = getattr(owner, attribute)

    def counted(*args, **kwargs):
        report["attempted"] += 1
        try:
            result = original(*args, **kwargs)
        except BaseException:
            report["exception_calls"] += 1
            raise
        else:
            report["completed"] += 1
            return result

    try:
        setattr(owner, attribute, counted)
        report["hook_installed"] = True
        result = function()
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        # Retain the exact ledger even when orchestration isolates this source.
        error.control_ledger = report
        raise
    finally:
        setattr(owner, attribute, original)
        report["hook_restored"] = True
        report["finalized"] = True
        report["elapsed_seconds"] = perf_counter() - started
        report["count_status"] = "partial_unknown" if report["exception_calls"] else "complete"
        report["actual_control_steps"] = None if report["exception_calls"] else report["completed"]
        _write(path, report)
    return result, report


def _native(operation, task, index, origin, output, protocol, *, construction_method=None,
            observation_profile=None, stability_profile=None):
    """Lazy native boundary. Called only by an explicitly selected native mode."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    identity = {"operation": operation, "protocol": protocol, "task_id": task,
                "initial_state_index": index, "output": str(output)}
    if construction_method is not None:
        identity["construction_method"] = construction_method
    if observation_profile is not None:
        identity["observation_profile"] = observation_profile
    if stability_profile is not None:
        identity["stability_profile"] = stability_profile
    ledger_path = output.with_name(output.name + ".control_ledger.json")
    # Import errors before a hook is installed leave unknown evidence, never 0.
    try:
        if operation == "build":
            producer = importlib.import_module("benchmark.remaining_goals.selected_build")
            owner = importlib.import_module("benchmark.remaining_goals.build")
            options = {"construction_method": construction_method} if construction_method is not None else {}
            if observation_profile is not None:
                options["observation_profile"] = observation_profile
            if stability_profile is not None:
                options["stability_profile"] = stability_profile
            function = lambda: producer.build(output, task=task, index=index, protocol=protocol, **options)
            attribute = "_step"
        else:
            producer = importlib.import_module("benchmark.remaining_goals.selected_replay")
            owner = importlib.import_module("benchmark.remaining_goals.replay_candidates").ReplayAuditEnv
            options = {"protocol": protocol} if protocol in NINE_PROTOCOLS else {}
            if observation_profile is not None:
                options["observation_profile"] = observation_profile
            if stability_profile is not None:
                options["stability_profile"] = stability_profile
            if origin.get("rgb_certificate"):
                options["rgb_certificate"] = origin["rgb_certificate"]
            function = lambda: producer.replay(origin["manifest"], output, task=task, index=index, **options)
            attribute = "step"
    except BaseException as error:
        ledger = {**identity, "count_status": "unknown", "actual_control_steps": None,
                  "finalized": True, "hook_installed": False, "error": f"{type(error).__name__}: {error}"}
        if not ledger_path.exists():
            _write(ledger_path, ledger)
        error.control_ledger = ledger
        raise
    result, ledger = _run_counted(function, owner, attribute, ledger_path, identity)
    if operation == "build":
        manifest_path = output / "manifest.candidates.json"
        manifest = _read(manifest_path)
        origin = {"manifest": str(manifest_path.resolve()), "manifest_sha256": _hash(manifest_path.read_bytes()),
                  "content_hash": manifest["content_hash"]}
        if protocol in ("normal00-control", "nine-normal00"):
            initialization = output / "construction_report.json"
            origin.update(initialization=str(initialization.resolve()), initialization_sha256=_hash(initialization.read_bytes()))
        accepted = result.get("complete") is True
    else:
        replay_path = output / "replay_report.json"
        origin = {**origin, "candidate_replay": str(replay_path.resolve()), "replay_sha256": _hash(replay_path.read_bytes())}
        accepted = result.get("technical_acceptance") is True
    if not accepted:
        error = ValueError(f"{operation} failed technical acceptance; preserve {output}")
        error.control_ledger = ledger
        error.source_origin = origin
        raise error
    return origin, ledger


def prepare(inventory_path, output, *, mode="inspect", indices=None, tasks=None,
            protocol=None, allow_failed_retry=False, continuation=False, construction_method=None,
            replace_failed_originals=False, observation_profile=None, stability_profile=None):
    """Inspect or explicitly prepare selected sources, preserving a full denominator."""
    if mode not in MODES:
        raise ValueError("invalid preparation mode")
    inventory_path, output = Path(inventory_path).resolve(), Path(output).resolve()
    inventory_raw = inventory_path.read_bytes()
    inventory = _read(inventory_path)
    protocol = protocol or inventory.get("protocol")
    if protocol not in PROTOCOLS or inventory.get("protocol") != protocol or inventory.get("schema_version") != SCHEMA:
        raise ValueError("inventory protocol/schema mismatch")
    if construction_method is not None and (construction_method not in (R2_METHOD, R5_METHOD) or protocol != "nine-mask10"):
        raise ValueError("explicit R2 construction method is only valid for nine-mask10")
    if type(replace_failed_originals) is not bool or replace_failed_originals and construction_method not in (R2_METHOD, R5_METHOD):
        raise ValueError("replacing failed original sources requires an explicit R2/R5 method")
    if observation_profile is not None:
        from ..validation import V6_PROFILE
        if observation_profile != V6_PROFILE or protocol not in NINE_PROTOCOLS:
            raise ValueError("explicit v6 observation profile requires a nine-task protocol")
    tasks, indices = _selection(tasks, indices, protocol)
    if construction_method == R5_METHOD:
        from ..validation import V6_PROFILE
        if tasks != ["mug_microwave_close"] or observation_profile != V6_PROFILE:
            raise ValueError("R5 requires only mug_microwave_close with the explicit v6 profile")
    if stability_profile is not None:
        from ..stability import PROFILE
        from ..validation import V6_PROFILE
        if (stability_profile != PROFILE or protocol != "nine-mask10" or tasks != ["mug_microwave_close"]
                or construction_method != R5_METHOD or observation_profile != V6_PROFILE):
            raise ValueError("R7 stability requires the explicit microwave R5 method and RGB v6")
    if protocol in NINE_PROTOCOLS:
        from .nine_planning import expected_episodes
    else:
        from .scoped_planning import expected_episodes
    expected = expected_episodes(protocol)
    expected_tasks = {episode["task_id"] for episode in expected}
    if inventory.get("expected") != expected:
        raise ValueError("inventory must retain the complete fixed expected population")
    entries = {}
    if not isinstance(inventory.get("entries"), list):
        raise ValueError("inventory needs entries")
    for value in inventory["entries"]:
        task, index = value.get("task_id"), value.get("initial_state_index")
        if task not in expected_tasks or type(index) is not int or not 0 <= index < 10 or (task, index) in entries:
            raise ValueError("duplicate or foreign source entry")
        entries[task, index] = {**deepcopy(value), "origin": _origin(value.get("origin"), inventory_path.parent)}
    report_path = output / "preparation_report.json"
    if output.exists():
        if not continuation:
            raise FileExistsError("output exists; explicit continuation is required")
        report = _read(report_path)
        if (report.get("schema_version") != REPORT_SCHEMA or report.get("inventory_sha256") != _hash(inventory_raw)
                or report.get("protocol") != protocol or report.get("construction_method") != construction_method
                or report.get("observation_profile") != observation_profile
                or report.get("stability_profile") != stability_profile
                or report.get("replace_failed_originals", False) != replace_failed_originals):
            raise ValueError("continuation inventory identity mismatch")
    else:
        output.mkdir(parents=True, exist_ok=False)
        report = {"schema_version": REPORT_SCHEMA, "protocol": protocol,
                  "inventory": str(inventory_path), "inventory_sha256": _hash(inventory_raw),
                  "expected": expected, "sources": [], "policy_called": False, "model_rollouts": 0}
        if construction_method is not None:
            report["construction_method"] = construction_method
        if observation_profile is not None:
            report["observation_profile"] = observation_profile
        if stability_profile is not None:
            report["stability_profile"] = stability_profile
        if replace_failed_originals:
            report["replace_failed_originals"] = True
    prior = {(r["task_id"], r["initial_state_index"]): r for r in report["sources"]}
    if continuation:
        # Readiness is current file evidence, while physical operations/counts
        # are immutable history. Refresh even retained rows outside this subset.
        readiness_fields = ("status", "phase", "candidate", "origin", "episode_id", "acceptance", "reason")
        for row in prior.values():
            if row["status"] != "ready" and not row.get("ready_origin_invalidated"):
                continue
            current = _inspect(protocol, row["task_id"], row["initial_state_index"], row.get("origin"))
            if current["status"] != "ready" and row["status"] == "ready":
                row.setdefault("readiness_history", []).append(
                    {field: deepcopy(row[field]) for field in readiness_fields if field in row})
                # A once-completed attempt becoming missing does not authorize
                # replay/build again through ordinary continuation selection.
                row["ready_origin_invalidated"] = True
                row["recovery_action"] = (
                    "Restore original evidence for file-only revalidation; a new physical attempt "
                    "requires a new --output, preserving this report. --allow-failed-retry does "
                    "not rebuild or replay an invalidated ready origin in this output.")
            for field in readiness_fields:
                row.pop(field, None)
                if field in current:
                    row[field] = current[field]
    # Continuation may select a disjoint subset; retain every earlier chosen
    # origin before writing the next composite inventory.
    for key, row in prior.items():
        if row.get("origin"):
            entries[key] = {"task_id": key[0], "initial_state_index": key[1], "origin": deepcopy(row["origin"])}

    def persist():
        report["sources"] = list(prior.values())
        _write(report_path, report)
        composite = {"schema_version": SCHEMA, "protocol": protocol, "expected": expected,
                     "entries": list(entries.values())}
        composite["content_hash"] = _hash(json.dumps(composite, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        _write(output / "sources.json", composite)

    persist()
    for task in tasks:
        for index in indices:
            key = task, index
            old = prior.get(key)
            if old and old.get("ready_origin_invalidated"):
                # Revalidated above without replacing its evidence/operation history.
                # Existing inventory sources may have no operations of their own.
                continue
            resume_replay = (old and old["status"] == "missing" and old["phase"] == "replay"
                             and not old.get("ready_origin_invalidated")
                             and mode in ("replay-missing", "prepare-missing")
                             and not any(op["operation"] == "replay" for op in old.get("operations", [])))
            if old and old.get("operations") and not resume_replay and not (allow_failed_retry and old["status"] == "failed"):
                if old.get("origin"):
                    entries[key] = {"task_id": task, "initial_state_index": index, "origin": old["origin"]}
                continue
            origin = old.get("origin") if old else entries.get(key, {}).get("origin")
            row = _inspect(protocol, task, index, origin)
            row["previous_attempts"] = deepcopy(old.get("previous_attempts", [])) if old else []
            if resume_replay:
                row["operations"] = deepcopy(old["operations"])
                row["constructed"] = old["constructed"]
                row["candidate"] = old["candidate"]
            elif old and old.get("operations"):
                row["previous_attempts"].append({k: deepcopy(v) for k, v in old.items() if k != "previous_attempts"})
            prior[key] = row
            replace_original = replace_failed_originals and not (old and old.get("operations"))
            if row["status"] == "ready" or mode == "inspect" or (row["status"] == "failed" and not (allow_failed_retry or replace_original)):
                persist()
                continue
            if row["status"] == "failed":
                # Explicit new attempt; the original failing origin stays in history.
                if not old or not old.get("operations"):
                    row["previous_attempts"].append({k: deepcopy(v) for k, v in row.items() if k != "previous_attempts"})
                row["status"] = "missing"
                if row["candidate"] != "existing":
                    origin = None
                    row.update(phase="candidate", candidate="missing")
            attempt = len(row["previous_attempts"]) + 1
            root = output / "attempts" / task / f"source_{index:02d}" / f"attempt_{attempt:03d}"
            try:
                for operation in ("build", "replay"):
                    if operation == "build":
                        needed = row["phase"] == "candidate" and mode in ("build-missing", "prepare-missing")
                    else:
                        needed = (protocol in ("selected-mask10", "nine-mask10") and row["phase"] == "replay"
                                  and mode in ("replay-missing", "prepare-missing"))
                    if not needed:
                        continue
                    # Persist running intent before native code; interrupted work cannot report zero.
                    row["operations"].append({"operation": operation, "status": "running", "output": str(root / operation)})
                    row.update(actual_control_steps=None, count_status="unknown")
                    persist()
                    options = {"construction_method": construction_method} if construction_method is not None else {}
                    if observation_profile is not None:
                        options["observation_profile"] = observation_profile
                    if stability_profile is not None:
                        options["stability_profile"] = stability_profile
                    origin, ledger = _native(operation, task, index, origin, root / operation, protocol, **options)
                    row["operations"][-1].update(status="completed", ledger=ledger)
                    inspected = _inspect(protocol, task, index, origin)
                    for field in ("status", "phase", "candidate", "origin", "episode_id", "acceptance", "reason"):
                        if field in inspected:
                            row[field] = inspected[field]
                    row["constructed" if operation == "build" else "replayed"] = True
                    if operation == "build":
                        row["candidate"] = "constructed"
                    persist()
            except Exception as error:
                ledger = getattr(error, "control_ledger", {"actual_control_steps": None, "count_status": "unknown"})
                row.update(status="failed", reason=f"{type(error).__name__}: {error}")
                if hasattr(error, "source_origin"):
                    row["origin"] = error.source_origin
                if row["operations"]:
                    row["operations"][-1].update(status="failed", ledger=ledger)
            if row["operations"]:
                counts = [operation.get("ledger", {}).get("actual_control_steps") for operation in row["operations"]]
                row["actual_control_steps"] = None if any(count is None for count in counts) else sum(counts)
                row["count_status"] = "complete" if row["actual_control_steps"] is not None else "unknown"
            if row.get("origin"):
                entries[key] = {"task_id": task, "initial_state_index": index, "origin": row["origin"]}
            persist()
    persist()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protocol", choices=PROTOCOLS)
    parser.add_argument("--mode", choices=MODES, default="inspect")
    parser.add_argument("--tasks", nargs="+", choices=(*TASKS, *NEW_TASKS))
    parser.add_argument("--indices", nargs="+", type=int)
    parser.add_argument("--continue", dest="continuation", action="store_true")
    parser.add_argument("--construction-method", choices=(R2_METHOD, R5_METHOD),
                        help="Explicit R2 or microwave-only R5 construction; legacy and normal00 remain unchanged.")
    from ..validation import V6_PROFILE
    parser.add_argument("--observation-profile", choices=(V6_PROFILE,),
                        help="Explicit adjudicated v6 comparison; absent retains legacy behavior.")
    from ..stability import PROFILE
    parser.add_argument("--stability-profile", choices=(PROFILE,),
                        help="Explicit R7 A-pose admission; independent of the RGB observation profile.")
    parser.add_argument("--allow-failed-retry", action="store_true",
                        help="Explicit new attempt with unchanged fixed physical rules; preserve prior failure evidence. Does not relax stability requirements.")
    args = parser.parse_args(argv)
    report = prepare(args.inventory, args.output, mode=args.mode, indices=args.indices, tasks=args.tasks,
                     protocol=args.protocol, allow_failed_retry=args.allow_failed_retry, continuation=args.continuation,
                     construction_method=args.construction_method, observation_profile=args.observation_profile,
                     stability_profile=args.stability_profile)
    tasks, indices = _selection(args.tasks, args.indices, report.get("protocol", args.protocol))
    selected = [row for row in report["sources"] if row["task_id"] in tasks and row["initial_state_index"] in indices]
    return 0 if selected and all(row["status"] == "ready" for row in selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
