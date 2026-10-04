"""Video evidence must never change physical rollout or its task metrics."""
from copy import deepcopy
import json

import numpy as np
import pytest

from benchmark.remaining_goals import video
from benchmark.remaining_goals.metrics import compute_metrics
from benchmark.remaining_goals.runner import run_episode
from tests.test_remaining_runner import FakeEnv, FakePolicy, episode


class MemoryWriter:
    def __init__(self, path, *, fail_append=False, fail_close=False):
        self.path = path
        self.frames = []
        self.closed = False
        self.fail_append = fail_append
        self.fail_close = fail_close

    def append_data(self, frame):
        if self.fail_append:
            raise OSError("encoder append failed")
        self.frames.append(frame.copy())

    def close(self):
        self.closed = True
        if self.fail_close:
            raise OSError("encoder close failed")
        self.path.write_bytes(b"mock encoded bytes")


@pytest.fixture
def writers(monkeypatch):
    opened = []

    def open_writer(path, fps):
        writer = MemoryWriter(path)
        writer.fps = fps
        opened.append(writer)
        return writer

    monkeypatch.setattr(video, "_open_writer", open_writer)
    return opened


def recorder(tmp_path, **options):
    environment = options.pop("environment", "toy")
    return video.EpisodeVideoRecorder(tmp_path / "episode.mp4", {"enabled": True, **options},
                                      environment_name=environment, episode=episode())


@pytest.mark.parametrize("config", [
    [], {"enabled": 1}, {"fps": True}, {"fps": 0}, {"fps": float("nan")},
    {"fps": float("inf")}, {"camera": "unknown"}, {"camera": []},
    {"stride": 0}, {"stride": True}, {"stride": 1.2}, {"private": True},
])
def test_bad_configuration_is_rejected_before_recording(config):
    with pytest.raises(ValueError):
        video.normalize_video_config(config)


def test_disabled_recording_has_no_encoder_or_filesystem_side_effects(tmp_path, writers):
    config = video.normalize_video_config()
    assert config == {"enabled": False, "fps": 20.0, "camera": "agentview", "stride": 1}
    item = video.EpisodeVideoRecorder(tmp_path / "absent" / "test.mp4", config,
                                      environment_name="toy", episode=episode())
    item.capture({}, step=0)
    assert item.close()["status"] == "disabled"
    assert not writers and not (tmp_path / "absent").exists()


@pytest.mark.parametrize("mask,predictions,chunk,steps", [
    ((True, False), [np.ones((3, 7))], 2, 5),
    ((True, False), [np.ones(7), None], 8, 5),
    ((True, True), [None], 8, 2),
])
def test_recording_is_neutral_and_covers_chunks_stop_and_retention(tmp_path, writers, mask, predictions, chunk, steps):
    spec = episode(mask=mask)
    baseline_env, recorded_env = FakeEnv(), FakeEnv()
    baseline = run_episode(baseline_env, FakePolicy(predictions), spec, max_chunk_steps=chunk)
    recorded = run_episode(recorded_env, FakePolicy(predictions), spec, max_chunk_steps=chunk,
                           recorder=recorder(tmp_path))
    assert recorded["video"]["status"] == "saved"
    assert recorded["video"]["frame_steps"] == list(range(steps + 1))
    assert len(writers[0].frames) == steps + 1
    assert writers[0].closed
    assert compute_metrics(spec, baseline["trace"]) == compute_metrics(spec, recorded["trace"])
    assert {k: v for k, v in baseline.items() if k != "elapsed_seconds"} == {
        k: v for k, v in recorded.items() if k not in ("elapsed_seconds", "video")}
    np.testing.assert_array_equal(baseline_env.actions, recorded_env.actions)
    assert baseline_env.goal_calls == recorded_env.goal_calls
    assert baseline_env.hold_calls == recorded_env.hold_calls


def test_recorder_cannot_mutate_policy_observation_or_environment_buffers():
    class MutatingRecorder:
        def capture(self, observation, *, step):
            observation["images"]["front"][:] = 255
            observation["proprio"][:] = 999

        def close(self):
            return {"status": "saved"}

    policy = FakePolicy()
    result = run_episode(FakeEnv(), policy, episode(), recorder=MutatingRecorder())
    assert result["status"] == "completed"
    assert [item[0]["proprio"][0] for item in policy.calls] == list(range(5))
    assert all(not item[0]["images"]["front"].any() for item in policy.calls)


@pytest.mark.parametrize("mode,status,frame_steps", [
    ("invalid", "invalid_initial_state", [0]),
    ("policy_error", "runtime_error", [0, 1]),
    ("predicate_error", "runtime_error", [0, 1]),
])
def test_invalid_initial_and_runtime_failures_retain_available_frames(tmp_path, writers, mode, status, frame_steps):
    class BadPredicateEnv(FakeEnv):
        def goal_values(self):
            if self.actions:
                raise RuntimeError("predicate error")
            return super().goal_values()

    env = (BadPredicateEnv() if mode == "predicate_error" else
           FakeEnv(initial=[False, False]) if mode == "invalid" else FakeEnv())
    policy = FakePolicy([np.ones(7), RuntimeError("inference error")])
    result = run_episode(env, policy, episode(), recorder=recorder(tmp_path))
    assert result["status"] == status
    assert result["video"]["frame_steps"] == frame_steps
    assert result["video"]["status"] == "saved"
    assert writers[0].closed


