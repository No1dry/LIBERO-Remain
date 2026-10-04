"""Local Windows preparation contracts; no native DLL loading or downloads."""

import hashlib
import json
from types import ModuleType, SimpleNamespace
import sys

import pytest

from scripts import prepare_remaining_windows as prepare
from benchmark.remaining_goals import libero_compat as compat


@pytest.fixture
def installation(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    packages = runtime / "venv" / "Lib" / "site-packages"
    robosuite, mujoco = packages / "robosuite", packages / "mujoco"
    (robosuite / "utils").mkdir(parents=True)
    mujoco.mkdir()
    (robosuite / "__init__.py").write_text("from robosuite.macros_private import *\n", encoding="utf-8")
    (robosuite / "utils" / "binding_utils.py").write_text('ctypes.WinDLL("mujoco.dll")\n', encoding="utf-8")
    (robosuite / "macros.py").write_text("MUJOCO_GPU_RENDERING = True\n", encoding="utf-8")
    source = mujoco / "mujoco.dll"
    source.write_bytes(b"MZ fake installed MuJoCo 2.3.7 DLL for tests")
    distributions = {name: SimpleNamespace(version=version, locate_file=lambda filename: packages / filename)
                     for name, version in (("robosuite", "1.4.0"), ("mujoco", "2.3.7"))}
    monkeypatch.setattr(prepare.platform, "system", lambda: "Windows")
    monkeypatch.setattr(prepare.importlib.metadata, "distribution", lambda name: distributions[name])
    monkeypatch.setattr(compat, "WINDOWS_RECORD", runtime / "windows_compat.json")
    return SimpleNamespace(runtime=runtime, packages=packages, robosuite=robosuite,
                           mujoco=mujoco, source=source, distributions=distributions)


def test_preparation_adds_only_private_hook_and_identical_dll_and_is_idempotent(installation):
    f = installation
    upstream = {str(path): path.read_bytes() for path in f.robosuite.rglob("*.py")}
    first = prepare.prepare_windows(f.runtime)
    assert first == prepare.prepare_windows(f.runtime)
    assert first["upstream_python_files_modified"] is False
    assert first["configuration"]["MUJOCO_GPU_RENDERING"] is False
    assert first["configuration"]["FILE_LOGGING_LEVEL"] is None
    assert (f.robosuite / "utils" / "mujoco.dll").read_bytes() == f.source.read_bytes()
    assert all(path.read_bytes() == upstream[str(path)] for path in f.robosuite.rglob("*.py")
               if path.name != "macros_private.py")
    identity = compat.compatibility_identity()
    assert identity["platform"] == "Windows"
    assert identity["windows_preparation"]["status"] == "prepared"
    assert identity["windows_preparation"]["verified_file_sha256"]["target_dll"] == hashlib.sha256(f.source.read_bytes()).hexdigest()


def test_official_private_hook_sets_actual_macro_module_fields(monkeypatch):
    parent = ModuleType("robosuite")
    macros = ModuleType("robosuite.macros")
    macros.MUJOCO_GPU_RENDERING = True
    macros.FILE_LOGGING_LEVEL = "DEBUG"
    parent.macros = macros
    monkeypatch.setitem(sys.modules, "robosuite", parent)
    monkeypatch.setitem(sys.modules, "robosuite.macros", macros)
    exec(prepare.MACROS, {})
    assert macros.MUJOCO_GPU_RENDERING is False
    assert macros.FILE_LOGGING_LEVEL is None


@pytest.mark.parametrize("foreign", ["dll", "macro"])
def test_foreign_existing_files_are_not_overwritten_or_partly_installed(installation, foreign):
    f = installation
    target = f.robosuite / "utils" / "mujoco.dll"
    macro = f.robosuite / "macros_private.py"
    foreign_path = target if foreign == "dll" else macro
    foreign_path.write_bytes(b"foreign existing contents")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        prepare.prepare_windows(f.runtime)
    assert foreign_path.read_bytes() == b"foreign existing contents"
    assert not (f.runtime / "windows_compat.json").exists()
    assert not (macro if foreign == "dll" else target).exists()


def test_inherited_parent_environment_packages_are_rejected(installation, tmp_path):
    f = installation
    f.distributions["robosuite"].locate_file = lambda filename: tmp_path / "parent" / filename
    with pytest.raises(ValueError, match="outside the workspace venv"):
        prepare.prepare_windows(f.runtime)


def test_other_package_versions_require_review(installation):
    installation.distributions["mujoco"].version = "3.0.0"
    with pytest.raises(ValueError, match="mujoco==2.3.7 only"):
        prepare.prepare_windows(installation.runtime)


@pytest.mark.parametrize("fault", ["missing", "ambiguous", "not_dll"])
def test_invalid_mujoco_dll_input_fails_before_copy(installation, fault):
    f = installation
    if fault == "missing":
        f.source.rename(f.mujoco / "not-mujoco.dll")
    elif fault == "ambiguous":
        (f.mujoco / "another").mkdir()
        (f.mujoco / "another" / "mujoco.dll").write_bytes(f.source.read_bytes())
    else:
        f.source.write_bytes(b"not a DLL")
    with pytest.raises(ValueError):
        prepare.prepare_windows(f.runtime)
    assert not (f.robosuite / "utils" / "mujoco.dll").exists()


@pytest.mark.parametrize("field", ["source_dll", "target_dll", "macro_file"])
def test_fingerprint_rejects_changed_preparation_artifact(installation, field):
    record = prepare.prepare_windows(installation.runtime)
    from pathlib import Path
    Path(record[field]["path"]).write_bytes(b"changed file")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        compat.compatibility_identity()


def test_preparation_configuration_is_part_of_fingerprint(installation):
    prepare.prepare_windows(installation.runtime)
    before = compat.compatibility_identity()
    path = installation.runtime / "windows_compat.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["configuration"]["render_backend"] = "changed_backend"
    path.write_text(json.dumps(record), encoding="utf-8")
    after = compat.compatibility_identity()
    assert before["windows_preparation"]["record_sha256"] != after["windows_preparation"]["record_sha256"]


def test_linux_identity_does_not_claim_windows_configuration(installation, monkeypatch):
    monkeypatch.setattr(prepare.platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeError, match="run on Windows"):
        prepare.prepare_windows(installation.runtime)
    identity = compat.compatibility_identity()
    assert identity["platform"] == "Linux" and "windows_preparation" not in identity
