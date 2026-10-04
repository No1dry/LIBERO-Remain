"""Run a real LIBERO render/state smoke check; never a policy benchmark.

Use ``python scripts/remaining_libero.py doctor --out <report.json>`` after the
local runtime installer finishes. Failure produces a failed report and a
nonzero exit status; there is no toy fallback or arbitrary pickle-file input.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter
import traceback
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SUITE = "libero_10"
TASK_NAME = "LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket"
DUMMY_ACTION = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _runtime_lock() -> tuple[dict, Path, Path]:
    # This constant is maintained by the installer, not supplied on the CLI.
    from scripts.setup_remaining_libero import COMMIT

    runtime_dir = ROOT / ".runtime" / "remaining_libero"
    lock = json.loads((runtime_dir / "runtime.json").read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or lock.get("libero_commit") != COMMIT:
        raise ValueError("runtime must use the installer's fixed official LIBERO commit")
    config = Path(lock["libero_config_path"]).resolve()
    configured = os.environ.get("LIBERO_CONFIG_PATH")
    if not configured or Path(configured).resolve() != config:
        raise ValueError("LIBERO_CONFIG_PATH differs from runtime.json; use scripts/remaining_libero.py doctor")
    if not (config / "config.yaml").is_file():
        raise ValueError("runtime LIBERO config.yaml is missing")
    archive = runtime_dir / f"LIBERO-{COMMIT}.zip"
    expected_hash = lock.get("archive_sha256")
    if not isinstance(expected_hash, str) or _sha256(archive) != expected_hash:
        raise ValueError("official source archive SHA-256 differs from runtime.json")
    source = (runtime_dir / f"LIBERO-{COMMIT}" / "libero" / "libero").resolve()
    return lock, source, archive


def _trusted_initial_bytes(package, task, source: Path, archive: Path, lock: dict) -> tuple[bytes, Path]:
    """Permit only the pinned official task's archive-matching init payload."""
    if Path(package.__file__).resolve().parent != source:
        raise ValueError("imported LIBERO is not the workspace's locked official source")
    for name, relative in (("bddl_files", "bddl_files"), ("init_states", "init_files"), ("assets", "assets")):
        if Path(package.get_libero_path(name)).resolve() != (source / relative).resolve():
            raise ValueError(f"configured LIBERO {name} is outside the locked official source")
    init_root = (source / "init_files").resolve()
    path = (init_root / task.problem_folder / task.init_states_file).resolve()
    try:
        relative = path.relative_to(init_root)
    except ValueError as error:
        raise ValueError("official initial-state path escapes the locked init_files directory") from error
    if path.suffix != ".pruned_init":
        raise ValueError("doctor only loads the official task .pruned_init file")
    payload = path.read_bytes()
    member = f"LIBERO-{lock['libero_commit']}/libero/libero/init_files/{relative.as_posix()}"
    with zipfile.ZipFile(archive) as source_archive:
        official = source_archive.read(member)
    if payload != official:
        raise ValueError("initial-state bytes differ from the locked official source archive")
    return payload, path


def _goal_truth(env) -> tuple[list[list[str]], list[bool]]:
    inner = env
    visited = set()
    while inner is not None and id(inner) not in visited:
        visited.add(id(inner))
        if hasattr(inner, "parsed_problem") and callable(getattr(inner, "_eval_predicate", None)):
            break
        inner = getattr(inner, "env", None)
    if inner is None or not hasattr(inner, "parsed_problem"):
        raise RuntimeError("official goal predicate evaluator is unavailable")
    predicates = inner.parsed_problem["goal_state"]
    if not isinstance(predicates, (list, tuple)) or not predicates:
        raise ValueError("official task must expose nonempty final predicates")
    normalized = []
    for predicate in predicates:
        if not isinstance(predicate, (list, tuple)) or any(not isinstance(token, str) for token in predicate) or len(predicate) not in (2, 3):
            raise ValueError("doctor expects official flat unary/binary predicates")
        normalized.append([predicate[0].lower(), *predicate[1:]])
    values = [bool(inner._eval_predicate(predicate)) for predicate in normalized]
    if all(values) != bool(env.check_success()):
        raise RuntimeError("per-predicate mask disagrees with official task success")
    return normalized, values


def _snapshot(env, observation: dict, *, step: int, directory: Path, np, imageio) -> dict:
    state = np.asarray(env.sim.get_state().flatten())
    if state.ndim != 1 or not state.size or state.dtype.kind not in "fiu" or not np.isfinite(state).all():
        raise RuntimeError("simulator state is not a finite 1-D real vector")
    shapes = {}
    for key, value in observation.items():
        array = np.asarray(value)
        if array.dtype.kind not in "fiu" or not np.isfinite(array).all():
            raise RuntimeError(f"nonfinite/nonnumeric observation: {key}")
        shapes[key] = {"shape": list(array.shape), "dtype": str(array.dtype)}
    images = {}
    for camera in ("agentview_image", "robot0_eye_in_hand_image"):
        pixels = np.asarray(observation[camera])
        if pixels.ndim != 3 or pixels.shape[2] != 3 or pixels.dtype != np.uint8 or not pixels.size:
            raise RuntimeError(f"{camera} is not a nonempty RGB uint8 image")
        if int(pixels.max()) == int(pixels.min()):
            raise RuntimeError(f"{camera} rendered a constant image")
        path = directory / f"step_{step:03d}_{camera}.png"
        imageio.imwrite(path, pixels)
        images[camera] = {"path": str(path), "sha256": _sha256(path),
                          "pixel_min": int(pixels.min()), "pixel_max": int(pixels.max()),
                          "orientation": "raw_libero_camera"}
    predicates, values = _goal_truth(env)
    return {"step": step, "state_finite": True, "state_shape": list(state.shape),
            "sim_time": float(state[0]), "observation_shapes": shapes,
            "goal_predicates": predicates, "goal_mask": values,
            "official_success": all(values), "images": images}


