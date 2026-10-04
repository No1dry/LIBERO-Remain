"""Install an isolated, workspace-local LIBERO state-construction runtime.

Run with a Python 3.10 installation that already has CPU-capable PyTorch.
By default provisions the entire pinned official simulation package, including
all assets required by the expanded task catalog. --two-task-profile retains
the original minimal basket/stove installer. Downloads no VLA weights and does not
alter the parent environment or use the user's ~/.libero configuration.
"""
from __future__ import annotations

import hashlib
import gzip
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "remaining_libero"
COMMIT = "8f1084e3132a39270c3a13ebe37270a43ece2a01"
PACKAGE = "libero/libero/"
PROFILE_TASKS = [
    "LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket",
    "KITCHEN_SCENE3_turn_on_the_stove_and_put_the_moka_pot_on_it",
]
REQUIREMENTS = [
    "numpy==1.26.4", "mujoco==2.3.7", "robosuite==1.4.0", "bddl==1.0.1",
    "gym==0.25.2", "easydict==1.13", "cloudpickle==2.2.1", "h5py==3.10.0",
    "PyYAML==6.0.2", "opencv-python==4.8.1.78", "matplotlib==3.7.5",
    "imageio==2.34.2", "imageio-ffmpeg==0.5.1", "termcolor==2.4.0",
    "numba==0.59.1", "scipy==1.11.4", "future==1.0.0",
    "setuptools==69.5.1", "wheel==0.43.0",
]


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "remaining-goals-state-builder", "Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                return gzip.decompress(body) if response.headers.get("Content-Encoding") == "gzip" else body
        except Exception:
            logging.exception("Upstream transfer failed (%d/3): %s", attempt + 1, url)
            if attempt == 2:
                raise
            print(f"Retrying upstream transfer ({attempt + 1}/3)", flush=True)


def _source_tree():
    tree_path = RUNTIME / "upstream_tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    else:
        tree = json.loads(_get(f"https://api.github.com/repos/Lifelong-Robot-Learning/LIBERO/git/trees/{COMMIT}?recursive=1"))
        tree_path.write_text(json.dumps(tree), encoding="utf-8")
    if tree.get("truncated") or tree.get("sha") != COMMIT:
        raise RuntimeError("GitHub source tree is truncated or does not match the pinned commit")
    entries = [entry for entry in tree["tree"] if entry["type"] == "blob" and (
        entry["path"].startswith("libero/libero/") or entry["path"] in
        ("libero/__init__.py", "setup.py", "README.md", "LICENSE"))]
    return {entry["path"]: entry for entry in entries}


def _metadata_paths(entries):
    return {path for path in entries if (
        path in ("libero/__init__.py", "setup.py", "README.md", "LICENSE")
        or Path(path).suffix in (".py", ".bddl", ".xml", ".mtl", ".txt")
        or path.startswith(PACKAGE + "init_files/")
    )}


def _fetch_entries(source, entries, label):
    print(f"{label}: {len(entries)} verified Git blobs, {sum(e.get('size', 0) for e in entries) / 1048576:.1f} MiB (valid existing files reused)", flush=True)
    source.mkdir(parents=True, exist_ok=True)

    def fetch(entry):
        path = (source / entry["path"]).resolve()
        if source.resolve() not in path.parents:
            raise ValueError("source path escapes its directory")
        def valid(body):
            return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest() == entry["sha"]
        if path.is_file() and valid(path.read_bytes()):
            return
        try:
            body = _get(f"https://raw.githubusercontent.com/Lifelong-Robot-Learning/LIBERO/{COMMIT}/{entry['path']}")
            if not valid(body):
                raise ValueError(f"Git blob checksum mismatch: {entry['path']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        except Exception as exc:
            logging.exception("Pinned source file failed: %s", entry["path"])
            raise RuntimeError(f"Failed to fetch {entry['path']}; see source-download.log") from exc

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(fetch, entry) for entry in entries]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % (10 if len(entries) < 100 else 50) == 0 or done == len(entries):
                print(f"Verified source files: {done}/{len(entries)}", flush=True)


