"""CPU-only metadata fixtures; no model package is installed or imported."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import policy_worker as subject


def _distribution(name, version):
    return SimpleNamespace(metadata={"Name": name}, version=version)


def _fake_metadata(monkeypatch, candidates, effective):
    calls = []

    def version(name):
        calls.append(name)
        if name not in effective:
            raise importlib.metadata.PackageNotFoundError(name)
        return effective[name]

    monkeypatch.setattr(subject.importlib.metadata, "distributions", lambda: iter(candidates))
    monkeypatch.setattr(subject.importlib.metadata, "version", version)
    return calls


def test_ordinary_environment_preserves_dictionary_and_policy_metadata(monkeypatch):
    calls = _fake_metadata(monkeypatch, [
        _distribution("Pillow", "10.2.0"),
        _distribution(None, "ignored"),
        _distribution("NumPy", "1.24.4"),
    ], {"numpy": "1.24.4", "pillow": "10.2.0"})
    config = {"adapter_options": {"checkpoint": "fixture/checkpoint"},
              "execution": {"random_seed": 7}}
    policy = SimpleNamespace(metadata={"fixture": np.array([1, 2]), "path": Path("weights")})

    record = subject.provenance(config, policy)

    assert type(record["packages"]) is dict
    assert record["packages"] == {"numpy": "1.24.4", "pillow": "10.2.0"}
    assert list(record["packages"]) == ["numpy", "pillow"]
    assert calls == ["numpy", "pillow"]
    assert record["package_metadata_resolution"]["duplicate_distributions"] == {}
    assert record["policy_metadata"] == {"fixture": [1, 2], "path": "weights"}
    assert record["checkpoint"] == "fixture/checkpoint"
    assert record["random_seed"] == 7
    assert record["checkpoint_bytes_verified"] is False
    json.dumps(record, allow_nan=False)


def test_equivalent_names_are_resolved_once_and_all_duplicates_are_diagnostic(monkeypatch):
    candidates = [
        _distribution("Example_Package", "1.0"),
        _distribution("example.package", "3.0"),
        _distribution("EXAMPLE---PACKAGE", "2.0"),
        _distribution("example-package", "4.0"),
    ]
    calls = _fake_metadata(monkeypatch, candidates, {"example-package": "3.0"})

    packages, resolution = subject._package_metadata()

    assert packages == {"example-package": "3.0"}
    assert calls == ["example-package"]
    assert resolution["duplicate_distributions"] == {
        "example-package": [
            {"name": "EXAMPLE---PACKAGE", "version": "2.0"},
            {"name": "Example_Package", "version": "1.0"},
            {"name": "example-package", "version": "4.0"},
            {"name": "example.package", "version": "3.0"},
        ]}
    assert resolution["resolver"] == "importlib.metadata.version"
    assert "not import precedence" in resolution["duplicate_order"]
    assert "does not establish" in resolution["scope"]
    assert "module.__version__" in resolution["scope"]


@pytest.mark.parametrize("effective, parent", [("2.10", "2.9"), ("1.24.4", "1.26.0")])
def test_overlay_version_comes_from_resolver_not_lexical_or_semantic_max(
        monkeypatch, effective, parent):
    candidates = [_distribution("numpy", effective), _distribution("numpy", parent)]
    _fake_metadata(monkeypatch, candidates, {"numpy": effective})

    packages, resolution = subject._package_metadata()

    assert packages == {"numpy": effective}
    assert len(resolution["duplicate_distributions"]["numpy"]) == 2


def test_candidate_iteration_order_does_not_change_resolved_versions_or_diagnostics(monkeypatch):
    candidates = [_distribution("numpy", "1.26.0"), _distribution("Pillow", "10.2"),
                  _distribution("numpy", "1.24.4"), _distribution("Pillow", "9.5")]
    effective = {"numpy": "1.24.4", "pillow": "10.2"}
    _fake_metadata(monkeypatch, candidates, effective)
    first = subject.provenance({})
    candidates.reverse()

    assert subject.provenance({}) == first


def test_identical_duplicate_metadata_is_not_dropped(monkeypatch):
    _fake_metadata(monkeypatch, [_distribution("numpy", "1.24.4") for _ in range(2)],
                   {"numpy": "1.24.4"})

    packages, resolution = subject._package_metadata()

    assert packages == {"numpy": "1.24.4"}
    assert resolution["duplicate_distributions"]["numpy"] == [
        {"name": "numpy", "version": "1.24.4"}, {"name": "numpy", "version": "1.24.4"}]


def test_missing_resolver_result_cannot_fall_back_to_enumerated_version(monkeypatch):
    _fake_metadata(monkeypatch, [_distribution("disappeared", "99.0")], {})

    with pytest.raises(importlib.metadata.PackageNotFoundError, match="disappeared"):
        subject.provenance({})


def test_metadata_collection_does_not_import_policy_modules_or_consume_rng(monkeypatch):
    _fake_metadata(monkeypatch, [_distribution("torch", "fixture-only")],
                   {"torch": "fixture-only"})

    def forbidden_import(*args, **kwargs):
        raise AssertionError("Metadata collection must not import a model module")

    monkeypatch.setattr(subject.importlib, "import_module", forbidden_import)
    python_rng = random.getstate()
    numpy_rng = np.random.get_state()
    imported_modules = set(sys.modules)

    record = subject.provenance({})

    assert record["packages"] == {"torch": "fixture-only"}
    assert set(sys.modules) == imported_modules
    assert random.getstate() == python_rng
    after = np.random.get_state()
    assert after[0] == numpy_rng[0]
    np.testing.assert_array_equal(after[1], numpy_rng[1])
    assert after[2:] == numpy_rng[2:]


def test_real_metadata_resolver_follows_path_priority_not_inventory_order(monkeypatch, tmp_path):
    """Use actual stdlib metadata lookup over tiny overlay/parent dist-info dirs."""
    name = "remaining-provenance-fixture"
    distributions = []
    layers = []
    for layer, version in [("overlay", "2.10"), ("parent", "2.9")]:
        root = tmp_path / layer
        info = root / f"remaining_provenance_fixture-{version}.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8")
        distributions.append(importlib.metadata.PathDistribution(info))
        layers.append(str(root))
    # Deliberately enumerate the parent first. This is not lookup precedence.
    monkeypatch.setattr(subject.importlib.metadata, "distributions",
                        lambda: iter(reversed(distributions)))
    original_path = list(sys.path)
    monkeypatch.setattr(sys, "path", layers + original_path)

    first, diagnostics = subject._package_metadata()

    assert first == {name: "2.10"}
    assert first[name] == importlib.metadata.version(name)
    monkeypatch.setattr(sys, "path", list(reversed(layers)) + original_path)
    second, new_diagnostics = subject._package_metadata()
    assert second == {name: "2.9"}
    assert second[name] == importlib.metadata.version(name)
    assert new_diagnostics == diagnostics


def test_current_interpreter_numpy_matches_stdlib_metadata_without_importing_models():
    packages, resolution = subject._package_metadata()

    assert packages["numpy"] == importlib.metadata.version("numpy")
    assert list(packages) == sorted(packages)
    assert all(name == name.lower() and "_" not in name and "." not in name for name in packages)
    json.dumps({"packages": packages, "resolution": resolution}, allow_nan=False)
