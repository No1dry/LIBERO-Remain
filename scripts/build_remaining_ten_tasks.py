"""Build and independently replay the ten-task, two-suite candidate collection.

Run from the project root after setup_remaining_libero.py:
  python scripts/build_remaining_ten_tasks.py --out data/remaining_ten --reports reports/remaining_ten

This constructs technical candidates only. It never runs a VLA, approves
semantic/execution feasibility, changes legal flags, or pools suite scores.
"""
from __future__ import annotations

import argparse
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.remaining_goals.task_catalog import TASKS, select_tasks
from benchmark.remaining_goals.replay_candidates import _candidate_pack
from benchmark.remaining_goals.package_audit import validate_replay_evidence
from scripts.preview_remaining_candidates import preview
from scripts.remaining_libero import launch_configuration


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class _ProcessGroup:
    """Own only the direct simulator children created by this collection.

    Build/replay launch Python modules directly, so each suite has an independent
    MuJoCo/GL process. Cancellation terminates and reaps registered children; it
    never kills unrelated Python processes or changes the shared runtime.
    """

    def __init__(self):
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.processes = set()

    def check(self):
        if self.cancelled.is_set():
            raise CancelledError("another collection stage failed or the run was interrupted")

    def run(self, command, environment):
        with self.lock:
            self.check()
            process = subprocess.Popen(command, cwd=str(ROOT), env=environment)
            self.processes.add(process)
        try:
            code = process.wait()
            self.check()
            if code:
                raise subprocess.CalledProcessError(code, command)
        finally:
            with self.lock:
                self.processes.discard(process)

    def cancel(self):
        with self.lock:
            self.cancelled.set()
            children = tuple(self.processes)
        # No registry lock is held while waiting; workers can reap and unregister.
        for process in children:
            try:
                if process.poll() is None:
                    process.terminate()
            except OSError:
                pass  # The child may have exited between poll and terminate.
        for process in children:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                process.wait(timeout=3)


