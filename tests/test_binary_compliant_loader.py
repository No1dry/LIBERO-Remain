"""Accepted-core file-only integration; never starts simulation or models."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from libero_remain_reporting import load_verified_results, map_verified_results


def core_path():
    configured = os.environ.get("LIBERO_REMAIN_ACCEPTED_CORE")
    if not configured:
        pytest.skip("set LIBERO_REMAIN_ACCEPTED_CORE to the accepted d8541ef4 checkout")
    return Path(configured)


def test_loader_rejects_unpinned_core_and_never_accepts_summary(tmp_path):
    with pytest.raises(ValueError, match="accepted core"):
        load_verified_results(tmp_path)
    result = subprocess.run([sys.executable, "-m", "libero_remain_reporting", "--summary", str(tmp_path / "summary.json")],
                            capture_output=True, text=True)
    assert result.returncode == 2


def test_accepted_core_missing_inputs_report_90_missing_without_loading_native(tmp_path):
    loaded = load_verified_results(core_path(), condition="10")
    report = map_verified_results(loaded["expected_episodes"], loaded["records"], artifact_issues=loaded["artifact_issues"])
    assert report["counts"]["expected"] == 90
    assert report["counts"]["completed"] == 0
    assert report["counts"]["unresolved_jobs"] == 90
    assert loaded["simulation_created"] is False
    assert loaded["weights_loaded"] is False


def test_cli_writes_incomplete_report_and_returns_integrity_exit_code(tmp_path):
    out = tmp_path / "report"
    result = subprocess.run([sys.executable, "-m", "libero_remain_reporting", "--core-root", str(core_path()),
                             "--out", str(out)], capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    summary = json.loads((out / "summary.json").read_text())
    assert summary["counts"]["formal_SR"] is None
    assert "Completion: 0.00% (0/90)" in result.stdout
    assert "Live completed SR: N/A" in result.stdout


def test_arbitrary_summary_success_is_rejected_by_accepted_source_chain(tmp_path):
    core = core_path()
    old = tmp_path / "old"
    old.mkdir()
    path = old / "summary.json"
    path.write_text(json.dumps({"episodes": [{"episode_id": "basket_s000_10", "classification": "success", "success": True}]}))
    before = path.read_bytes()
    loaded = load_verified_results(core, mask10_run=old)
    report = map_verified_results(loaded["expected_episodes"], loaded["records"], artifact_issues=loaded["artifact_issues"])
    assert report["counts"]["completed"] == 0
    assert report["counts"]["successes"] == 0
    assert report["integrity_errors"]
    assert path.read_bytes() == before
