"""Real scoped file validation plus CPU fake execution; no native/model runs."""
from copy import deepcopy
import hashlib

import pytest

from benchmark.remaining_goals import pilot
from benchmark.remaining_goals.headless import planning, source_acceptance, workflow
from tests.test_headless_source_acceptance import make_source, tree_hash
from tests.test_headless_workflow import configuration, execution
from tests.test_headless_runner import synthetic_measurement_validator


def test_mask10_plan_run_and_archived_inspection_keep_original_failures(tmp_path, monkeypatch):
    config_path = configuration(tmp_path, monkeypatch)
    source_root = tmp_path / "already_prepared"
    manifest_path, replay_path, manifest, original_report = make_source(source_root)
    config = planning.read_json(config_path)
    config["source_acceptance"] = source_acceptance.SCHEMA
    config["sources"]["basket"] = {"manifest": str(manifest_path), "candidate_replay": str(replay_path)}
    workflow.write_json(config_path, config, update=True)
    # The old process/report remains authoritative about its all-mask failure;
    # it is neither a readiness prerequisite nor a document this run may edit.
    preparation_path = source_root / "preparation.json"
    workflow.write_json(preparation_path, {"tasks": {
        "basket": {"status": "preparation_error", "error": "other-mask replay failure"},
        "stove": {"status": "starting"}}})
    original_files = tree_hash(source_root)
    manifest_bytes, replay_bytes = manifest_path.read_bytes(), replay_path.read_bytes()
    made, environments = execution(monkeypatch)

    plan = planning.validate_plan(planning.dry_plan(config_path))
    assert plan["expected"] == planning.planned_episodes() and len(plan["expected"]) == 100
    assert plan["ready_episodes"] == 10 and not made and not environments
    selected = next(row for row in plan["tasks"] if row["task_id"] == "basket")
    evidence = selected["source_acceptance"]
    assert evidence["status"] == "mask10_ready" and evidence["acceptance_scope"] == "mask10"
    assert evidence["global_report_diagnostic"]["technical_acceptance"] is False
    assert len(evidence["unselected_failures"]) == 60
    assert selected["source_snapshot_files"] == {"manifest": manifest_path.name, "replay": replay_path.name}

    out = tmp_path / "run"
    batch = workflow.run_batch(config_path, out)
    assert batch["tasks"]["basket"]["status"] == "completed"
    assert all(row["status"] == "preparation_error" for task, row in batch["tasks"].items() if task != "basket")
    assert len(made) == len(environments) == 1
    assert made[0].calls == made[0].resets == 10 and len(environments[0].actions) == 60
    assert tree_hash(source_root) == original_files
    assert original_report["technical_acceptance"] is False

    task_dir = out / "tasks/basket"
    assert (task_dir / "source/manifest.json").read_bytes() == manifest_bytes
    assert (task_dir / "source/replay_report.json").read_bytes() == replay_bytes
    for item in evidence["selected_files"]:
        archived = task_dir / "source" / (item["root"] + "_files") / item["path"]
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == item["sha256"]
    metadata = planning.read_json(task_dir / "task_run.json")
    expected_identity = workflow.evidence_identity(metadata, metadata["source_plan"]["episodes"][0])
    raw = planning.read_json(task_dir / metadata["results"][0]["path"])
    assert raw["source_acceptance"] == expected_identity["source_acceptance"]
    assert raw["configuration"] == {"horizon": 520, "confirmation_steps": 4, "max_chunk_steps": 8}

    # Move only this test's synthetic input tree. The offline reader must use
    # the archived selected dependencies rather than the original locations.
    moved = tmp_path / "originals_unavailable"
    assert source_root.resolve().is_relative_to(tmp_path.resolve()) and not moved.exists()
    source_root.rename(moved)
    assert not manifest_path.exists() and not replay_path.exists()
    summary = workflow.inspect_batch(out)
    assert not summary["unverified_task_artifacts"]
    assert summary["source_acceptance_version"] == source_acceptance.SCHEMA
    assert summary["source_acceptance"]["basket"] == evidence
    assert summary["counts"]["expected"] == 100
    assert summary["counts"]["classification_counts"] == {
        "success": 10, "failure": 0, "unknown": 0, "technical_error": 0, "missing": 90}
    assert tree_hash(moved) == original_files

    state = next(item for item in evidence["selected_files"]
                 if item["root"] == "manifest" and item["path"].endswith(".npy"))
    archived = task_dir / "source/manifest_files" / state["path"]
    archived.write_bytes(archived.read_bytes() + b"synthetic tampering")
    rejected = workflow.inspect_batch(out)
    assert rejected["unverified_task_artifacts"][0]["task_id"] == "basket"
    assert rejected["counts"]["successes"] == 0 and rejected["counts"]["expected"] == 100
    assert made[0].calls == made[0].resets == 10
    assert tree_hash(moved) == original_files


def test_default_full_mask_and_unknown_scope_are_not_relaxed(tmp_path, monkeypatch):
    original_source = pilot._source
    config_path = configuration(tmp_path, monkeypatch)
    # Undo only the existing integration fixture's source seam. Both the old
    # default and new scope operate on real file-only validation here.
    monkeypatch.setattr(pilot, "_source", original_source)
    mp, rp, _, _ = make_source(tmp_path / "source")
    source = {"manifest": str(mp), "candidate_replay": str(rp)}
    with pytest.raises(ValueError, match="passing independent replay"):
        planning.source_plan("basket", source)
    with pytest.raises(ValueError, match="unknown.*acceptance"):
        planning.source_plan("basket", source, acceptance="implicit-mask10")
    config = planning.read_json(config_path)
    assert "source_acceptance" not in planning.load_config(config_path)[0]
    config["source_acceptance"] = "implicit-mask10"
    workflow.write_json(config_path, config, update=True)
    with pytest.raises(ValueError):
        planning.load_config(config_path)
