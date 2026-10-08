"""Launcher contract checks; do not install or execute a LIBERO runtime."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import remaining_libero as launcher


@pytest.fixture
def runtime(tmp_path):
    directory = tmp_path / ".runtime" / "remaining_libero"
    directory.mkdir(parents=True)
    python = directory / "python with spaces.exe"
    python.write_bytes(b"test placeholder, never executed")
    config = directory / "libero_config"
    config.mkdir()
    (config / "config.yaml").write_text("{}", encoding="utf-8")
    lock = {"python": str(python), "libero_config_path": str(config), "mujoco_gl": "glfw"}
    path = directory / "runtime.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return SimpleNamespace(root=tmp_path, python=python, config=config, lock=lock, path=path)


def test_windows_child_configuration_preserves_parent_and_argument_boundaries(runtime, monkeypatch):
    monkeypatch.setenv("PYOPENGL_PLATFORM", "egl")
    monkeypatch.setenv("PYTHONPATH", "existing-parent-path")
    monkeypatch.setenv("LIBERO_CONFIG_PATH", "parent-config")
    before = dict(os.environ)
    args = ["--out", "data/path with spaces", "--scenes", "1", "--tasks", "all"]
    command, child = launcher.launch_configuration("build", args, root=runtime.root, platform_name="win32")
    assert command == [str(runtime.python), "-m", "benchmark.remaining_goals.build", *args]
    assert child["LIBERO_CONFIG_PATH"] == str(runtime.config)
    assert child["MUJOCO_GL"] == "glfw"
    assert child["PYTHONPATH"] == str(runtime.root) + os.pathsep + "existing-parent-path"
    assert "PYOPENGL_PLATFORM" not in child
    assert dict(os.environ) == before


def test_linux_egl_sets_pyopengl_for_child_only(runtime, monkeypatch):
    runtime.lock["mujoco_gl"] = "egl"
    runtime.path.write_text(json.dumps(runtime.lock), encoding="utf-8")
    monkeypatch.delenv("PYOPENGL_PLATFORM", raising=False)
    command, environment = launcher.launch_configuration("doctor", ["--out", "report.json"],
                                                         root=runtime.root, platform_name="linux")
    assert command[2] == "benchmark.remaining_goals.doctor"
    assert environment["PYOPENGL_PLATFORM"] == "egl"
    assert "PYOPENGL_PLATFORM" not in os.environ


@pytest.mark.parametrize("path_kind", ["absolute", "relative", "home"])
def test_interpreter_path_is_absolutized_without_resolving_symlinks(runtime, monkeypatch, path_kind):
    # This guard runs even on Windows without symlink creation privileges.
    # Calling resolve() on the selected executable would reproduce the defect.
    selected = runtime.python
    original_resolve = Path.resolve
    resolved_config = []
    def guarded_resolve(path, *args, **kwargs):
        assert path != selected, "the selected interpreter must not be resolved"
        if path == runtime.config:
            resolved_config.append(path)
        return original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    if path_kind == "relative":
        runtime.lock["python"] = str(selected.relative_to(runtime.root))
    elif path_kind == "home":
        monkeypatch.setenv("HOME", str(runtime.root))
        monkeypatch.setenv("USERPROFILE", str(runtime.root))
        runtime.lock["python"] = "~/" + selected.relative_to(runtime.root).as_posix()
    runtime.path.write_text(json.dumps(runtime.lock), encoding="utf-8")
    command, environment = launcher.launch_configuration("doctor", ["--out", "path with spaces.json"],
                                                         root=runtime.root)
    assert command[0] == str(selected)
    assert command[-1] == "path with spaces.json"
    assert environment["LIBERO_CONFIG_PATH"] == str(runtime.config)
    assert resolved_config == [runtime.config]


def test_launcher_preserves_real_interpreter_symlink(runtime):
    selected = runtime.python.parent / "venv with spaces" / "bin" / "python"
    selected.parent.mkdir(parents=True)
    try:
        selected.symlink_to(runtime.python)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"interpreter symlink creation is unavailable: {type(error).__name__}: {error}")
    runtime.lock["python"] = str(selected.relative_to(runtime.root))
    runtime.path.write_text(json.dumps(runtime.lock), encoding="utf-8")
    command, _ = launcher.launch_configuration("doctor", [], root=runtime.root, platform_name="linux")
    assert selected.is_symlink()
    assert command[0] == str(selected) and command[0] != str(selected.resolve())


def test_missing_runtime_gives_setup_instruction(tmp_path):
    with pytest.raises(ValueError, match="setup_remaining_libero.py"):
        launcher.launch_configuration("doctor", [], root=tmp_path)


@pytest.mark.parametrize("field", ["python", "libero_config_path", "mujoco_gl"])
def test_missing_runtime_fields_rejected(runtime, field):
    del runtime.lock[field]
    runtime.path.write_text(json.dumps(runtime.lock), encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        launcher.launch_configuration("doctor", [], root=runtime.root)


def test_main_forwards_module_help_and_nonzero_exit_without_shell(monkeypatch, tmp_path):
    captured = {}

    def configure(command, arguments):
        captured["configuration"] = (command, arguments)
        return ["python", "-m", "doctor", *arguments], {"CHILD": "only"}

    def run(command, **kwargs):
        captured["run"] = (command, kwargs)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "launch_configuration", configure)
    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main(["doctor", "--help"]) == 7
    assert captured["configuration"] == ("doctor", ["--help"])
    assert captured["run"][1] == {"cwd": str(tmp_path), "env": {"CHILD": "only"}, "check": False}


def test_main_runtime_error_is_nonzero(monkeypatch):
    def broken(*args):
        raise ValueError("missing runtime")

    monkeypatch.setattr(launcher, "launch_configuration", broken)
    assert launcher.main(["build", "--out", "out"]) == 2
