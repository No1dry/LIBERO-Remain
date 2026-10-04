"""Previews bind actual replay evidence and cannot replace arbitrary user files."""
from copy import deepcopy
import base64
import json

import pytest

from benchmark.remaining_goals import replay_candidates as replay
from scripts import preview_remaining_candidates as preview_module
from tests.test_remaining_replay_candidates import pack, write_json


@pytest.fixture
def preview_pack(pack):
    path, replay_dir, manifest, record = pack
    for episode in manifest["episodes"]:
        audit_path = path.parent / episode["construction"]["technical_audit"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["completed_steps"] = 2
        audit["trace"][0]["object_position_drift"] = {"a": 0.0, "b": 0.0}
        write_json(audit_path, audit)
        (audit_path.parent / "start.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6aZsAAAAASUVORK5CYII="))
    return path, replay_dir, manifest, record


def test_preview_reads_verified_replay_and_embeds_all_masks(preview_pack, tmp_path):
    path, replay_dir, _, _ = preview_pack
    replay.replay(path, replay_dir, steps=2, repeats=2)
    output = tmp_path / "preview.html"
    preview_module.preview(path, output, replay_dir / "replay_report.json")
    text = output.read_text(encoding="utf-8")
    assert text.startswith(preview_module.DOCUMENT_MARKER)
    assert "独立回放通过" in text and "8/8" in text and "请求 2 个物理步" in text
    assert text.count("data:image/png;base64,") == 4
    assert "尚未认证剩余任务的执行可行性" in text


@pytest.mark.parametrize("fault", ["file_hash", "duplicate", "false_pass", "short_audit", "reset"])
def test_preview_rejects_falsely_passing_replay(preview_pack, tmp_path, fault):
    path, replay_dir, _, _ = preview_pack
    report = replay.replay(path, replay_dir, steps=2, repeats=2)
    if fault == "file_hash":
        report["source_manifest_sha256"] = "0" * 64
    elif fault == "duplicate":
        report["episodes"][-1] = deepcopy(report["episodes"][0])
    elif fault == "false_pass":
        report["episodes"] = []
    elif fault == "reset":
        report["episodes"][0]["reset_checks"]["saved_state_exact"] = False
    else:
        audit_path = replay_dir / report["episodes"][0]["audit_path"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["trace"].pop()
        write_json(audit_path, audit)
    report_path = replay_dir / "replay_report.json"
    write_json(report_path, report)
    output = tmp_path / "preview.html"
    with pytest.raises(ValueError):
        preview_module.preview(path, output, report_path)
    assert not output.exists()


def test_preview_marks_coherent_incomplete_replay_as_failed(preview_pack, tmp_path):
    path, replay_dir, _, _ = preview_pack
    report = replay.replay(path, replay_dir, steps=2, repeats=2)
    report.update(episodes=[], technical_acceptance=False)
    report_path = replay_dir / "replay_report.json"
    write_json(report_path, report)
    output = tmp_path / "preview.html"
    preview_module.preview(path, output, report_path)
    text = output.read_text(encoding="utf-8")
    assert "独立回放未通过" in text and "0/8" in text
    assert "独立回放通过" not in text


def test_preview_requires_explicit_overwrite_of_its_own_output(preview_pack, tmp_path):
    path, _, _, _ = preview_pack
    output = tmp_path / "preview.html"
    preview_module.preview(path, output)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        preview_module.preview(path, output)
    assert output.read_bytes() == original
    preview_module.preview(path, output, overwrite=True)
    assert output.read_bytes() == original


def test_preview_never_replaces_arbitrary_existing_html(preview_pack, tmp_path):
    path, _, _, _ = preview_pack
    output = tmp_path / "precious.html"
    output.write_text("user document", encoding="utf-8")
    with pytest.raises(ValueError, match="marked preview"):
        preview_module.preview(path, output, overwrite=True)
    assert output.read_text(encoding="utf-8") == "user document"


@pytest.mark.parametrize("target", ["manifest", "report", "non_html"])
def test_preview_does_not_overwrite_inputs_or_non_html(preview_pack, tmp_path, target):
    path, _, _, _ = preview_pack
    output = tmp_path / ("source.html" if target != "non_html" else "state.npy")
    output.write_bytes(b"important data")
    source = output if target == "manifest" else path
    report = output if target == "report" else None
    with pytest.raises(ValueError):
        preview_module.preview(source, output, report, overwrite=True)
    assert output.read_bytes() == b"important data"
