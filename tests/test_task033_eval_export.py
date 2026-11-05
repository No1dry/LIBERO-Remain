"""Export a temporary Git commit; no benchmark/native code is executed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_task033_eval.py"
GIT = shutil.which("git") or "C:/Users/robot/AppData/Local/Programs/Git/cmd/git.exe"


def git(repo, *arguments):
    return subprocess.run([GIT, "-C", str(repo), *arguments], check=True, capture_output=True).stdout


def commit(repo):
    git(repo, "add", ".")
    git(repo, "-c", "user.name=CPU Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic source snapshot")
    return git(repo, "rev-parse", "HEAD").decode().strip()


def source_tree(repo):
    payload = {
        "benchmark/__init__.py": b"# benchmark package\n",
        "benchmark/remaining_goals/nine_catalog.py": b"# approved nine definitions\n",
        "benchmark/remaining_goals/task_catalog.py": b"# preserved legacy definitions\n",
        "benchmark/remaining_goals/headless/nine_cli.py": b"# nine default command\n",
        "benchmark/remaining_goals/headless/scoped_workflow.py": b"# legacy reader dependency\n",
        "pyproject.toml": b"[project]\nname='synthetic-test-only'\n",
        "LICENSE": b"Synthetic fixture license bytes, not a project license.\n",
        "scripts/setup_remaining_libero.py": b"COMMIT='synthetic'\n",
        "scripts/remaining_libero.py": b"# setup/doctor wrapper\n",
        "configs/remaining_goals/runtime/openvla_oft_sog10.json": b'{"suite":"libero_10"}\n',
        "configs/remaining_goals/headless/nine-normal00.example.json": b'{"protocol":"nine-normal00"}\n',
        "configs/remaining_goals/headless/nine-mask10.example.json": b'{"protocol":"nine-mask10"}\n',
        "docs/task033_nine_task_runbook.md": b"# Nine task runbook\n",
        "docs/task033_eval_README.md": b"# Eval: nine LIBERO-10 tasks\n",
    }
    excluded = {
        "README.md": b"# historical source README\n",
        "configs/remaining_goals/headless/ten_tasks.json": b"{}",
        "configs/remaining_goals/runtime/libero90.json": b"{}",
        "docs/headless_ten_task_baseline_runbook.md": b"old6+4",
        "data/secret.npy": b"not source",
        "raw/run.json": b"not source",
        "benchmark/raw/score.json": b"not source",
        "collaboration/tasks/private.md": b"not source",
        "research/analysis.py": b"not source",
    }
    for name, raw in {**payload, **excluded}.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return payload


def run_export(repo, revision, output):
    return subprocess.run([sys.executable, str(SCRIPT), "--source-revision", revision,
        "--output", str(output), "--git", GIT], cwd=repo, capture_output=True, text=True)


@pytest.mark.skipif(not Path(GIT).is_file(), reason="Git executable unavailable for pure file fixture")
def test_exact_commit_export_has_nine_defaults_and_hashes_every_payload(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    payload = source_tree(repo)
    revision = commit(repo)
    # A later commit and dirty checkout must not enter the accepted export.
    (repo / "benchmark/newer.py").write_text("# newer unaccepted commit\n")
    commit(repo)
    (repo / "benchmark/remaining_goals/nine_catalog.py").write_text("# dirty unreviewed code\n")
    (repo / "docs/task033_eval_README.md").write_text("# dirty README\n")
    (repo / "benchmark/untracked.py").write_text("# untracked\n")
    before = git(repo, "status", "--porcelain=v1", "-uall")
    output = tmp_path / "eval.zip"
    result = run_export(repo, revision, output)
    assert result.returncode == 0, result.stderr
    assert git(repo, "status", "--porcelain=v1", "-uall") == before
    with zipfile.ZipFile(output) as archive:
        expected = {**payload, "README.md": payload["docs/task033_eval_README.md"]}
        assert set(archive.namelist()) == set(expected) | {"SOURCE_EXPORT.json"}
        metadata = json.loads(archive.read("SOURCE_EXPORT.json"))
        assert metadata["source_revision"] == revision
        assert metadata["default_entrypoint"] == "python -m benchmark.remaining_goals.headless.nine_cli"
        assert metadata["legacy_definition_paths"] == ["benchmark/remaining_goals/task_catalog.py"]
        assert metadata["source_paths"]["README.md"] == "docs/task033_eval_README.md"
        assert metadata["files"] == {name: hashlib.sha256(raw).hexdigest() for name, raw in expected.items()}
        for name, raw in expected.items():
            assert archive.read(name) == raw
    original = output.read_bytes()
    second = run_export(repo, revision, output)
    assert second.returncode != 0 and output.read_bytes() == original


@pytest.mark.skipif(not Path(GIT).is_file(), reason="Git executable unavailable for pure file fixture")
def test_export_rejects_revision_without_committed_nine_docs(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    source_tree(repo)
    missing = repo / "docs/task033_nine_task_runbook.md"
    raw = missing.read_bytes()
    missing.unlink()
    revision = commit(repo)
    missing.write_bytes(raw)  # The working tree cannot fill a missing commit asset.
    output = tmp_path / "eval.zip"
    result = run_export(repo, revision, output)
    assert result.returncode != 0
    assert "docs/task033_nine_task_runbook.md" in result.stderr
    assert not output.exists()
