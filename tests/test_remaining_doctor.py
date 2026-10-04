"""Doctor contracts with fakes; passing these is not real LIBERO acceptance."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

from benchmark.remaining_goals import doctor, libero_env
from scripts.setup_remaining_libero import COMMIT
from tests.test_remaining_libero_env import FakeControlEnv


@pytest.fixture
def official_source(tmp_path):
    source = tmp_path / f"LIBERO-{COMMIT}" / "libero" / "libero"
    init_root = source / "init_files"
    (init_root / "libero_10").mkdir(parents=True)
    task = SimpleNamespace(problem_folder="libero_10", init_states_file="basket.pruned_init")
    path = init_root / task.problem_folder / task.init_states_file
    payload = b"official archive byte fixture; not executable pickle"
    path.write_bytes(payload)
    archive = tmp_path / f"LIBERO-{COMMIT}.zip"
    member = f"LIBERO-{COMMIT}/libero/libero/init_files/libero_10/basket.pruned_init"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(member, payload)
    roots = {"init_states": init_root, "bddl_files": source / "bddl_files", "assets": source / "assets"}
    module = SimpleNamespace(__file__=str(source / "__init__.py"), get_libero_path=lambda name: str(roots[name]))
    return SimpleNamespace(source=source, task=task, path=path, payload=payload,
                           archive=archive, module=module, roots=roots, lock={"libero_commit": COMMIT})


def test_trusted_initial_payload_must_match_official_archive(official_source):
    f = official_source
    payload, path = doctor._trusted_initial_bytes(f.module, f.task, f.source, f.archive, f.lock)
    assert payload == f.payload
    assert path == f.path
    f.path.write_bytes(b"tampered pickle")
    with pytest.raises(ValueError, match="differ from"):
        doctor._trusted_initial_bytes(f.module, f.task, f.source, f.archive, f.lock)


@pytest.mark.parametrize("violation", ["import", "config", "traversal", "extension"])
def test_arbitrary_initial_state_sources_rejected(official_source, violation, tmp_path):
    f = official_source
    if violation == "import":
        f.module.__file__ = str(tmp_path / "other" / "__init__.py")
    elif violation == "config":
        f.roots["init_states"] = tmp_path / "external"
    elif violation == "traversal":
        f.task.problem_folder = "../../../other"
    else:
        f.task.init_states_file = "arbitrary.pkl"
    with pytest.raises(ValueError):
        doctor._trusted_initial_bytes(f.module, f.task, f.source, f.archive, f.lock)


def test_runtime_lock_verifies_commit_archive_and_configuration(tmp_path, monkeypatch):
    root = tmp_path / ".runtime" / "remaining_libero"
    root.mkdir(parents=True)
    config = root / "config"
    config.mkdir()
    (config / "config.yaml").write_text("{}", encoding="utf-8")
    archive = root / f"LIBERO-{COMMIT}.zip"
    archive.write_bytes(b"archive fixture")
    lock = {"libero_commit": COMMIT, "libero_config_path": str(config),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    lock_path = root / "runtime.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    monkeypatch.setenv("LIBERO_CONFIG_PATH", str(config))
    assert doctor._runtime_lock()[0] == lock
    archive.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        doctor._runtime_lock()
    lock["libero_commit"] = "not-the-fixed-commit"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed official"):
        doctor._runtime_lock()


@pytest.fixture
def fake_doctor(tmp_path, monkeypatch):
    class ContinuousFakeEnv(FakeControlEnv):
        def step(self, action):
            self.done = self.env.done = False
            return super().step(action)

    env = ContinuousFakeEnv()
    loaded = []
    imports = []
    task = SimpleNamespace(language="put two objects away")
    bddl = tmp_path / "task.bddl"
    bddl.write_text("test", encoding="utf-8")
    lock = {"libero_commit": COMMIT, "archive_sha256": "0" * 64}
    monkeypatch.setattr(doctor, "_runtime_lock", lambda: (lock, tmp_path, tmp_path / "source.zip"))
    monkeypatch.setattr(doctor, "_trusted_initial_bytes", lambda *args: (b"trusted test bytes", tmp_path / "official.pruned_init"))
    monkeypatch.setattr(libero_env, "create_scene", lambda *args, **kwargs: (env, task, bddl))
    monkeypatch.setattr(libero_env, "reset_scene", lambda native_wrapper: native_wrapper.reset())
    monkeypatch.setattr(libero_env, "environment_identity", lambda: {"name": "fake-test-only"})

    def torch_load(stream, **kwargs):
        loaded.append((stream.read(), kwargs))
        return np.array([[.75, 1., 0., .25]])

    def imwrite(path, pixels):
        # Fake encoding for control-flow tests; real doctor imports imageio.
        Path(path).write_bytes(b"fake image encoding" + pixels.tobytes())

    modules = {"numpy": np, "torch": SimpleNamespace(load=torch_load),
               "imageio.v3": SimpleNamespace(imwrite=imwrite)}

    def import_module(name):
        imports.append(name)
        return modules.get(name, SimpleNamespace(__version__="fake"))

    monkeypatch.setattr(doctor.importlib, "import_module", import_module)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "fake-test-only")
    return SimpleNamespace(env=env, loaded=loaded, imports=imports, output=tmp_path / "doctor.json")


def test_doctor_contract_has_20_steps_snapshots_and_explicit_not_benchmark(fake_doctor):
    f = fake_doctor
    report = doctor.run_doctor(f.output)
    assert report["status"] == "passed", report.get("error")
    assert report["not_policy_benchmark"] is True
    assert report["policy_model_loaded"] is False
    assert report["physical_steps_completed"] == 20
    assert [x["step"] for x in report["snapshots"]] == [0, 10, 20]
    assert all(x["state_finite"] for x in report["snapshots"])
    assert len(f.env.env.actions) == 20
    assert all(action == doctor.DUMMY_ACTION for action in f.env.env.actions)
    assert f.loaded == [(b"trusted test bytes", {"map_location": "cpu", "weights_only": False})]
    assert set(f.imports) == {"libero.libero", "robosuite", "mujoco", "torch", "numpy", "imageio.v3"}
    assert f.env.closed
    assert len(list(f.output.parent.glob("doctor_frames/*.png"))) == 6
    assert json.loads(f.output.read_text(encoding="utf-8"))["status"] == "passed"


def test_simulation_failure_is_reported_without_toy_fallback(fake_doctor):
    f = fake_doctor

    def broken_step(action):
        raise RuntimeError("real renderer/physics failure")

    f.env.step = broken_step
    report = doctor.run_doctor(f.output)
    assert report["status"] == "failed"
    assert report["error_phase"] == "initial_wait"
    assert report["physical_steps_completed"] == 0
    assert "real renderer/physics failure" in report["error"]
    assert f.env.closed
    assert json.loads(f.output.read_text(encoding="utf-8"))["status"] == "failed"


def test_runtime_failure_still_writes_report_and_cli_exits_nonzero(tmp_path, monkeypatch):
    def broken_lock():
        raise ValueError("runtime not installed")

    monkeypatch.setattr(doctor, "_runtime_lock", broken_lock)
    path = tmp_path / "failed.json"
    assert doctor.main(["--out", str(path)]) == 1
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["error_phase"] == "runtime_lock"
    assert report["not_policy_benchmark"] is True
