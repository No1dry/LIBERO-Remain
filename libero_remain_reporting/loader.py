"""Load only original accepted source/result chains in an isolated interpreter."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def validate_core(core_root):
    root = Path(core_root).resolve()
    manifest = json.loads(Path(__file__).with_name("accepted_core.json").read_text(encoding="utf-8"))
    try:
        for relative, expected in manifest["files"].items():
            if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f"source differs: {relative}")
    except (OSError, ValueError) as error:
        raise ValueError(f"accepted core {manifest['commit']} is required: {error}") from error
    return root, manifest["commit"]


def load_verified_results(core_root, *, condition="10", normal00_run=None,
                          mask10_rescore=None, mask10_run=None, runs=()):
    """Return expected_episodes, accepted records and artifact_issues.

    Accepts historical source roots and Task033 run roots, never a free-standing
    summary or hand-authored success JSON. No simulation, model, replay, rendering
    or source write occurs. The pinned accepted core performs all evidence reads.
    ``condition='10'`` is the compliant main result; 00 remains capability-only.
    """
    if condition not in {"00", "10"}:
        raise ValueError("condition must be 00 or 10")
    root, commit = validate_core(core_root)
    options = {"core_root": str(root), "condition": condition,
               "runs": [str(Path(path).resolve()) for path in runs]}
    for key, value in (("normal00_run", normal00_run), ("mask10_rescore", mask10_rescore), ("mask10_run", mask10_run)):
        options[key] = str(Path(value).resolve()) if value is not None else None
    process = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).with_name("_worker.py"))],
                             input=json.dumps(options), capture_output=True, text=True, encoding="utf-8", cwd=root)
    if process.returncode:
        raise ValueError("accepted core reader failed: " + process.stderr.strip())
    result = json.loads(process.stdout)
    result["accepted_core_commit"] = commit
    result["source_roots"] = sorted(set(options["runs"] + [str(Path(value).parent if key == "mask10_rescore" else Path(value))
        for key, value in options.items() if key in {"normal00_run", "mask10_rescore", "mask10_run"} and value]))
    return result
