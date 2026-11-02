"""Export the committed nine-task implementation for later Eval synchronization.

This tool only reads Git objects and writes a new ZIP. It neither marks a
revision accepted nor deploys/pushes/runs anything. Checkout changes cannot enter
the package; every payload is read by blob ID from one resolved commit tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile


README_SOURCE = "docs/task033_eval_README.md"
DEFAULT_ENTRYPOINT = "python -m benchmark.remaining_goals.headless.nine_cli"
REQUIRED_FILES = (
    "benchmark/remaining_goals/headless/nine_cli.py",
    "benchmark/remaining_goals/nine_catalog.py",
    "benchmark/remaining_goals/task_catalog.py",
    "pyproject.toml",
    "scripts/setup_remaining_libero.py",
    "scripts/remaining_libero.py",
    "configs/remaining_goals/runtime/openvla_oft_sog10.json",
    "configs/remaining_goals/headless/nine-normal00.example.json",
    "configs/remaining_goals/headless/nine-mask10.example.json",
    "docs/task033_nine_task_runbook.md",
    README_SOURCE,
)
LICENSE_NAMES = {"LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md", "COPYING.txt", "NOTICE"}
EXCLUDED_DIRECTORIES = {"data", "raw", "collaboration", "research", "__pycache__"}


def _git(executable, repository, *arguments):
    result = subprocess.run([str(executable), "-C", str(repository), *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode:
        raise ValueError("Git object read failed: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _safe_path(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
            or any(ord(character) < 32 for character in name)):
        raise ValueError(f"unsafe committed export path: {name!r}")
    return path


def _selected(name):
    path = _safe_path(name)
    if name in REQUIRED_FILES or name in LICENSE_NAMES:
        return True
    # The complete current benchmark implementation is Python source. Keep
    # legacy reader modules, but never include raw/data/research artifacts.
    return (path.parts[0] == "benchmark" and path.suffix in {".py", ".pyi"}
            and not EXCLUDED_DIRECTORIES.intersection(path.parts[:-1]))


def export_revision(source_revision, output, *, repository=".", git="git"):
    """Write a new source-only ZIP and return its committed export manifest."""
    if not isinstance(source_revision, str) or not source_revision or source_revision.startswith("-"):
        raise ValueError("--source-revision must identify an explicit committed revision")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    revision = _git(git, repository, "rev-parse", "--verify", "--end-of-options",
                    source_revision + "^{commit}").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("Git did not resolve an exact commit object")
    tree = _git(git, repository, "ls-tree", "-r", "-z", revision)
    entries = {}
    for row in tree.split(b"\0"):
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        name = raw_path.decode("utf-8")
        if not _selected(name):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"export requires a regular committed source file: {name}")
        entries[name] = object_id
    missing = sorted(set(REQUIRED_FILES) - set(entries))
    if missing:
        raise ValueError("source commit lacks required nine-task export files: " + ", ".join(missing))
    # Read and validate the entire payload before opening the destination.
    payload = {name: _git(git, repository, "cat-file", "blob", object_id)
               for name, object_id in sorted(entries.items())}
    payload["README.md"] = payload[README_SOURCE]
    source_paths = {name: name for name in payload}
    source_paths["README.md"] = README_SOURCE
    licenses = sorted(set(payload) & LICENSE_NAMES)
    manifest = {
        "schema_version": "remaining-task033-eval-export-v1",
        "source_revision": revision,
        "requested_revision": source_revision,
        "default_entrypoint": DEFAULT_ENTRYPOINT,
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(payload.items())},
        "source_paths": dict(sorted(source_paths.items())),
        "hash_scope": "Every exported payload file; SOURCE_EXPORT.json excludes itself.",
        "license_files": licenses,
        "license_status": "copied_from_source_commit" if licenses else "not_present",
        "legacy_definition_paths": ["benchmark/remaining_goals/task_catalog.py"],
        "legacy_notice": "Legacy task definitions and readers are retained for historical evidence only; the default documented scope is nine LIBERO-10 tasks.",
        "deployment_status": "export_only_not_deployed",
        "acceptance_status": "not_asserted_by_export_tool",
    }
    payload["SOURCE_EXPORT.json"] = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a competing writer after preflight.
    with output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, raw in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True, help="Commit/ref resolved once, then read exclusively as Git objects")
    parser.add_argument("--output", required=True, type=Path, help="New ZIP path; an existing output is rejected")
    parser.add_argument("--git", default="git", help="Git executable, including an absolute Windows path")
    args = parser.parse_args(argv)
    try:
        result = export_revision(args.source_revision, args.output, git=args.git)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"export failed: {error}\n")
    print(json.dumps({"source_revision": result["source_revision"], "output": str(args.output.resolve()),
        "payload_files": len(result["files"]), "deployment_status": result["deployment_status"],
        "license_status": result["license_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