def _profile_resources(source, entries):
    """Resolve the two pinned canonical scenes, including distractors/backgrounds.

    This deliberately supports these two official tasks, not arbitrary BDDL.
    No source XML, task, texture or mesh is rewritten.
    """
    roots = {
        PACKAGE + "assets/scenes/libero_living_room_tabletop_base_style.xml",
        PACKAGE + "assets/scenes/libero_kitchen_tabletop_base_style.xml",
    }
    # Arena constructors replace two texture filenames at runtime. Resolve the
    # actual default style dictionaries without importing LIBERO or rewriting
    # XML; the XML's original assets are also kept in the closure below.
    style_ast = ast.parse((source / (PACKAGE + "envs/arenas/style.py")).read_text(encoding="utf-8"))
    styles = {}
    for node in style_ast.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("FLOOR_STYLE", "WALL_STYLE"):
                styles[node.targets[0].id] = ast.literal_eval(node.value)
    for room in ("living_room", "kitchen"):
        problem = source / (PACKAGE + f"envs/problems/libero_{room}_tabletop_manipulation.py")
        problem_ast = ast.parse(problem.read_text(encoding="utf-8"))
        for node in ast.walk(problem_ast):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ("floor_style", "wall_style"):
                    mapping = styles["FLOOR_STYLE" if key.value == "floor_style" else "WALL_STYLE"]
                    roots.add(PACKAGE + "assets/textures/" + mapping[ast.literal_eval(value)])
    categories = set()
    for task in PROFILE_TASKS:
        text = (source / (PACKAGE + "bddl_files/libero_10/" + task + ".bddl")).read_text(encoding="utf-8")
        for section in ("objects", "fixtures"):
            match = re.search(r"\(:" + section + r"\s+(.*?)\)", text, re.S)
            if match is None:
                raise RuntimeError(f"Missing {section} in pinned task {task}")
            categories.update(re.findall(r"-\s*([A-Za-z0-9_]+)", match.group(1)))
    # These fixtures are the arena itself; all its visual and collision models
    # are retained through the official arena XML dependency closure.
    for category in categories - {"living_room_table", "kitchen_table"}:
        matches = [path for path in entries if path.startswith(PACKAGE + "assets/")
                   and Path(path).name == category + ".xml"]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one canonical object XML for {category}, found {matches}")
        roots.add(matches[0])
    selected = set()
    pending = list(sorted(roots))
    while pending:
        path = pending.pop()
        if path in selected:
            continue
        if path not in entries:
            raise RuntimeError(f"Resource not present in pinned Git tree: {path}")
        selected.add(path)
        if not path.endswith(".xml"):
            continue
        document = ET.parse(source / path).getroot()
        compiler = document.find("compiler")
        directory = posixpath.dirname(path)
        for node in document.iter():
            filename = node.get("file")
            if not filename:
                continue
            asset_dir = ""
            if compiler is not None and node.tag in ("mesh", "texture"):
                asset_dir = compiler.get("meshdir" if node.tag == "mesh" else "texturedir", "")
            candidate = posixpath.normpath(posixpath.join(directory, asset_dir, filename.replace("\\", "/")))
            if not candidate.startswith(PACKAGE + "assets/") or candidate not in entries:
                raise RuntimeError(f"Unresolved {node.tag} dependency: {path} -> {filename} ({candidate})")
            pending.append(candidate)
    return selected, sorted(roots), sorted(categories)


def _download_source(source: Path, archive: Path, *, full=False, metadata_only=False):
    entries_by_path = _source_tree()
    metadata = _metadata_paths(entries_by_path)
    _fetch_entries(source, [entries_by_path[p] for p in sorted(metadata)], "Source metadata")
    if metadata_only:
        return None
    if full:
        selected, roots, categories = set(entries_by_path), [], []
    else:
        resources, roots, categories = _profile_resources(source, entries_by_path)
        selected = metadata | resources
    entries = [entries_by_path[path] for path in sorted(selected)]
    total = sum(entry.get("size", 0) for entry in entries)
    profile = {
        "name": "full" if full else "remaining-goals-two-tasks-v1",
        "suite": "all" if full else "libero_10", "tasks": "all" if full else PROFILE_TASKS,
        "scope": "Entire simulation package" if full else "Two unmodified canonical scenes, including all distractors and arena dependencies; other tasks are not provisioned",
        "resource_roots": roots, "object_categories": categories,
        "file_count": len(entries), "total_bytes": total,
    }
    print(f"Selected profile {profile['name']}: {len(entries)} files, {total / 1048576:.1f} MiB", flush=True)
    _fetch_entries(source, [entry for entry in entries if entry["path"] not in metadata], "Scene resources")
    (RUNTIME / "source_tree.json").write_text(json.dumps({"commit": COMMIT, "profile": profile, "entries": entries}, indent=2), encoding="utf-8")
    # Keep a local verified source archive for independent init-file checks.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for entry in entries:
            package.write(source / entry["path"], f"LIBERO-{COMMIT}/{entry['path']}")
    return profile


