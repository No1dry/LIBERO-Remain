"""Actual XML resolver + synthetic HDF integration; no real simulation or model."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

h5py = pytest.importorskip("h5py", reason="synthetic XML asset audit integration requires h5py")

from benchmark.remaining_goals.finish import cli, data, xml_assets
from benchmark.remaining_goals.finish.data_registry import build_source_registry
from tests.finish_domain_helpers import FakeProvider, make_assets

LEGACY = "/home/yifengz/workspace/libero-dev/chiliocosm/assets/"
ROBO = "/home/yifengz/workspace/robosuite-master/robosuite/models/assets/"
TEXTURE = LEGACY + "scenes/../textures/seamless_wood_planks_floor.png"
MESH = ROBO + "robots/panda/meshes/link0.stl"


def setup_assets(monkeypatch, tmp_path, *, defects=False):
    config = make_assets(tmp_path / "source")
    roots = {"libero": str(tmp_path / "fixed/libero/assets"),
             "robosuite": str(tmp_path / "fixed/robosuite/models/assets")}
    texture = Path(roots["libero"]) / "textures/seamless_wood_planks_floor.png"
    mesh = Path(roots["robosuite"]) / "robots/panda/meshes/link0.stl"
    for path in (texture, mesh):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tiny test-only resource: " + path.name.encode())
    original = (f'<mujoco model="synthetic"><compiler angle="radian" meshdir="meshes/"/>'
                f'<asset><texture name="floor" file="{TEXTURE}"/><mesh name="arm" file="{MESH}" scale="1 2 3"/>'
                '</asset><worldbody><body name="fixed" pos="1 2 3"/></worldbody></mujoco>')
    with h5py.File(config["hdf5_path"], "a") as source:
        for group in source["data"].values():
            group.attrs["model_file"] = original
        if defects:
            # All defects are in head_unused. A train/validation-only scan would
            # incorrectly permit provider construction and miss every failure.
            source["data/demo_0"].attrs["model_file"] = original.replace(TEXTURE, LEGACY + "textures/missing.png")
            source["data/demo_4"].attrs["model_file"] = original.replace(TEXTURE, LEGACY + "../../outside.png")
            source["data/demo_40"].attrs["model_file"] = original.replace(TEXTURE, "/unknown-root/texture.png")
            source["data/demo_49"].attrs["model_file"] = original.replace("<worldbody>", '<include file="extra.xml"/><worldbody>')
    config["expected_assets"]["hdf5_sha256"] = data._file_hash(config["hdf5_path"])
    actual_scan = xml_assets.scan_xml_assets
    fixed_roots = roots
    # Only inject approved tiny resource locations. The scanner, resolver,
    # containment checks, hashes and validation remain their production code.
    monkeypatch.setattr(xml_assets, "scan_xml_assets", lambda trajectories, roots=None:
                        actual_scan(trajectories, roots=roots if roots is not None else fixed_roots))
    return config, roots, texture, mesh, original


def config_path(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def resign(audit):
    audit["audit_sha256"] = data.canonical_hash({k: v for k, v in audit.items() if k != "audit_sha256"})
    return audit


def test_register_scans_all_fifty_original_xmls_without_experiment_imports(monkeypatch, tmp_path, capsys):
    config, roots, texture, _, original = setup_assets(monkeypatch, tmp_path)
    expected_registry = build_source_registry(config)
    original_hdf = Path(config["hdf5_path"]).read_bytes()
    class NoExperimentImports:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"libero", "robosuite", "mujoco", "transformers", "torch"}:
                raise AssertionError("file-only registration imported " + fullname)
    monkeypatch.setattr(sys, "meta_path", [NoExperimentImports(), *sys.meta_path])
    out = tmp_path / "registered"
    assert cli.main(["register-data", "--config", str(config_path(tmp_path, config)), "--out", str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "registered_file_only" and result["ready_for_feature_export"] is False
    assert result["simulation_created"] is result["weights_loaded"] is False
    assert data.read_json(out / "registry.json") == expected_registry
    assert data.read_json(out / "registration.json") == result
    scan = data.read_json(out / "xml_asset_scan.json")
    assert scan["status"] == "resolved" and scan["errors"] == [] and scan["trajectory_count"] == 50
    assert scan["file_reference_occurrences"] == 100 and scan["resolved_reference_occurrences"] == 100
    assert {row["trajectory_id"] for row in scan["sources"]} == {f"demo_{i}" for i in range(50)}
    assert all(row["original_xml"] == original for row in scan["sources"])
    assert all(row["original_xml_sha256"] == hashlib.sha256(original.encode()).hexdigest() for row in scan["sources"])
    mapping = next(row for row in scan["sources"][0]["mappings"] if row["original"] == TEXTURE)
    assert Path(mapping["resolved"]) == texture.resolve()
    assert mapping["target_sha256"] == hashlib.sha256(texture.read_bytes()).hexdigest()
    assert set(scan["approved_roots"]) == set(roots)
    assert Path(config["hdf5_path"]).read_bytes() == original_hdf and not (out / "audit.json").exists()


def test_unused_dependency_errors_are_aggregated_before_provider_and_preserved(monkeypatch, tmp_path):
    config, _, _, _, _ = setup_assets(monkeypatch, tmp_path, defects=True)
    before = Path(config["hdf5_path"]).read_bytes()
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out,
        provider_factory=lambda _: pytest.fail("all XMLs must pass before creating a provider"))
    assert report["status"] == "insufficient" and report["rows"] == [] and report["provider_identity"] == {}
    assert report["work_counts"]["restore_attempts"] == report["work_counts"]["hold_attempts"] == 0
    scan = report["xml_asset_scan"]
    assert scan["trajectory_count"] == 50 and scan["status"] == "unresolved"
    assert {row["trajectory_id"] for row in scan["errors"]} >= {"demo_0", "demo_4", "demo_40", "demo_49"}
    assert len(scan["errors"]) >= 4
    assert data.read_json(out / "xml_asset_scan.json") == scan
    assert data.read_json(out / "audit.json") == report
    assert Path(config["hdf5_path"]).read_bytes() == before


def test_register_dependency_failure_writes_registry_and_scan_with_nonzero_exit(monkeypatch, tmp_path, capsys):
    config, _, _, _, _ = setup_assets(monkeypatch, tmp_path, defects=True)
    expected_registry = build_source_registry(config)
    out = tmp_path / "registry"
    args = ["register-data", "--config", str(config_path(tmp_path, config)), "--out", str(out)]
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "insufficient" and result["xml_asset_errors"] >= 4
    assert result["ready_for_feature_export"] is False and result["simulation_created"] is False
    assert data.read_json(out / "registry.json") == expected_registry
    assert data.read_json(out / "xml_asset_scan.json")["status"] == "unresolved"
    before = {path.name: path.read_bytes() for path in out.iterdir()}
    assert cli.main(args) == 2
    assert {path.name: path.read_bytes() for path in out.iterdir()} == before


def test_audit_binds_scan_and_passes_private_copy_only_after_complete_preflight(monkeypatch, tmp_path):
    config, _, _, _, _ = setup_assets(monkeypatch, tmp_path)
    config["_xml_asset_scan"] = {"untrusted": "a caller cannot substitute a claimed scan"}
    saved_config = deepcopy(config)
    provider, out = FakeProvider(), tmp_path / "audit"
    def create(private):
        assert private is not config and private["_xml_asset_scan"]["status"] == "resolved"
        assert private["_xml_asset_scan"]["trajectory_count"] == 50
        assert (out / "xml_asset_scan.json").is_file()
        private["_xml_asset_scan"]["errors"].append({"test_only": "isolated private mutation"})
        return provider
    report = data.audit_demonstrations(config, out=out, provider_factory=create)
    assert report["status"] == "ready_for_feature_export", report["issues"]
    assert report["xml_asset_scan"]["errors"] == [] and config == saved_config
    assert provider.closed and len(provider.restore_calls) == 70
    data.validate_audit(report, base_dir=out)
    assert data._identities(report, {"fake_base": True})["data_identity"]["audit_sha256"] == report["audit_sha256"]


def test_changed_target_resource_rejects_reuse_before_any_feature_call(monkeypatch, tmp_path):
    config, _, texture, _, _ = setup_assets(monkeypatch, tmp_path)
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out, provider_factory=lambda _: FakeProvider())
    assert report["status"] == "ready_for_feature_export"
    texture.write_bytes(b"different pixels at the same approved path")
    with pytest.raises(ValueError):
        data.validate_audit(report, base_dir=out)
    class NeverCalled:
        def predict(self, *args):
            pytest.fail("changed assets must be rejected before a model call")
    with pytest.raises(ValueError):
        data.export_features(out, NeverCalled(), tmp_path / "features", base_identity={"fake": True})
    assert not (tmp_path / "features").exists()


def test_target_mutation_during_close_retains_partial_but_cannot_be_ready(monkeypatch, tmp_path):
    config, _, texture, _, _ = setup_assets(monkeypatch, tmp_path)
    class MutatingClose(FakeProvider):
        def close(self):
            super().close()
            texture.write_bytes(b"changed during provider close")
    provider, out = MutatingClose(), tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert report["status"] == "insufficient" and provider.closed and len(report["rows"]) == 70
    assert any(issue["reason"] == "xml_asset_changed" for issue in report["issues"])
    assert data.read_json(out / "audit.json") == report


@pytest.mark.parametrize("change", ["remove_scan", "omit_unused", "different_xml"])
def test_resigned_audit_cannot_drop_scan_coverage_or_change_source_xml(monkeypatch, tmp_path, change):
    config, _, _, _, _ = setup_assets(monkeypatch, tmp_path)
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out, provider_factory=lambda _: FakeProvider())
    assert report["status"] == "ready_for_feature_export"
    if change == "remove_scan":
        del report["xml_asset_scan"]
    elif change == "omit_unused":
        report["xml_asset_scan"]["sources"] = [row for row in report["xml_asset_scan"]["sources"] if row["trajectory_id"] != "demo_0"]
    else:
        report["xml_asset_scan"]["sources"][0]["original_xml_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        data.validate_audit(resign(report), base_dir=out)
