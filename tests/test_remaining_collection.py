"""Collection orchestration validates coverage, retains failures and never releases."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor

import numpy as np
import pytest

from scripts import build_remaining_ten_tasks as collection


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fake_runtime(monkeypatch, *, failure=None, mutate_manifest=None, mutate_replay=None,
                  replay_steps=150, replay_repeats=2, stage_hook=None):
    """Fake simulation and candidate loading, retaining the real replay evidence validator."""
    calls = []
    monkeypatch.setattr(collection, "launch_configuration", lambda command, args: ([command, *args], {}))
    monkeypatch.setattr(collection, "preview", lambda manifests, output, replays: output.write_text("preview"))

    def candidate_pack(path):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        states = {e["episode_id"]: np.array([0.]) for e in manifest["episodes"]}
        hashes = {e["episode_id"]: "a" * 64 for e in manifest["episodes"]}
        return manifest, [], states, hashes

    monkeypatch.setattr(collection, "_candidate_pack", candidate_pack)

    def run(group, command, environment):
        group.check()
        kind, *arguments = command
        calls.append(kind)
        if failure == kind:
            raise subprocess.CalledProcessError(1, command)
        options = dict(zip(arguments[::2], arguments[1::2]))
        if stage_hook:
            stage_hook(kind, options, group)
        group.check()
        output = Path(options["--out"])
        output.mkdir(parents=True)
        if kind == "build":
            suite, first = output.name, int(options["--start-index"])
            episodes = []
            for task in collection.select_tasks(options["--tasks"]):
                for source in range(first, first + int(options["--scenes"])):
                    for index, mask in enumerate(([False, False], [True, False], [False, True], [True, True])):
                        episodes.append({"episode_id": f"{task}_{source}_{index}", "task_id": task,
                                         "task_name": collection.TASKS[task]["name"], "suite": suite,
                                         "initial_state_index": source, "initial_mask": mask,
                                         "split": options["--split"], "construction": {"legal": False}})
            manifest = {"episodes": episodes, "content_hash": suite}
            if mutate_manifest:
                mutate_manifest(manifest)
            _write(output / "manifest.candidates.json", manifest)
        else:
            manifest_path = Path(options["--manifest"])
            manifest, _, states, hashes = candidate_pack(manifest_path)
            result = {"kind": "candidate_formal_adapter_replay", "technical_acceptance": True,
                      "source_content_hash": manifest["content_hash"],
                      "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                      "steps": replay_steps, "repeats": replay_repeats, "episodes": [], "error": None,
                      "policy_called": False, "release_authorized": False}
            for repetition in range(replay_repeats):
                for episode in manifest["episodes"]:
                    identifier = episode["episode_id"]
                    checks = {"validation_window_complete": True, "snapshot_contract_valid": True}
                    reset = {key: True for key in ("saved_state_exact", "initial_mask_exact", "construction_observation_exact")}
                    audit_path = f"{identifier}_{repetition}/audit.json"
                    audit = {"technical_acceptance": True, "completed_steps": replay_steps,
                             "requested_steps": replay_steps, "checks": checks, "error": None,
                             "formal_reset_checks": reset,
                             "trace": [{"step": step, "state": states[identifier].tolist(),
                                        "goals": episode["initial_mask"], "checks": {"mask_exact": True},
                                        "observation_check": {"returned_sha256": hashes[identifier]}}
                                       for step in range(replay_steps + 1)]}
                    _write(output / audit_path, audit)
                    result["episodes"].append({"episode_id": identifier, "repetition": repetition,
                                               "initial_mask": episode["initial_mask"], "source_legal": False,
                                               "technical_acceptance": True, "audit_path": audit_path,
                                               "checks": checks, "reset_checks": reset, "error": None})
            if mutate_replay:
                mutate_replay(result)
            _write(output / "replay_report.json", result)
    monkeypatch.setattr(collection._ProcessGroup, "run", run)
    return calls


def test_collection_keeps_suite_tracks_and_never_promotes_release(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    result = collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1, start_index=3, split="test")
    assert calls == ["build", "replay", "build", "replay"]
    assert result["technical_acceptance"] is True
    assert result["candidate_states"] == 40 and result["replay_runs"] == 80
    assert result["initial_state_indices"] == [3] and result["split"] == "test"
    assert [t["suite"] for t in result["tracks"]] == ["libero_10", "libero_90"]
    assert result["release_authorized"] is False and result["policy_called"] is False
    assert result["pool_suite_scores"] is False
    assert all(len(t["manifest_sha256"]) == 64 for t in result["tracks"])


@pytest.mark.parametrize("failure", ["build", "replay"])
def test_collection_records_failed_stage(tmp_path, monkeypatch, failure):
    calls = _fake_runtime(monkeypatch, failure=failure)
    with pytest.raises(subprocess.CalledProcessError):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)
    report = json.loads((tmp_path / "reports/collection_report.json").read_text())
    assert report["technical_acceptance"] is False
    assert report["error"]["type"] == "CalledProcessError" and len(report["tracks"]) == 2
    assert [track["status"] for track in report["tracks"]] == ["failed", "cancelled"]
    assert calls == (["build"] if failure == "build" else ["build", "replay"])
    assert not (tmp_path / "reports/preview.html").exists()


@pytest.mark.parametrize("field", ["source_content_hash", "source_manifest_sha256"])
def test_collection_rejects_replay_from_another_pack(tmp_path, monkeypatch, field):
    _fake_runtime(monkeypatch, mutate_replay=lambda report: report.update({field: "wrong"}))
    with pytest.raises(ValueError, match="matching, policy-free"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)
    assert json.loads((tmp_path / "reports/collection_report.json").read_text())["technical_acceptance"] is False


def test_collection_rejects_duplicate_replay_even_when_count_and_flags_match(tmp_path, monkeypatch):
    def corrupt(report):
        report["episodes"][-1] = deepcopy(report["episodes"][0])
    _fake_runtime(monkeypatch, mutate_replay=corrupt)
    with pytest.raises(ValueError, match="repeated"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)


@pytest.mark.parametrize("steps,repeats", [(149, 2), (150, 1), (151, 2), (150, 3)])
def test_collection_requires_prescribed_replay_window(tmp_path, monkeypatch, steps, repeats):
    _fake_runtime(monkeypatch, replay_steps=steps, replay_repeats=repeats)
    with pytest.raises(ValueError, match="incomplete or failed independent replay"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)


@pytest.mark.parametrize("field,value", [("task_id", "unknown"), ("initial_state_index", 1),
                                       ("initial_mask", [True, True]), ("split", "train"),
                                       ("task_name", "wrong")])
def test_collection_rejects_wrong_cells_even_with_expected_count(tmp_path, monkeypatch, field, value):
    def corrupt(manifest):
        manifest["episodes"][0][field] = value
    calls = _fake_runtime(monkeypatch, mutate_manifest=corrupt)
    with pytest.raises(ValueError, match="task/source/mask coverage"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)
    assert calls == ["build"]


def test_collection_preserves_existing_outputs(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    (tmp_path / "data").mkdir()
    with pytest.raises(ValueError, match="must both be new"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports")
    assert not calls and not (tmp_path / "reports").exists()


def test_collection_rejects_nested_data_and_reports(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    with pytest.raises(ValueError, match="non-nested"):
        collection.build_collection(tmp_path / "data", tmp_path / "data/reports")
    assert not calls and not (tmp_path / "data").exists()


def test_cross_drive_paths_are_rejected_before_creating_outputs(tmp_path, monkeypatch):
    calls = _fake_runtime(monkeypatch)
    def unavailable_relative_path(*args):
        raise ValueError("path is on mount D:, start on mount C:")
    monkeypatch.setattr(collection.os.path, "relpath", unavailable_relative_path)
    with pytest.raises(ValueError, match="same drive"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports")
    assert not calls and not (tmp_path / "data").exists() and not (tmp_path / "reports").exists()


def test_preview_failure_keeps_collection_failed(tmp_path, monkeypatch):
    _fake_runtime(monkeypatch)
    def fail_preview(*args):
        raise ValueError("bad preview evidence")
    monkeypatch.setattr(collection, "preview", fail_preview)
    with pytest.raises(ValueError, match="bad preview"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1)
    report = json.loads((tmp_path / "reports/collection_report.json").read_text())
    assert report["technical_acceptance"] is False and report["error"]["type"] == "ValueError"


def test_parallel_suites_overlap_but_keep_each_pipeline_ordered(tmp_path, monkeypatch):
    barrier, lock = threading.Barrier(2), threading.Lock()
    stages = {suite: [] for suite in ("libero_10", "libero_90")}
    def hook(kind, options, group):
        suite = Path(options["--out"]).name
        with lock:
            stages[suite].append(kind)
        if kind == "build":
            barrier.wait(timeout=5)  # Fails if the pipelines were actually sequential.
    _fake_runtime(monkeypatch, stage_hook=hook)
    result = collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1, workers=2)
    assert result["workers"] == 2 and result["technical_acceptance"] is True
    assert stages == {"libero_10": ["build", "replay"], "libero_90": ["build", "replay"]}
    assert [track["suite"] for track in result["tracks"]] == ["libero_10", "libero_90"]
    stored = json.loads((tmp_path / "reports/collection_report.json").read_text())
    assert stored == result and all(track["status"] == "technical_pass" for track in stored["tracks"])


def test_parallel_failure_cancels_other_pipeline_without_false_pass(tmp_path, monkeypatch):
    other_started = threading.Event()
    def hook(kind, options, group):
        if Path(options["--out"]).name == "libero_90":
            other_started.set()
            assert group.cancelled.wait(timeout=5)
            group.check()
        else:
            assert other_started.wait(timeout=5)
            raise subprocess.CalledProcessError(7, ["fake-primary-build"])
    calls = _fake_runtime(monkeypatch, stage_hook=hook)
    with pytest.raises(subprocess.CalledProcessError) as error:
        collection.build_collection(tmp_path / "data", tmp_path / "reports", scenes=1, workers=2)
    assert error.value.returncode == 7
    report = json.loads((tmp_path / "reports/collection_report.json").read_text())
    assert report["technical_acceptance"] is False and report["error"]["type"] == "CalledProcessError"
    assert [track["status"] for track in report["tracks"]] == ["failed", "cancelled"]
    assert all(track["failed_phase"] == "building" for track in report["tracks"])
    assert calls == ["build", "build"] and not (tmp_path / "reports/preview.html").exists()


@pytest.mark.parametrize("workers", [0, 3, True, 1.5])
def test_invalid_worker_count_creates_nothing(tmp_path, monkeypatch, workers):
    calls = _fake_runtime(monkeypatch)
    with pytest.raises(ValueError, match="workers"):
        collection.build_collection(tmp_path / "data", tmp_path / "reports", workers=workers)
    assert not calls and not (tmp_path / "reports").exists()


def test_process_registry_cancellation_reaps_real_child(monkeypatch):
    """A tiny subprocess validates cancellation without LIBERO, GPU or model code."""
    started = threading.Event()
    real_popen = collection.subprocess.Popen
    children = []
    def popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        children.append(process)
        started.set()
        return process
    monkeypatch.setattr(collection.subprocess, "Popen", popen)
    group = collection._ProcessGroup()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(group.run, [sys.executable, "-c", "import time; time.sleep(30)"], None)
        assert started.wait(timeout=5)
        group.cancel()
        with pytest.raises(CancelledError):
            future.result(timeout=5)
    assert len(children) == 1 and children[0].poll() is not None and not group.processes
    with pytest.raises(CancelledError):
        group.run([sys.executable, "-c", "raise SystemExit(0)"], None)
    assert len(children) == 1


def test_process_registry_propagates_real_child_exit_code():
    group = collection._ProcessGroup()
    with pytest.raises(subprocess.CalledProcessError) as error:
        group.run([sys.executable, "-c", "raise SystemExit(6)"], None)
    assert error.value.returncode == 6 and not group.processes