def _install_dependencies(index_url):
    venv = RUNTIME / "venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        print("Creating isolated virtual environment", flush=True)
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
    log_path = RUNTIME / "pip-install.log"
    print(f"Installing simulation dependencies; log: {log_path}", flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                        "--index-url", index_url, "--timeout", "60",
                        "--cache-dir", str(RUNTIME / "pip-cache"), *REQUIREMENTS],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return python


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-url", default=os.environ.get("PIP_INDEX_URL") or "https://pypi.org/simple",
                        help="Python dependency index (default: PIP_INDEX_URL, then PyPI)")
    parser.add_argument("--dependencies-only", action="store_true", help="Install the simulation dependencies without downloading LIBERO assets")
    parser.add_argument("--source-only", action="store_true", help="Download and verify source assets without installing dependencies")
    parser.add_argument("--metadata-only", action="store_true", help="Download verified Python, BDDL, initial states and XML only")
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("--full", dest="full", action="store_true", default=True,
                         help="Provision the entire official simulation package (default)")
    profile.add_argument("--two-task-profile", dest="full", action="store_false",
                         help="Legacy minimal basket/stove assets only; insufficient for the expanded default task catalog")
    args = parser.parse_args(argv)
    if not args.index_url.strip():
        parser.error("--index-url must not be empty")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError("Use the existing Python 3.10 environment with PyTorch")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=RUNTIME / "source-download.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.dependencies_only:
        _install_dependencies(args.index_url)
        return
    archive = RUNTIME / f"LIBERO-{COMMIT}.zip"
    source = RUNTIME / f"LIBERO-{COMMIT}"
    if args.source_only or args.metadata_only:
        _download_source(source, archive, full=args.full, metadata_only=args.metadata_only)
        return
    # Source blobs and wheels are independent downloads. Keep one dependency
    # installer, with both phases joined before writing a usable runtime lock.
    with ThreadPoolExecutor(max_workers=2) as setup_pool:
        dependencies = setup_pool.submit(_install_dependencies, args.index_url)
        profile = _download_source(source, archive, full=args.full)
        python = dependencies.result()
    if os.name == "nt":
        subprocess.run([str(python), str(ROOT / "scripts" / "prepare_remaining_windows.py")], check=True)
    with (RUNTIME / "pip-install.log").open("a", encoding="utf-8") as log:
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation",
                        "-e", str(source)], stdout=log, stderr=subprocess.STDOUT, check=True)
    config_dir = RUNTIME / "libero_config"
    config_dir.mkdir(exist_ok=True)
    package_root = source / "libero" / "libero"
    datasets = RUNTIME / "datasets"
    datasets.mkdir(exist_ok=True)
    paths = {
        "benchmark_root": str(package_root), "bddl_files": str(package_root / "bddl_files"),
        "init_states": str(package_root / "init_files"), "assets": str(package_root / "assets"),
        "datasets": str(datasets),
    }
    (config_dir / "config.yaml").write_text(json.dumps(paths, indent=2), encoding="utf-8")
    lock = {
        "libero_commit": COMMIT, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "source_method": "pinned_git_tree_verified_blobs",
        "source_profile": profile,
        "dependency_index_url": args.index_url,
        "requirements": REQUIREMENTS, "python": str(python), "parent_python": sys.executable,
        "libero_config_path": str(config_dir), "mujoco_gl": "glfw" if os.name == "nt" else "egl",
    }
    (RUNTIME / "runtime.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    print(json.dumps(lock, indent=2), flush=True)


if __name__ == "__main__":
    main()
