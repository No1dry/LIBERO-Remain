"""Launch the local, isolated LIBERO runtime without changing parent settings.

Examples:
    python scripts/remaining_libero.py doctor --out reports/libero_runtime_doctor.json
    python scripts/remaining_libero.py build --out data/remaining_goals --scenes 1 --tasks all
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "build": "benchmark.remaining_goals.build",
    "doctor": "benchmark.remaining_goals.doctor",
    "replay": "benchmark.remaining_goals.replay_candidates",
    "evaluate": "benchmark.remaining_goals.evaluation",
    "metrics": "benchmark.remaining_goals.cli",
}


def launch_configuration(command: str, arguments: list[str], *, root: Path = ROOT,
                         platform_name: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Return a shell-free command and child-only environment from runtime.json."""
    if command not in MODULES:
        raise ValueError(f"unsupported command: {command!r}")
    root = Path(root).resolve()
    path = root / ".runtime" / "remaining_libero" / "runtime.json"
    if not path.is_file():
        raise ValueError(f"LIBERO runtime is not installed: {path}; run scripts/setup_remaining_libero.py first")
    runtime = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(runtime, dict):
        raise ValueError("runtime.json must contain an object")
    for key in ("python", "libero_config_path", "mujoco_gl"):
        if not isinstance(runtime.get(key), str) or not runtime[key].strip():
            raise ValueError(f"runtime.json is missing {key!r}")
    python = Path(runtime["python"]).expanduser()
    config = Path(runtime["libero_config_path"])
    if not python.is_absolute():
        python = root / python
    if not config.is_absolute():
        config = root / config
    # A venv executable can be a symlink to the base Python. Keep that selected
    # path so Python discovers the venv's pyvenv.cfg and installed packages.
    python = Path(os.path.abspath(python))
    config = config.resolve()
    if not python.is_file():
        raise ValueError(f"runtime interpreter is missing: {python}")
    if not (config / "config.yaml").is_file():
        raise ValueError(f"runtime LIBERO configuration is missing: {config / 'config.yaml'}")
    environment = os.environ.copy()
    environment["LIBERO_CONFIG_PATH"] = str(config)
    environment["MUJOCO_GL"] = runtime["mujoco_gl"]
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(root) + (os.pathsep + existing if existing else "")
    host = platform_name or sys.platform
    if host.startswith("win"):
        # PyOpenGL platform selection from a Linux-oriented parent environment
        # must not make a Windows GLFW subprocess try to load EGL/OSMesa.
        environment.pop("PYOPENGL_PLATFORM", None)
    elif host.startswith("linux") and runtime["mujoco_gl"].lower() == "egl":
        environment["PYOPENGL_PLATFORM"] = "egl"
    return [str(python), "-m", MODULES[command], *arguments], environment


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=tuple(MODULES))
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="arguments passed unchanged to the selected module")
    args = parser.parse_args(argv)
    try:
        command, environment = launch_configuration(args.command, args.arguments)
        completed = subprocess.run(command, cwd=str(ROOT), env=environment, check=False)
        return completed.returncode
    except (OSError, ValueError) as error:
        print(f"remaining_libero: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