def test_stride_keeps_initial_and_final_frame_and_reports_physical_steps(tmp_path, writers):
    item = recorder(tmp_path, stride=3)
    result = run_episode(FakeEnv(), FakePolicy(), episode(), recorder=item)
    assert result["video"]["frame_steps"] == [0, 3, 5]
    assert result["video"]["fps"] == writers[0].fps == 20.0
    assert item.close() == result["video"]
    assert len(writers[0].frames) == 3


@pytest.mark.parametrize("environment,flip", [("libero", True), ("toy", False)])
def test_orientation_both_cameras_and_input_are_exact(tmp_path, writers, environment, flip):
    front = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
    wrist = front + 100
    observation = {"agentview_image": front, "robot0_eye_in_hand_image": wrist}
    snapshot = deepcopy(observation)
    item = recorder(tmp_path, environment=environment, camera="both")
    item.capture(observation, step=0)
    assert not (tmp_path / "episode.mp4").exists()
    assert (tmp_path / "episode.partial.mp4").exists()
    report = item.close()
    expected = np.concatenate([front[::-1, ::-1], wrist[::-1, ::-1]] if flip else [front, wrist], axis=1)
    np.testing.assert_array_equal(writers[0].frames[0], expected)
    for key in observation:
        np.testing.assert_array_equal(observation[key], snapshot[key])
    assert report["encoded_size"] == [4, 12]
    assert report["path"] == "episode.mp4"
    assert (tmp_path / "episode.mp4").is_file()
    assert not (tmp_path / "episode.partial.mp4").exists()


def test_odd_image_edges_are_padded_without_resampling(tmp_path, writers):
    frame = np.arange(3 * 5 * 3, dtype=np.uint8).reshape(3, 5, 3)
    item = recorder(tmp_path)
    item.capture({"images": {"front": frame}}, step=0)
    assert item.close()["encoded_size"] == [4, 6]
    np.testing.assert_array_equal(writers[0].frames[0][:3, :5], frame)


@pytest.mark.parametrize("failure", ["missing_dependencies", "append", "close", "camera"])
def test_encoding_errors_are_separate_and_do_not_publish_false_video(tmp_path, monkeypatch, failure):
    opened = []

    def open_writer(path, fps):
        if failure == "missing_dependencies":
            raise RuntimeError("install imageio and imageio-ffmpeg")
        writer = MemoryWriter(path, fail_append=failure == "append", fail_close=failure == "close")
        opened.append(writer)
        return writer

    monkeypatch.setattr(video, "_open_writer", open_writer)
    item = recorder(tmp_path, camera="wrist" if failure == "camera" else "agentview")
    result = run_episode(FakeEnv(), FakePolicy(), episode(), recorder=item)
    assert result["status"] == "completed" and result["n_steps"] == 5
    assert result["video"]["status"] == "video_error"
    assert result["video"]["error"] and result["video"]["path"] is None
    assert not list(tmp_path.glob("*.mp4"))
    assert all(writer.closed for writer in opened)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("existing", ["episode.mp4", "episode.partial.mp4"])
def test_preexisting_files_are_not_overwritten_or_deleted(tmp_path, writers, existing):
    path = tmp_path / existing
    path.write_bytes(b"existing evidence")
    result = run_episode(FakeEnv(), FakePolicy(), episode(), recorder=recorder(tmp_path))
    assert result["video"]["status"] == "video_error"
    assert path.read_bytes() == b"existing evidence"
    assert not writers


@pytest.mark.parametrize("mode", ["capture", "close", "invalid_report"])
def test_runner_protects_against_external_recorder_failure(mode):
    class BrokenRecorder:
        closed = False

        def capture(self, observation, *, step):
            if mode == "capture":
                raise RuntimeError("third-party capture")

        def close(self):
            self.closed = True
            if mode == "close":
                raise RuntimeError("third-party close")
            if mode == "invalid_report":
                return {"bad": np.zeros(2)}
            return {"status": "saved"}

    item = BrokenRecorder()
    result = run_episode(FakeEnv(), FakePolicy(), episode(), recorder=item)
    assert result["status"] == "completed"
    assert result["video"]["status"] == "video_error"
    assert item.closed
    json.dumps(result, allow_nan=False)


def test_real_ffmpeg_mp4_can_be_decoded_and_has_all_frames(tmp_path):
    pytest.importorskip("imageio_ffmpeg")
    imageio = pytest.importorskip("imageio.v2")
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    frame[:16, :, 0] = 240
    frame[16:, :, 2] = 240
    item = recorder(tmp_path, environment="libero")
    for step in range(4):
        item.capture({"agentview_image": frame}, step=step)
    report = item.close()
    assert report["status"] == "saved", report
    reader = imageio.get_reader(tmp_path / report["path"], format="FFMPEG")
    try:
        decoded = list(reader.iter_data())
        assert reader.get_meta_data()["fps"] == pytest.approx(20)
    finally:
        reader.close()
    assert len(decoded) == report["frames"] == 4
    assert decoded[0].shape == frame.shape
    assert decoded[0][:12, :, 2].mean() > 225
    assert decoded[0][-12:, :, 0].mean() > 225
    assert not (tmp_path / "episode.partial.mp4").exists()
