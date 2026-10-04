"""Publication scope and source preservation; no simulator or network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import zipfile

from benchmark.remaining_goals import package_audit as package
from tests.test_remaining_package import create, delivery, pack  # noqa: F401 -- pytest fixtures


def test_bundle_includes_optional_clone_metadata_and_only_benchmark_docs(delivery):
    root, _, _, output = delivery
    included = {
        "README.md": "# LIBERO-PAB\n",
        "THIRD_PARTY_NOTICES.md": "External dependency attribution.\n",
        "data/README.md": "Candidate artifact download and rebuild instructions.\n",
        "pyproject.toml": "[project]\nname = 'libero-pab'\n",
        "requirements-dev.txt": "pytest>=8\n",
        ".gitignore": "__pycache__/\n",
        ".gitattributes": "*.py text eol=lf\n",
        "CITATION.cff": "cff-version: 1.2.0\n",
        "docs/remaining_goals_installation.md": "Benchmark installation.\n",
    }
    excluded = {
        "plan/research_master_plan.md": "Unrelated research plan.\n",
        "docs/research/private_notes.md": "Research discussion.\n",
        "docs/unrelated.md": "Other project documentation.\n",
        "configs/mini_pab.yaml": "legacy: true\n",
    }
    for relative, content in {**included, **excluded}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    create(delivery)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert set(included) <= names
        assert names.isdisjoint(excluded)
        for name, text in included.items():
            assert archive.read(name) == text.encode("utf-8")


def test_source_packaging_is_independent_of_checkout_file_times(delivery):
    root, manifest, replay, output = delivery
    create(delivery)
    source = root / "benchmark/example/helper.py"
    os.utime(source, (946684800, 946684800))
    second_output = root / "after-checkout.zip"
    package.create_bundle(root, manifest, replay, second_output)
    with zipfile.ZipFile(output) as before, zipfile.ZipFile(second_output) as after:
        # The index binds file contents, not local checkout times. Payload
        # timestamps are fixed, so copying or cloning cannot alter these bytes.
        assert json.loads(before.read(package.INDEX)) == json.loads(after.read(package.INDEX))
        assert before.read("benchmark/example/helper.py") == after.read("benchmark/example/helper.py")
        assert before.getinfo("benchmark/example/helper.py").date_time == after.getinfo("benchmark/example/helper.py").date_time


def test_bundle_omits_local_overrides_and_fake_credentials_but_keeps_public_runtime(delivery):
    root, _, _, output = delivery
    fake_token = "FAKE_PUBLICATION_TEST_SECRET_NOT_A_REAL_TOKEN"
    fake_private_path = "C:" + "/Users/" + "fake_user/private/python.exe"
    local_body = json.dumps({"token": fake_token, "python": fake_private_path}).encode()
    private_names = (
        "configs/remaining_goals/local/model.json",
        "configs/remaining_goals/local/nested/settings.yaml",
        "configs/remaining_goals/local/README.md",
        "configs/remaining_goals/custom.local.json",
        "configs/remaining_goals/runtime/model.local.json",
        "configs/remaining_goals/runtime/model.LOCAL.JSON",
    )
    for name in private_names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(local_body)
    public_name = "configs/remaining_goals/runtime/model.json"
    public_body = b'{"adapter_options": {"repo_path": "external/model"}}\n'
    (root / public_name).write_bytes(public_body)
    create(delivery)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()).isdisjoint(private_names)
        assert archive.read(public_name) == public_body
        assert all(fake_token.encode() not in archive.read(name) for name in archive.namelist())


def test_public_runtime_import_closure_needs_no_legacy_builder_or_arenas():
    root = Path(__file__).resolve().parents[1]
    seeds = list((root / "benchmark/remaining_goals").rglob("*.py"))
    seeds += list((root / "scripts").glob("*remaining*.py"))
    closure = {path.relative_to(root).as_posix() for path in package._python_closure(root, seeds)}
    assert "benchmark/states/mujoco_state.py" in closure
    assert "benchmark/states/builder.py" not in closure
    assert not any(name.startswith(("benchmark/arena/", "benchmark/tasks/")) for name in closure)


def test_actual_source_and_test_closure_passes_immutable_private_path_guard():
    root = Path(__file__).resolve().parents[1]
    seeds = list((root / "benchmark/remaining_goals").rglob("*.py"))
    seeds += list((root / "scripts").glob("*remaining*.py"))
    seeds += list((root / "tests").glob("test_remaining*.py"))
    seeds += list((root / "tests").glob("test_prepare_remaining*.py"))
    for relative in ("tests/__init__.py", "tests/conftest.py"):
        if (root / relative).is_file():
            seeds.append(root / relative)
    rejected = [path.relative_to(root).as_posix()
                for path in package._python_closure(root, seeds)
                if package.PRIVATE_HOME.search(path.read_text(encoding="utf-8-sig"))]
    assert rejected == []
