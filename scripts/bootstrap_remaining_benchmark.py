"""Install and check a local CPU harness, or build real simulator candidates.

CPU (Python 3.10-3.12; no simulator or model weights):
  python scripts/bootstrap_remaining_benchmark.py cpu --out reports/cpu_smoke

Simulation (requires an available Python 3.10 and working OpenGL/EGL):
  python scripts/bootstrap_remaining_benchmark.py simulation --python python3.10 \
      --phase all --out data/remaining_goals_local --reports reports/remaining_goals_local

The simulation setup downloads fixed CPU PyTorch and the pinned official LIBERO
source/assets. It creates technical candidates, never model scores or release
approval. Each model's CUDA environment and checkpoint must be installed separately.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_VERSION = "2.2.0"


def _run(command, *, root=ROOT):
    """Use argument lists and the checkout as cwd; preserve child exit codes."""
    print("Running: " + subprocess.list2cmdline([str(item) for item in command]), flush=True)
    subprocess.run([str(item) for item in command], cwd=str(root), check=True)


def _executable(value):
    located = shutil.which(str(value))
    if located:
        return Path(located).resolve()
    path = Path(value).expanduser().resolve()
    if path.is_file():
        return path
    raise ValueError(f"Python executable not found: {value}")


def _version(python):
    result = subprocess.run(
        [str(python), "-c", "import json,sys; print(json.dumps(list(sys.version_info[:2])))"],
        capture_output=True, text=True, check=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError("Python returned an invalid version")
    return tuple(value)


def _venv_python(directory):
    return Path(directory) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _ensure_venv(python, directory):
    local = _venv_python(directory)
    if not local.is_file():
        _run([python, "-m", "venv", directory])
    if _version(local) != _version(python):
        raise ValueError(f"Existing virtual environment uses a different Python version: {directory}")
    return local


def _path_in_root(value):
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def cpu(args):
    """Install an editable checkout and verify toy construction/rollout/rescoring."""
    python = _executable(args.python)
    if _version(python) not in ((3, 10), (3, 11), (3, 12)):
        raise ValueError("CPU harness requires Python 3.10, 3.11 or 3.12")
    output = _path_in_root(args.out)
    if output.exists():
        raise ValueError(f"CPU smoke output must be new: {output}")
    if not args.skip_install:
        python = _ensure_venv(python, ROOT / ".venv")
        _run([python, "-m", "pip", "install", "--index-url", args.index_url,
              "-r", ROOT / "requirements-dev.txt"])
    _run([python, "-m", "benchmark.remaining_goals.cli", "demo", "--out", output, "--scenes", "1"])
    _run([python, "-m", "benchmark.remaining_goals.cli", "summarize", "--run-dir", output / "run"])
    print(f"CPU fixture smoke complete: {output / 'run' / 'summary.json'}; no real model or physics evaluation.")


def _runtime_python():
    lock_path = ROOT / ".runtime" / "remaining_libero" / "runtime.json"
    if not lock_path.is_file():
        raise ValueError("No simulator runtime; run the simulation setup phase first")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    value = lock.get("python")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing runtime interpreter in {lock_path}")
    path = _path_in_root(value)
    if not path.is_file():
        raise ValueError(f"Simulator runtime interpreter is missing: {path}")
    return path


def simulation(args):
    """Keep setup, renderer checks and candidate construction explicit phases."""
    runtime = ROOT / ".runtime" / "remaining_libero"
    if args.phase in ("setup", "all"):
        python = _executable(args.python)
        if _version(python) != (3, 10):
            raise ValueError("Simulation setup requires --python pointing to Python 3.10")
        final_python = _ensure_venv(python, runtime / "venv")
        _run([final_python, "-m", "pip", "install", "--index-url", args.index_url,
              "numpy==1.26.4", "setuptools==69.5.1", "wheel==0.43.0"])
        _run([final_python, "-m", "pip", "install", "--index-url", TORCH_CPU_INDEX, f"torch=={TORCH_VERSION}"])
        _run([final_python, "-c", "import torch; print('Final runtime PyTorch:', torch.__version__)"])
        # Install into the final interpreter directly. A nested venv does not
        # reliably inherit an outer venv's site-packages, so no intermediate
        # parent environment is used. The installer reuses this existing venv.
        _run([final_python, ROOT / "scripts/setup_remaining_libero.py", "--full", "--index-url", args.index_url])
    if args.phase in ("doctor", "all"):
        doctor_report = _path_in_root(args.doctor_report)
        _run([sys.executable, ROOT / "scripts/remaining_libero.py", "doctor", "--out", doctor_report])
    if args.phase in ("build", "all"):
        _run([_runtime_python(), ROOT / "scripts/build_remaining_ten_tasks.py",
              "--out", _path_in_root(args.out), "--reports", _path_in_root(args.reports),
              "--scenes", str(args.scenes), "--start-index", str(args.start_index),
              "--split", args.split, "--workers", str(args.workers)])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    default_index = os.environ.get("PIP_INDEX_URL") or "https://pypi.org/simple"
    for name in ("cpu", "simulation"):
        command = commands.add_parser(name)
        command.add_argument("--python", default=sys.executable, help="Python command name or executable path")
        command.add_argument("--index-url", default=default_index,
                             help="Dependency index (default: PIP_INDEX_URL, then PyPI)")
        if name == "cpu":
            command.add_argument("--out", default="reports/cpu_smoke")
            command.add_argument("--skip-install", action="store_true",
                                 help="Use --python as-is for an offline smoke with already installed CPU dependencies")
        else:
            command.add_argument("--phase", choices=("setup", "doctor", "build", "all"), default="all")
            command.add_argument("--out", default="data/remaining_goals_local")
            command.add_argument("--reports", default="reports/remaining_goals_local")
            command.add_argument("--doctor-report", default="reports/libero_runtime_doctor.json")
            command.add_argument("--scenes", type=int, default=3)
            command.add_argument("--start-index", type=int, default=0)
            command.add_argument("--split", choices=("train", "val", "test"), default="val")
            command.add_argument("--workers", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    if not args.index_url.strip():
        parser.error("--index-url must not be empty")
    if args.command == "simulation" and (args.scenes < 1 or args.start_index < 0):
        parser.error("--scenes must be positive and --start-index must be nonnegative")
    try:
        (cpu if args.command == "cpu" else simulation)(args)
    except subprocess.CalledProcessError as error:
        print(f"bootstrap failed: child exited with {error.returncode}", file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except (OSError, ValueError) as error:
        print(f"bootstrap failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
