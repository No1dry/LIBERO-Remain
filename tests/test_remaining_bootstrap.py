"""Bootstrap command contracts; these tests never install or download anything."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import bootstrap_remaining_benchmark as bootstrap
from scripts import setup_remaining_libero as setup


@pytest.fixture
def commands(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "_executable", lambda value: Path(value))
    monkeypatch.setattr(bootstrap, "_version", lambda python: (3, 10))
    monkeypatch.setattr(bootstrap, "_ensure_venv", lambda python, directory: directory / "local-python")
    monkeypatch.setattr(bootstrap, "_runtime_python", lambda: tmp_path / "runtime-python")
    monkeypatch.setattr(bootstrap, "_run", lambda command: calls.append([str(item) for item in command]))
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    return calls


def test_cpu_uses_local_editable_install_then_demo_and_rescore(commands, tmp_path):
    assert bootstrap.main(["cpu", "--python", "base-python", "--out", "reports/new smoke"]) == 0
    assert commands[0] == [str(tmp_path / ".venv/local-python"), "-m", "pip", "install",
                           "--index-url", "https://pypi.org/simple", "-r", str(tmp_path / "requirements-dev.txt")]
    assert commands[1][1:5] == ["-m", "benchmark.remaining_goals.cli", "demo", "--out"]
    assert commands[1][5] == str(tmp_path / "reports/new smoke")
    assert commands[2][3:] == ["summarize", "--run-dir", str(tmp_path / "reports/new smoke/run")]
    assert all("torch" not in str(command) and "setup_remaining_libero" not in str(command) for command in commands)


def test_offline_cpu_never_creates_environment_or_installs(commands, monkeypatch):
    monkeypatch.setattr(bootstrap, "_ensure_venv", lambda *args: pytest.fail("offline mode created a venv"))
    assert bootstrap.main(["cpu", "--skip-install", "--python", "cpu-python"]) == 0
    assert len(commands) == 2
    assert all(command[0] == "cpu-python" for command in commands)


def test_existing_cpu_output_rejected_before_install(commands, tmp_path):
    (tmp_path / "already").mkdir()
    assert bootstrap.main(["cpu", "--out", "already"]) == 2
    assert commands == []


def test_simulation_installs_torch_in_final_runtime_then_checks_it_before_setup(commands, tmp_path):
    assert bootstrap.main(["simulation", "--python", "python3.10", "--phase", "all",
                           "--index-url", "https://mirror.invalid/simple", "--workers", "2"]) == 0
    assert len(commands) == 6
    final_python = str(tmp_path / ".runtime/remaining_libero/venv/local-python")
    assert all(command[0] == final_python for command in commands[:4])
    assert commands[0][-3:] == ["numpy==1.26.4", "setuptools==69.5.1", "wheel==0.43.0"]
    assert commands[1][-3:] == ["--index-url", bootstrap.TORCH_CPU_INDEX, "torch==2.2.0"]
    assert commands[2][1] == "-c" and "import torch" in commands[2][2]
    assert commands[3][1:] == [str(tmp_path / "scripts/setup_remaining_libero.py"), "--full",
                               "--index-url", "https://mirror.invalid/simple"]
    assert commands[4][1:4] == [str(tmp_path / "scripts/remaining_libero.py"), "doctor", "--out"]
    assert commands[5][:2] == [str(tmp_path / "runtime-python"), str(tmp_path / "scripts/build_remaining_ten_tasks.py")]
    assert commands[5][-2:] == ["--workers", "2"]
    assert not any("weights" in str(command) or "train" in str(command) for command in commands)


@pytest.mark.parametrize("phase,expected", [("setup", 4), ("doctor", 1), ("build", 1)])
def test_phases_do_only_requested_work(commands, monkeypatch, phase, expected):
    if phase != "setup":
        monkeypatch.setattr(bootstrap, "_version", lambda *args: pytest.fail("existing runtime does not need setup Python"))
    assert bootstrap.main(["simulation", "--phase", phase]) == 0
    assert len(commands) == expected


def test_wrong_setup_python_fails_before_mutating(commands, monkeypatch):
    monkeypatch.setattr(bootstrap, "_version", lambda *args: (3, 12))
    assert bootstrap.main(["simulation", "--phase", "setup"]) == 2
    assert commands == []


def test_child_failure_stops_following_phases_and_preserves_exit(commands, monkeypatch):
    def fail(command):
        raise subprocess.CalledProcessError(17, command)
    monkeypatch.setattr(bootstrap, "_run", fail)
    assert bootstrap.main(["simulation", "--phase", "all"]) == 17
    assert commands == []


def test_index_environment_default_and_explicit_override(commands, monkeypatch):
    monkeypatch.setenv("PIP_INDEX_URL", "https://environment.invalid/simple")
    assert bootstrap.main(["cpu"]) == 0
    assert "https://environment.invalid/simple" in commands[0]
    commands.clear()
    assert bootstrap.main(["cpu", "--index-url", "https://explicit.invalid/simple"]) == 0
    assert "https://explicit.invalid/simple" in commands[0]


def test_resolves_python_command_via_path_and_rejects_missing(tmp_path, monkeypatch):
    interpreter = tmp_path / "python with spaces.exe"
    interpreter.write_bytes(b"not executed")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda value: str(interpreter) if value == "python3.10" else None)
    assert bootstrap._executable("python3.10") == interpreter
    assert bootstrap._executable(str(interpreter)) == interpreter
    with pytest.raises(ValueError, match="not found"):
        bootstrap._executable(tmp_path / "missing")


def test_runtime_interpreter_resolves_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    runtime = tmp_path / ".runtime/remaining_libero"
    runtime.mkdir(parents=True)
    with pytest.raises(ValueError, match="setup phase"):
        bootstrap._runtime_python()
    python = runtime / "fake-python"
    python.write_bytes(b"not executed")
    (runtime / "runtime.json").write_text(json.dumps({"python": ".runtime/remaining_libero/fake-python"}))
    assert bootstrap._runtime_python() == python


def test_setup_dependency_installer_uses_selected_index(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "RUNTIME", tmp_path)
    python = bootstrap._venv_python(tmp_path / "venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"not executed")
    calls = []
    monkeypatch.setattr(setup.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    assert setup._install_dependencies("https://chosen.invalid/simple") == python
    command, options = calls[0]
    assert command[command.index("--index-url") + 1] == "https://chosen.invalid/simple"
    assert options["check"] is True
    assert options["stderr"] == subprocess.STDOUT


def test_setup_cli_defaults_to_pypi_or_environment_and_passes_override(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "RUNTIME", tmp_path)
    monkeypatch.setattr(setup.sys, "version_info", (3, 10, 0))
    monkeypatch.setattr(setup.logging, "basicConfig", lambda **kwargs: None)
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    indexes = []
    monkeypatch.setattr(setup, "_install_dependencies", indexes.append)
    setup.main(["--dependencies-only"])
    monkeypatch.setenv("PIP_INDEX_URL", "https://environment.invalid/simple")
    setup.main(["--dependencies-only"])
    setup.main(["--dependencies-only", "--index-url", "https://explicit.invalid/simple"])
    assert indexes == ["https://pypi.org/simple", "https://environment.invalid/simple", "https://explicit.invalid/simple"]


def test_nested_venv_does_not_supply_outer_site_packages(tmp_path):
    """Reproduce why installing torch into an intermediate venv is insufficient."""
    outer, inner = tmp_path / "outer", tmp_path / "inner"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(outer)], check=True)
    outer_python = bootstrap._venv_python(outer)
    purelib = subprocess.run([str(outer_python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                             capture_output=True, text=True, check=True).stdout.strip()
    marker = "libero_pab_outer_only_test_marker"
    (Path(purelib) / f"{marker}.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run([str(outer_python), "-m", "venv", "--without-pip", "--system-site-packages", str(inner)], check=True)
    child = subprocess.run([str(bootstrap._venv_python(inner)), "-c",
                            f"import importlib.util; print(importlib.util.find_spec('{marker}') is None)"],
                           capture_output=True, text=True, check=True)
    assert child.stdout.strip() == "True"
