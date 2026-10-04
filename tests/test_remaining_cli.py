"""End-to-end bookkeeping checks; these do not run a robot simulator."""

import csv
import json

import pytest

from benchmark.remaining_goals.cli import evaluate, main, rescore
from benchmark.remaining_goals.toy import build_toy_manifest


def run_toy(tmp_path, mode="reactive"):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=2)
    output = tmp_path / "run"
    summary = evaluate(manifest, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                       policy_config={"mode": mode}, policy_id=f"toy-{mode}", max_chunk_steps=1)
    return manifest, output, summary


@pytest.mark.parametrize("mode,partial,terminal", [("reactive", 1, 1), ("idle", 0, 1), ("destructive", 0, 0)])
def test_known_answer_end_to_end_and_rescore(tmp_path, mode, partial, terminal):
    _, output, summary = run_toy(tmp_path, mode)
    assert summary["counts"]["completed"] == 8
    assert summary["partial_macro"]["valid_joint_success"] == partial
    assert summary["terminal_11"]["valid_joint_success"] == terminal
    assert summary["is_toy_fixture"] is True
    assert rescore(output) == summary


def test_missing_episode_is_visible_in_summary_and_csv(tmp_path):
    _, output, _ = run_toy(tmp_path)
    (output / "episodes" / "000001.json").rename(output / "withheld_episode.json")
    summary = rescore(output)
    assert summary["counts"]["missing"] == 1
    assert summary["partial_macro"]["coverage"] < 1
    with (output / "episodes.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 8
    assert sum(row["status"] == "missing" for row in rows) == 1


def test_mixed_model_results_are_rejected(tmp_path):
    _, output, _ = run_toy(tmp_path)
    path = output / "episodes" / "000000.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["policy_id"] = "another-checkpoint"
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="mixed"):
        rescore(output)


def test_cached_metrics_cannot_change_report(tmp_path):
    _, output, summary = run_toy(tmp_path, "idle")
    for path in (output / "episodes").glob("*.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        result["metrics"] = {"joint_success": True}
        path.write_text(json.dumps(result), encoding="utf-8")
    assert rescore(output) == summary


def test_same_checkpoint_different_method_cannot_be_mixed(tmp_path):
    manifest, first, _ = run_toy(tmp_path)
    second = tmp_path / "idle"
    evaluate(manifest, second, policy_factory="benchmark.remaining_goals.toy:make_policy",
             policy_config={"mode": "idle"}, policy_id="toy-reactive", max_chunk_steps=1)
    (second / "episodes" / "000001.json").write_bytes((first / "episodes" / "000001.json").read_bytes())
    with pytest.raises(ValueError, match="mixed"):
        rescore(second)


def test_changed_instruction_is_rejected(tmp_path):
    _, output, _ = run_toy(tmp_path)
    path = output / "episodes" / "000000.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["instruction"] = "another goal"
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="instruction"):
        rescore(output)


def test_factory_failure_leaves_auditable_missing_results(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="toy mode"):
        evaluate(manifest, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                 policy_config={"mode": "invalid"}, policy_id="bad-config", max_chunk_steps=1)
    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "aborted"
    assert summary["counts"]["missing"] == 4


def test_previous_run_is_never_overwritten(tmp_path):
    manifest, output, _ = run_toy(tmp_path)
    before = (output / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        evaluate(manifest, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                 policy_config={}, policy_id="replacement", max_chunk_steps=1)
    assert (output / "run.json").read_bytes() == before


def test_cli_demo_and_validate(tmp_path, capsys):
    output = tmp_path / "demo"
    main(["demo", "--out", str(output), "--scenes", "1"])
    main(["validate", "--manifest", str(output / "fixture" / "manifest.json")])
    main(["summarize", "--run-dir", str(output / "run")])
    assert '"valid": true' in capsys.readouterr().out
