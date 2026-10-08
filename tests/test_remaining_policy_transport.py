"""Transport integration; these tests never load a VLA or claim simulator success."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import time
import random
import subprocess
import venv
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.policy_transport import decode, read_frame, write_frame, MAX_FRAME
from benchmark.remaining_goals.isolated_policy import SubprocessPolicy
from benchmark.remaining_goals.cli import evaluate, rescore
from benchmark.remaining_goals.toy import build_toy_manifest
from benchmark.remaining_goals.evaluation import check_config, matrix


def test_numeric_protocol_preserves_dtype_shape_bytes_and_nested_images():
    array = np.array([-0.0, 1.0], dtype="<f8")
    value = {"array": array, "images": {"camera": np.zeros((8, 8, 3), dtype=np.uint8)}, "text": "抓住杯子"}
    stream = io.BytesIO()
    write_frame(stream, value)
    stream.seek(0)
    result = read_frame(stream)
    assert result["array"].dtype == array.dtype
    assert result["array"].tobytes() == array.tobytes()
    assert result["images"]["camera"].shape == (8, 8, 3)
    assert result["text"] == value["text"]


@pytest.mark.parametrize("dtype,shape,data", [("O", [1], "AAAAAAAAAAA="), ("f8", [10**12], ""), ("f8", [1], ""), ("f8", [True], "")])
def test_unsafe_array_encoding_rejected(dtype, shape, data):
    with pytest.raises(ValueError):
        decode({"__ndarray__": True, "dtype": dtype, "shape": shape, "data": data})


def test_frame_limit_and_truncation_fail_without_unbounded_allocation():
    with pytest.raises(ValueError, match="length"):
        read_frame(io.BytesIO(struct.pack("!I", MAX_FRAME + 1)))
    with pytest.raises(EOFError):
        read_frame(io.BytesIO(b"\x00\x00\x00\x04x"))
    with pytest.raises(ValueError):
        write_frame(io.BytesIO(), np.array([float("nan")]))


def toy_worker_config(mode="reactive"):
    return {"policy_factory": "benchmark.remaining_goals.toy:make_policy", "mode": mode,
            "execution": {"random_seed": 42}, "runtime": {"python_executable": sys.executable,
            "startup_timeout_seconds": 30, "predict_timeout_seconds": 10}}


def test_real_worker_process_round_trip_and_close():
    policy = SubprocessPolicy(toy_worker_config())
    try:
        assert policy.provenance["python_version"]
        policy.reset()
        # Privileged metadata is rejected before reaching the subprocess.
        with pytest.raises(ValueError, match="not permitted"):
            policy.predict({"state": np.array([0.0, 0.0]), "initial_mask": [True, True]}, "test")
        action = policy.predict({"images": {"front": np.zeros((8, 16, 3), dtype=np.uint8)}}, "test")
        assert np.asarray(action).shape == (7,)
    finally:
        policy.close()
    assert policy.process.poll() is not None
    policy.close()


@pytest.mark.parametrize("path_kind", ["absolute", "relative", "home"])
def test_worker_keeps_selected_interpreter_path_and_child_environment(tmp_path, monkeypatch, path_kind):
    from benchmark.remaining_goals import isolated_policy
    selected = tmp_path / "model venv" / "bin" / "python"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"not executable: spawn is deliberately intercepted")
    original_resolve = Path.resolve
    def guarded_resolve(path, *args, **kwargs):
        assert path != selected, "the worker interpreter must not be resolved"
        return original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PYTHONHOME", "unrelated-parent-python")
    monkeypatch.setenv("PYTHONPATH", "unrelated-parent-imports")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "parent-device")
    monkeypatch.setenv("LIBERO_CONFIG_PATH", "shared-libero-config")
    before = dict(os.environ)
    value = str(selected)
    if path_kind == "relative":
        value = str(selected.relative_to(tmp_path))
    elif path_kind == "home":
        value = "~/" + selected.relative_to(tmp_path).as_posix()
    config = toy_worker_config()
    config["runtime"].update(python_executable=value, cuda_visible_devices="worker-device")
    captured = []
    def intercept(command, **kwargs):
        captured.append((command, kwargs))
        raise OSError("test-only spawn failure")
    monkeypatch.setattr(isolated_policy.subprocess, "Popen", intercept)
    with pytest.raises(OSError, match="test-only spawn failure"):
        SubprocessPolicy(config)
    command, kwargs = captured[0]
    assert command == [str(selected), "-m", "benchmark.remaining_goals.policy_worker"]
    assert kwargs.get("shell", False) is False
    child = kwargs["env"]
    assert "PYTHONHOME" not in child
    assert child["PYTHONPATH"] == str(Path(isolated_policy.__file__).resolve().parents[2])
    assert child["CUDA_VISIBLE_DEVICES"] == "worker-device"
    assert child["LIBERO_CONFIG_PATH"] == "shared-libero-config"
    assert child["PYTHONHASHSEED"] == "42"
    assert dict(os.environ) == before


def test_worker_preserves_real_selected_python_symlink(tmp_path, monkeypatch):
    from benchmark.remaining_goals import isolated_policy
    selected = tmp_path / "model venv" / "bin" / Path(sys.executable).name
    selected.parent.mkdir(parents=True)
    try:
        selected.symlink_to(sys.executable)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"interpreter symlink creation is unavailable: {type(error).__name__}: {error}")
    actual_popen = isolated_policy.subprocess.Popen
    launched = []
    def capture(command, **kwargs):
        launched.append(command[0])
        return actual_popen(command, **kwargs)
    monkeypatch.setattr(isolated_policy.subprocess, "Popen", capture)
    config = toy_worker_config()
    config["runtime"]["python_executable"] = str(selected)
    policy = SubprocessPolicy(config)
    try:
        policy.reset()
        assert np.asarray(policy.predict({"images": {"front": np.zeros((8, 16, 3), dtype=np.uint8)}}, "test")).shape == (7,)
    finally:
        policy.close()
    assert launched == [str(selected)]


class _VenvMarkerPolicy:
    def __init__(self, config):
        import importlib
        marker = importlib.import_module("remaining_worker_venv_marker")
        self.metadata = {"marker": marker.VALUE, "prefix": sys.prefix}

    def reset(self):
        pass

    def predict(self, observation, instruction):
        return np.zeros(7)


def make_venv_marker_policy(config):
    return _VenvMarkerPolicy(config)


@pytest.mark.skipif(os.name == "nt", reason="POSIX venv symlink/site-packages integration; Windows uses portable path guards")
def test_worker_symlink_uses_selected_venv_site_packages(tmp_path):
    selected_env = tmp_path / "selected model venv"
    venv.EnvBuilder(with_pip=False, system_site_packages=False, symlinks=True).create(selected_env)
    selected = selected_env / "bin" / "python"
    if not selected.is_symlink():
        pytest.skip("this Python venv implementation did not create an interpreter symlink")
    result = subprocess.run([str(selected), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                            check=True, capture_output=True, text=True)
    site_packages = Path(result.stdout.strip())
    assert site_packages.is_relative_to(selected_env)
    site_packages.mkdir(parents=True, exist_ok=True)
    # Reuse only the current test dependency directories without network/pip.
    # Nested venvs do not reliably inherit their immediate parent's packages.
    dependencies = sorted({str(Path(module.__file__).parent.parent) for module in (np, pytest)})
    (site_packages / "test_dependencies.pth").write_text("\n".join(dependencies) + "\n", encoding="utf-8")
    (site_packages / "remaining_worker_venv_marker.py").write_text("VALUE = 'selected-venv-only'\n", encoding="utf-8")
    config = toy_worker_config()
    config["runtime"]["python_executable"] = str(selected)
    config["policy_factory"] = "tests.test_remaining_policy_transport:make_venv_marker_policy"
    policy = SubprocessPolicy(config)
    try:
        assert policy.provenance["policy_metadata"] == {"marker": "selected-venv-only", "prefix": str(selected_env)}
        policy.reset()
        np.testing.assert_array_equal(policy.predict({"state": np.zeros(1)}, "test"), np.zeros(7))
    finally:
        policy.close()


def test_worker_factory_failure_cleans_up():
    with pytest.raises(RuntimeError, match="worker failed"):
        SubprocessPolicy(toy_worker_config("invalid"))


def test_isolated_policy_evaluation_and_offline_rescore(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    output = tmp_path / "run"
    summary = evaluate(manifest, output,
                       policy_factory="benchmark.remaining_goals.isolated_policy:make_policy",
                       policy_config=toy_worker_config(), policy_id="test-only-toy", max_chunk_steps=1)
    assert summary["counts"]["completed"] == 4
    assert summary["partial_macro"]["valid_joint_success"] == 1
    assert summary["is_toy_fixture"] is True
    assert rescore(output) == summary
    assert json.loads((output / "run.json").read_text())["model_runtime"]["python"]


def test_configuration_rejects_suite_mismatch_and_missing_environment():
    checked = check_config({"model_id": "pi05", "suite": "libero_10", "adapter_options": {"suite": "libero_90"}}, "libero_90")
    assert checked["static_configuration_ready"] is False
    assert checked["weights_loaded"] is False
    assert any("suite" in item for item in checked["errors"])
    assert any("python" in item for item in checked["errors"])


def test_matrix_rejects_same_gpu_before_creating_output(tmp_path):
    config = {"model_id": "pi05", "suite": "toy", "policy_id": "unit", "policy_factory": "a:b",
              "runtime": {"python_executable": sys.executable, "cuda_visible_devices": "0"},
              "execution": {"max_chunk_steps": 1}, "adapter_options": {"suite": "toy", "checkpoint": "test/id"}}
    (tmp_path / "c.json").write_text(json.dumps(config))
    (tmp_path / "m.json").write_text(json.dumps({"episodes": [{"suite": "toy"}]}))
    plan = {"jobs": [{"id": name, "config": "c.json", "manifest": "m.json"} for name in ("a", "b")]}
    (tmp_path / "p.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="disjoint"):
        matrix(tmp_path / "p.json", tmp_path / "output", max_workers=2)
    assert not (tmp_path / "output").exists()


def test_protocol_retries_short_pipe_writes():
    class ShortWriter(io.BytesIO):
        def write(self, data):
            return super().write(data[:3])
    output = ShortWriter()
    write_frame(output, {"array": np.arange(1000, dtype=np.float32)})
    output.seek(0)
    np.testing.assert_array_equal(read_frame(output)["array"], np.arange(1000, dtype=np.float32))


def test_protocol_rejects_duplicate_keys_and_excessive_encoding_depth():
    body = b'{"command":"reset","command":"close"}'
    with pytest.raises(ValueError, match="duplicate"):
        read_frame(io.BytesIO(struct.pack("!I", len(body)) + body))
    deep = 0
    for _ in range(20):
        deep = [deep]
    with pytest.raises(ValueError, match="nesting"):
        write_frame(io.BytesIO(), deep)


class _NoisePolicy:
    """Real worker fake API for seeds, metadata, noisy stdout and cleanup."""
    def __init__(self, config):
        self.config = config
        self.metadata = {"repo_commit": "fixture", "unnorm_key": "fixture_suite",
                         "native_prediction_steps": np.int64(1), "values": np.array([1, 2])}
        self.torch_rng = np.random.RandomState()
        sys.modules["torch"] = SimpleNamespace(manual_seed=self.torch_rng.seed,
                                              cuda=SimpleNamespace(is_available=lambda: False))
        print("test-only model library writes to stdout", flush=True)

    def reset(self):
        pass

    def predict(self, obs, instruction):
        if self.config.get("pause"):
            time.sleep(self.config["pause"])
        return np.array([random.random(), np.random.random(), self.torch_rng.random_sample(), 0, 0, 0, 0])

    def close(self):
        if self.config.get("close_error"):
            raise RuntimeError("fake cleanup failed")


def make_noise_policy(config):
    return _NoisePolicy(config)


def test_worker_metadata_and_per_episode_seed_stream_are_preserved():
    config = toy_worker_config()
    config["policy_factory"] = "tests.test_remaining_policy_transport:make_noise_policy"
    policy = SubprocessPolicy(config)
    try:
        assert policy.provenance["policy_metadata"]["unnorm_key"] == "fixture_suite"
        assert policy.provenance["policy_metadata"]["native_prediction_steps"] == 1
        assert policy.provenance["policy_metadata"]["values"] == [1, 2]
        policy.reset()
        first = policy.predict({"state": np.zeros(1)}, "same instruction")
        second = policy.predict({"state": np.zeros(1)}, "same instruction")
        policy.reset()
        repeated = policy.predict({"state": np.zeros(1)}, "same instruction")
        np.testing.assert_array_equal(first, repeated)
        assert not np.array_equal(first, second)
    finally:
        policy.close()


def test_hung_real_worker_times_out_and_is_reaped():
    config = toy_worker_config()
    config.update(policy_factory="tests.test_remaining_policy_transport:make_noise_policy", pause=30)
    config["runtime"]["predict_timeout_seconds"] = .1
    policy = SubprocessPolicy(config)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        policy.predict({"state": np.zeros(1)}, "task")
    assert time.monotonic() - started < 9
    assert policy.closed and policy.process.poll() is not None
    assert not policy.reader.is_alive() and not policy.writer.is_alive()


def test_worker_cleanup_failure_is_not_success():
    config = toy_worker_config()
    config.update(policy_factory="tests.test_remaining_policy_transport:make_noise_policy", close_error=True)
    policy = SubprocessPolicy(config)
    with pytest.raises(RuntimeError, match="exited with code"):
        policy.close()
    assert policy.process.poll() is not None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_invalid_timeout_rejected_before_spawning(value):
    config = toy_worker_config()
    config["runtime"]["predict_timeout_seconds"] = value
    with pytest.raises(ValueError, match="finite and positive"):
        SubprocessPolicy(config)
