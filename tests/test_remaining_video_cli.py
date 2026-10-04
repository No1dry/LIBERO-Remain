"""Video CLI/metadata contracts, including real subprocess dispatch with CPU policies."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmark.remaining_goals import cli, evaluation
from benchmark.remaining_goals.toy import build_toy_manifest
from tests.test_remaining_evaluation import fake_config
from tests.test_remaining_video import writers  # noqa: F401 -- pytest fixture


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_toy(manifest, output, **kwargs):
    return cli.evaluate(manifest, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                        policy_config={}, policy_id="video-test-toy", max_chunk_steps=1, **kwargs)


def test_enabled_recording_preserves_every_episode_trace_and_metric(tmp_path, writers):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    plain, recorded = tmp_path / "plain", tmp_path / "recorded"
    baseline = evaluate_toy(manifest, plain)
    config = {"enabled": True, "fps": 12.5, "camera": "agentview", "stride": 3}
    actual = evaluate_toy(manifest, recorded, video_config=config)
    assert read(recorded / "run.json")["video_config"] == config
    assert read(plain / "run.json")["video_config"]["enabled"] is False
    assert read(plain / "run.json")["run_config_sha256"] != read(recorded / "run.json")["run_config_sha256"]
    assert len(writers) == 4 and all(writer.closed for writer in writers)
    assert not (plain / "videos").exists()
    for index in range(4):
        name = f"{index:06d}.json"
        before, after = read(plain / "episodes" / name), read(recorded / "episodes" / name)
        assert "video" not in before
        for key in ("trace", "metrics", "status", "error", "n_steps", "policy_queries", "stop_step"):
            assert before[key] == after[key]
        assert after["video"]["path"] == f"videos/{index:06d}.mp4"
        assert (recorded / after["video"]["path"]).is_file()
        assert after["video"]["frame_steps"][-1] == after["n_steps"]
    assert actual.pop("video_summary") == {"enabled": True, "expected": 4, "reported": 4,
                                           "saved": 4, "video_error": 0, "empty": 0,
                                           "missing": 0, "affects_metrics": False}
    assert actual == baseline
    assert cli.rescore(recorded) == read(recorded / "summary.json")


def test_video_settings_are_hash_bound_and_old_records_without_them_rescore(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    output = tmp_path / "run"
    summary = evaluate_toy(manifest, output)
    metadata = read(output / "run.json")
    altered = deepcopy(metadata)
    altered["video_config"]["fps"] = 99
    cli._write_json(output / "run.json", altered)
    with pytest.raises(ValueError, match="configuration hash mismatch"):
        cli.rescore(output)
    # Reconstruct the pre-video metadata/hash contract without changing the
    # physical episode fields. Absence of this optional field remains valid.
    metadata.pop("video_config")
    metadata["run_config_sha256"] = cli._config_hash(metadata)
    cli._write_json(output / "run.json", metadata)
    for path in (output / "episodes").glob("*.json"):
        row = read(path)
        row["run_config_sha256"] = metadata["run_config_sha256"]
        cli._write_json(path, row)
    assert cli.rescore(output) == summary


def test_unexpected_recorder_setup_failure_keeps_successful_rollout(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("test recorder initialization failed")
    monkeypatch.setattr(cli, "EpisodeVideoRecorder", fail)
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    output = tmp_path / "run"
    summary = evaluate_toy(manifest, output, video_config={"enabled": True})
    assert summary["run_status"] == "finished" and summary["counts"]["completed"] == 4
    assert summary["video_summary"]["video_error"] == 4
    for path in (output / "episodes").glob("*.json"):
        row = read(path)
        assert row["status"] == "completed" and row["error"] is None
        assert row["video"]["path"] is None and "initialization failed" in row["video"]["error"]


@pytest.mark.parametrize("config", [{"fps": 0}, {"enabled": "yes"}, {"stride": 0}, {"extra": True}])
def test_bad_video_config_is_rejected_before_output_or_policy_launch(tmp_path, config):
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="video"):
        evaluate_toy(tmp_path / "missing_manifest.json", output, video_config=config)
    assert not output.exists()


@pytest.mark.parametrize("command", ["demo", "run"])
def test_low_level_cli_forwards_all_flags_without_loading_encoder_when_disabled(tmp_path, command):
    output = tmp_path / command
    if command == "demo":
        argv = ["demo", "--scenes", "1", "--out", str(output)]
        run_dir = output / "run"
    else:
        manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
        argv = ["run", "--manifest", str(manifest), "--out", str(output),
                "--policy-factory", "benchmark.remaining_goals.toy:make_policy", "--policy-id", "toy",
                "--max-chunk-steps", "1"]
        run_dir = output
    assert cli.main(argv + ["--no-save-video", "--video-fps", "7.5", "--video-camera", "both",
                            "--video-stride", "4"]) == 0
    assert read(run_dir / "run.json")["video_config"] == {
        "enabled": False, "fps": 7.5, "camera": "both", "stride": 4}
    assert not (run_dir / "videos").exists()


@pytest.mark.parametrize("command", ["run", "matrix"])
def test_real_unified_cli_transmits_video_options_and_does_not_fail_scores(tmp_path, command):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    config = tmp_path / "model.json"
    config.write_text(json.dumps(fake_config()), encoding="utf-8")
    output = tmp_path / command
    if command == "run":
        argv = ["run", "--config", str(config), "--manifest", str(manifest), "--out", str(output)]
        run_dir = output
    else:
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"jobs": [{"id": "toy", "config": "model.json", "manifest": str(manifest)}]}))
        argv = ["matrix", "--plan", str(plan), "--out", str(output)]
        run_dir = output / "toy"
    # The fixture has only an agentview camera. Missing wrist is a deterministic
    # recording error before encoder loading, independent of local FFmpeg.
    config_video = {"enabled": True, "fps": 13.0, "camera": "wrist", "stride": 2}
    process = subprocess.run([sys.executable, "-m", "benchmark.remaining_goals.evaluation", *argv,
                              "--save-video", "--video-fps", "13", "--video-camera", "wrist",
                              "--video-stride", "2"], cwd=Path(__file__).resolve().parents[1],
                             capture_output=True, text=True, timeout=45)
    assert process.returncode == 0, process.stdout + process.stderr
    assert read(run_dir / "run.json")["video_config"] == config_video
    summary = read(run_dir / "summary.json")
    assert summary["run_status"] == "finished" and summary["counts"]["completed"] == 4
    assert summary["video_summary"]["video_error"] == 4
    assert cli.rescore(run_dir) == summary
    if command == "matrix":
        assert read(output / "matrix_report.json")["video_config"] == config_video


def test_video_is_not_implicitly_read_from_model_configuration(tmp_path, monkeypatch):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    config = fake_config()
    config["video"] = {"enabled": True, "fps": 100}
    path = tmp_path / "model.json"
    path.write_text(json.dumps(config))
    captured = {}
    def observe(*args, **kwargs):
        captured.update(kwargs)
        return {}
    monkeypatch.setattr(evaluation, "evaluate", observe)
    evaluation.run(path, manifest, tmp_path / "run")
    assert captured["video_config"]["enabled"] is False