def build_collection(output, reports, *, scenes=3, start_index=0, split="val", workers=1):
    output, reports = Path(output).resolve(), Path(reports).resolve()
    if output.exists() or reports.exists():
        raise ValueError("collection output and report directories must both be new")
    if output == reports or output in reports.parents or reports in output.parents:
        raise ValueError("data and report directories must be separate, non-nested paths")
    if type(scenes) is not int or scenes < 1 or type(start_index) is not int or start_index < 0:
        raise ValueError("scenes must be positive and start_index nonnegative")
    if split not in ("train", "val", "test"):
        raise ValueError("unsupported split")
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError("workers must be 1 or 2")
    try:
        os.path.relpath(output, reports)
    except ValueError as error:
        raise ValueError("data and report directories must be on the same drive for relative evidence paths") from error
    tracks = [("libero_10", "all", 6), ("libero_90", "extension", 4)]
    for suite, selection, count in tracks:
        keys = select_tasks(selection)
        if len(keys) != count or {TASKS[key]["suite"] for key in keys} != {suite}:
            raise ValueError("ten-task collection catalog changed; review the collection protocol")
        if any(len(TASKS[key]["goals"]) != 2 for key in keys):
            raise ValueError("ten-task collection requires two goals per task")
    # Validate installation before creating output directories.
    launch_configuration("build", [])
    output.mkdir(parents=True)
    reports.mkdir(parents=True)
    report_path = reports / "collection_report.json"
    report = {"kind": "remaining_goals_ten_task_collection", "technical_acceptance": False,
              "stage": "technical_candidates_not_release", "policy_called": False,
              "release_authorized": False, "pool_suite_scores": False,
              "scenes_per_task": scenes, "initial_state_indices": list(range(start_index, start_index + scenes)),
              "split": split, "workers": workers, "tracks": [], "error": None}
    for suite, selection, _ in tracks:
        report["tracks"].append({
            "suite": suite, "tasks": select_tasks(selection), "status": "pending", "error": None,
            "manifest": Path(os.path.relpath(output / suite / "manifest.candidates.json", reports)).as_posix(),
            "replay": Path(os.path.relpath(reports / suite / "replay_report.json", reports)).as_posix()})
    _write(report_path, report)
    report_lock = threading.Lock()
    processes = _ProcessGroup()

    def publish(entry, **updates):
        with report_lock:
            entry.update(updates)
            _write(report_path, report)

    def run_track(index):
        suite, selection, count = tracks[index]
        entry = report["tracks"][index]
        state_dir, replay_dir = output / suite, reports / suite
        manifest_path = state_dir / "manifest.candidates.json"
        replay_path = replay_dir / "replay_report.json"
        phase = "pending"
        try:
            processes.check()
            phase = "building"
            publish(entry, status=phase)
            arguments = ["--out", str(state_dir), "--tasks", selection, "--scenes", str(scenes),
                         "--split", split, "--start-index", str(start_index)]
            command, environment = launch_configuration("build", arguments)
            processes.run(command, environment)
            manifest, _, states, observation_hashes = _candidate_pack(manifest_path)
            if len(manifest["episodes"]) != count * scenes * 4:
                raise ValueError(f"incomplete candidate coverage for {suite}")
            if any(e["suite"] != suite or e["construction"]["legal"] is not False for e in manifest["episodes"]):
                raise ValueError("collection requires separate suites and unapproved candidates")
            expected_cells = {(task, index, mask) for task in entry["tasks"]
                              for index in range(start_index, start_index + scenes)
                              for mask in ((False, False), (True, False), (False, True), (True, True))}
            actual_cells = {(e["task_id"], e["initial_state_index"], tuple(e["initial_mask"]))
                            for e in manifest["episodes"]}
            if (actual_cells != expected_cells or len(actual_cells) != len(manifest["episodes"])
                    or any(e["split"] != split or e["task_name"] != TASKS[e["task_id"]]["name"]
                           for e in manifest["episodes"])):
                raise ValueError("candidate task/source/mask coverage differs from the requested collection")
            processes.check()
            phase = "replaying"
            publish(entry, status=phase)
            command, environment = launch_configuration("replay", ["--manifest", str(manifest_path),
                                                         "--out", str(replay_dir), "--steps", "150", "--repeats", "2"])
            processes.run(command, environment)
            _, replay = validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes)
            if (replay["technical_acceptance"] is not True or replay["requested_steps"] != 150
                    or replay["repeats"] != 2 or replay["records"] != count * scenes * 8):
                raise ValueError(f"incomplete or failed independent replay for {suite}")
            publish(entry, status="technical_pass", candidate_states=len(manifest["episodes"]),
                         replay_runs=replay["records"], content_hash=manifest["content_hash"],
                         manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                         replay_sha256=hashlib.sha256(replay_path.read_bytes()).hexdigest())
            return manifest_path, replay_path
        except BaseException as error:
            publish(entry, status="cancelled" if isinstance(error, CancelledError) else "failed",
                    failed_phase=phase, error={"type": type(error).__name__, "message": str(error)})
            processes.cancel()
            raise

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="remaining-suite")
    futures = []
    try:
        futures = [executor.submit(run_track, index) for index in range(len(tracks))]
        failures = []
        for future in as_completed(futures):
            try:
                future.result()
            except BaseException as error:
                failures.append(error)
                processes.cancel()
        if failures:
            raise next((error for error in failures if not isinstance(error, CancelledError)), failures[0])
        results = [future.result() for future in futures]
        manifests, replays = [item[0] for item in results], [item[1] for item in results]
        preview(manifests, reports / "preview.html", replays)
        report.update(technical_acceptance=True, task_count=10, candidate_states=40 * scenes,
                      replay_runs=80 * scenes, preview="preview.html")
    except BaseException as error:
        processes.cancel()
        with report_lock:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        with report_lock:
            for entry in report["tracks"]:
                if entry["status"] == "pending":
                    entry.update(status="cancelled", failed_phase="pending",
                                 error={"type": "CancelledError", "message": "collection stopped before this track started"})
            _write(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--scenes", type=int, default=3)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--split", choices=("train", "val", "test"), default="val")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1,
                        help="independent suite subprocess pipelines; 2 needs memory/GL capacity for both")
    args = parser.parse_args(argv)
    result = build_collection(args.out, args.reports, scenes=args.scenes, start_index=args.start_index,
                              split=args.split, workers=args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
