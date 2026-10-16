"""Task008 file-only CLI and shipping configuration integration checks."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmark.remaining_goals.finish import cli
from benchmark.remaining_goals.finish.data_profiles import validate_domain_config
from benchmark.remaining_goals.finish.data_registry import validate_source_registry
from tests.finish_domain_helpers import make_assets


def config_file(tmp_path):
    config = make_assets(tmp_path / "synthetic_assets")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path, config


def test_register_cli_is_file_only_and_does_not_import_simulator_or_model(tmp_path):
    config, _ = config_file(tmp_path)
    output = tmp_path / "registered"
    script = """
import sys
class NoExperimentImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'libero', 'robosuite', 'mujoco', 'transformers', 'torch'}:
            raise AssertionError('unexpected experiment dependency: ' + fullname)
sys.meta_path.insert(0, NoExperimentImports())
from benchmark.remaining_goals.finish.cli import main
raise SystemExit(main(['register-data', '--config', sys.argv[1], '--out', sys.argv[2]]))
"""
    result = subprocess.run([sys.executable, "-c", script, str(config), str(output)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "registered_file_only"
    assert summary["ready_for_feature_export"] is False
    assert summary["simulation_created"] is summary["weights_loaded"] is False
    registry = validate_source_registry(json.loads((output / "registry.json").read_text()), verify_files=True)
    assert registry["labels_generated"] == 0 and registry["demo_to_init_mapping"] is None
    assert registry["registry_sha256"] == summary["registry_sha256"]
    assert not (output / "audit.json").exists()


def test_register_cli_rejects_replaced_asset_and_existing_output(tmp_path, capsys):
    path, config = config_file(tmp_path)
    output = tmp_path / "registry"
    args = ["register-data", "--config", str(path), "--out", str(output)]
    assert cli.main(args) == 0
    before = (output / "registry.json").read_bytes()
    assert cli.main(args) == 2
    assert (output / "registry.json").read_bytes() == before
    Path(config["bddl_path"]).write_text("replacement at identical path", encoding="utf-8")
    assert cli.main([*args[:-1], str(tmp_path / "changed_registry")]) == 2
    assert not (tmp_path / "changed_registry").exists()
    assert "expected_assets" in capsys.readouterr().err


def test_prepare_normal_cli_forwards_explicit_registry_without_starting_work(tmp_path, monkeypatch):
    from benchmark.remaining_goals.finish import workflow
    calls = []
    def prepare(indices, output, **kwargs):
        calls.append((indices, output, kwargs))
        return {"status": "prepared"}
    monkeypatch.setattr(workflow, "prepare_normal_bank", prepare)
    assert cli.main(["prepare-normal", "--indices", "35", "36", "37", "38", "39",
                     "--source-registry", "registry.json", "--out", str(tmp_path / "bank")]) == 0
    assert calls == [([35, 36, 37, 38, 39], str(tmp_path / "bank"),
                      {"environment_config": None, "source_registry": "registry.json"})]


def test_new_data_example_declares_all_groups_and_actual_asset_hashes():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "configs/remaining_goals/finish/data.example.json").read_text())
    profile = validate_domain_config(config)
    assert len(profile["domains"]["head_demonstration"]["groups"]["head_train"]) == 30
    assert config["expected_assets"]["hdf5_sha256"] == "3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af"
    assert "trajectory_source_map" not in config and "split" not in config


@pytest.mark.parametrize("purpose", ["validation_shadow", "normal_active", "remain_active", "remain_shadow"])
def test_new_job_examples_cannot_silently_select_legacy_identity(purpose):
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / f"configs/remaining_goals/finish/{purpose}.example.json").read_text())
    assert config["schema_version"] == "remaining-finish-job-v2"
    assert config["source_registry"].endswith("/registry/registry.json")
    assert config["purpose"] == purpose
    assert "split" not in config and "alternative_confirmation" not in config