def run_doctor(output: Path, *, image_size: int = 256, seed: int = 0,
               initial_state_index: int = 0) -> dict:
    """Write a real-runtime report, including failures; caller checks status."""
    output = Path(output).resolve()
    started = perf_counter()
    report = {"schema_version": "remaining-libero-doctor-v1", "status": "running",
              "not_policy_benchmark": True, "policy_model_loaded": False,
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": {"executable": sys.executable, "version": platform.python_version()},
              "platform": platform.platform(), "imports": {}, "versions": {},
              "snapshots": [], "suite": SUITE, "task_name": TASK_NAME,
              "seed": seed, "initial_state_index": initial_state_index,
              "initial_wait_steps": 10, "smoke_steps": 10, "physical_steps_completed": 0,
              "action": DUMMY_ACTION, "action_note": "zero pose delta with gripper open; not a universally safe hold",
              "render_environment": {key: os.environ.get(key) for key in ("LIBERO_CONFIG_PATH", "MUJOCO_GL", "PYOPENGL_PLATFORM")}}
    _write_report(output, report)
    env = None
    phase = "runtime_lock"
    try:
        if type(seed) is not int or seed < 0 or type(initial_state_index) is not int or initial_state_index < 0:
            raise ValueError("seed and initial_state_index must be nonnegative integers")
        lock, source, archive = _runtime_lock()
        report["source_lock"] = {key: lock[key] for key in ("libero_commit", "archive_sha256")}
        modules = {}
        for name in ("libero.libero", "robosuite", "mujoco", "torch", "numpy", "imageio.v3"):
            phase = f"import:{name}"
            print(f"Doctor: {phase}", flush=True)
            module = importlib.import_module(name)
            modules[name] = module
            report["imports"][name] = True
            distribution = {"libero.libero": "libero", "imageio.v3": "imageio"}.get(name, name)
            try:
                report["versions"][distribution] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                report["versions"][distribution] = str(getattr(module, "__version__", "unknown"))
        np = modules["numpy"]
        from .libero_env import create_scene, environment_identity, fresh_observation, model_xml_hash, restore_raw_state, reset_scene

        phase = "create_real_scene"
        print("Doctor: creating the real LIBERO basket scene", flush=True)
        env, task, bddl = create_scene(SUITE, TASK_NAME, image_size=image_size)
        report["instruction"] = task.language
        report["bddl_sha256"] = _sha256(bddl)
        phase = "verify_official_initial_states"
        payload, init_path = _trusted_initial_bytes(modules["libero.libero"], task, source, archive, lock)
        report["initial_state_source"] = {"path": str(init_path), "sha256": hashlib.sha256(payload).hexdigest(),
                                           "trust": "bytes_match_pinned_official_source_archive"}
        # The only pickle-capable load: fixed official task bytes verified above,
        # not a CLI-supplied checkpoint/path. BytesIO prevents a verify/load race.
        states = modules["torch"].load(io.BytesIO(payload), map_location="cpu", weights_only=False)
        if initial_state_index >= len(states):
            raise ValueError("initial_state_index is outside the official state collection")
        initial = np.asarray(states[initial_state_index])
        phase = "reset_and_restore"
        env.seed(seed)
        reset_scene(env)
        observation = restore_raw_state(env, initial)
        report["model_xml_sha256"] = model_xml_hash(env)
        report["environment"] = environment_identity()
        frame_dir = output.parent / f"{output.stem}_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        phase = "snapshot_initial"
        report["snapshots"].append(_snapshot(env, observation, step=0, directory=frame_dir,
                                              np=np, imageio=modules["imageio.v3"]))
        initial_time = report["snapshots"][0]["sim_time"]
        for step in range(1, 21):
            phase = "initial_wait" if step <= 10 else "smoke_steps"
            env.step(list(DUMMY_ACTION))
            report["physical_steps_completed"] = step
            state = np.asarray(env.sim.get_state().flatten())
            if not np.isfinite(state).all():
                raise RuntimeError(f"nonfinite simulator state after step {step}")
            if step in (10, 20):
                observation = fresh_observation(env)
                report["snapshots"].append(_snapshot(env, observation, step=step, directory=frame_dir,
                                                      np=np, imageio=modules["imageio.v3"]))
                _write_report(output, report)
        if report["snapshots"][-1]["sim_time"] <= initial_time:
            raise RuntimeError("simulation time did not advance during 20 real control steps")
        if model_xml_hash(env) != report["model_xml_sha256"]:
            raise RuntimeError("model XML changed during the smoke test")
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error_phase=phase,
                      error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as error:
                report.update(status="failed", close_error=f"{type(error).__name__}: {error}")
        report["elapsed_seconds"] = perf_counter() - started
        _write_report(output, report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--initial-state-index", type=int, default=0)
    args = parser.parse_args(argv)
    report = run_doctor(args.out, image_size=args.image_size, seed=args.seed,
                        initial_state_index=args.initial_state_index)
    print(f"LIBERO doctor {report['status']}: {args.out}", flush=True)
    if report["status"] != "passed":
        print(report.get("error") or report.get("close_error", "doctor failed"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
