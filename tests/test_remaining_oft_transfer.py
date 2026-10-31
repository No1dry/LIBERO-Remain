"""Explicit SOG10 transfer with CPU upstream doubles, never research weights."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.adapters import openvla, openvla_oft, oft_transfer as transfer
from benchmark.remaining_goals import evaluation, isolated_policy, policy_worker
from benchmark.remaining_goals.policy_transport import read_frame, write_frame
from tests.test_remaining_adapter_openvla import configuration, observation, upstream


def configs(tmp_path):
    primary = configuration(tmp_path)
    # Tiny fake bytes identify this software fixture only; never load a native
    # library, a research checkpoint, or claim published checkpoint equivalence.
    for name in transfer.INFERENCE_SOURCES:
        path = Path(primary["adapter_options"]["repo_path"]) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic API fixture: " + name)
    for name in ("action_head", "proprio_projector"):
        (Path(primary["adapter_options"]["checkpoint"]) / (name + "--300000_checkpoint.pt")).write_bytes(b"synthetic:" + name.encode())
    primary.update(model_id="openvla_oft", policy_id="test-only-sog10",
                   policy_factory=transfer.FACTORY, checkpoint_source=deepcopy(transfer.SOG10_SOURCE),
                   execution={"max_chunk_steps": 8, "random_seed": 7},
                   runtime={"python_executable": sys.executable, "startup_timeout_seconds": 30, "predict_timeout_seconds": 10})
    primary["adapter_options"]["repo_revision"] = transfer.REPO_REVISION
    extension = deepcopy(primary)
    extension["suite"] = extension["adapter_options"]["suite"] = "libero_90"
    extension["adapter_options"]["suite_transfer"] = deepcopy(transfer.TRANSFER)
    return primary, extension


def fake_upstream(options):
    api, torch, calls = upstream()
    model = api.get_model(None)
    model.norm_stats = json.loads((Path(options["checkpoint"]) / "dataset_statistics.json").read_text())
    api.NUM_ACTIONS_CHUNK = 8
    def check(cfg, loaded):
        calls.append(("original_check", cfg.task_suite_name))
        cfg.unnorm_key = openvla._normalization_key(loaded.norm_stats, cfg.task_suite_name)
    api.check_unnorm_key = check
    def initialize(cfg):
        calls.append(("initialize", cfg.task_suite_name))
        api.check_unnorm_key(cfg, model)
        return model, "original_action_head", "original_proprio_projector", None, "processor"
    api.initialize_model = initialize
    def prepare(raw, size):
        calls.append(("prepare", deepcopy(raw)))
        return {"full_image": raw["agentview_image"], "wrist_image": raw["robot0_eye_in_hand_image"],
                "state": np.r_[raw["robot0_eef_pos"], [0., 0., 0.], raw["robot0_gripper_qpos"]]}, None
    api.prepare_observation = prepare
    def action(cfg, loaded, obs, instruction, **kwargs):
        assert cfg.task_suite_name in {*transfer.TRAINING_SUITES, "libero_90"}
        assert cfg.unnorm_key in loaded.norm_stats
        assert kwargs["action_head"] == "original_action_head" and kwargs["proprio_projector"] == "original_proprio_projector"
        calls.append(("action", cfg.task_suite_name, cfg.unnorm_key, instruction, deepcopy(obs)))
        actions = np.arange(56, dtype=np.float64).reshape(8, 7) / 100
        actions[:, -1] = [0., 1.] * 4
        return actions
    api.get_action = action
    return api, torch, calls


def fake_load(options, revision):
    api, torch, _ = fake_upstream(options)
    return api, torch, transfer.REPO_REVISION


def worker_main():
    """Subprocess test seam: substitute upstream API, use the real worker/proxy."""
    openvla_oft._load_upstream = fake_load
    return policy_worker.main()


def test_explicit_transfer_retains_environment_suite_and_original_action_path(monkeypatch, tmp_path):
    primary, extension = configs(tmp_path)
    api, torch, calls = fake_upstream(extension["adapter_options"])
    original_check = api.check_unnorm_key
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: (api, torch, transfer.REPO_REVISION))
    policy = openvla_oft.make_policy(extension)
    try:
        assert api.check_unnorm_key is original_check
        assert policy.cfg.task_suite_name == extension["suite"] == "libero_90"
        assert calls[1] == ("initialize", "libero_90")
        assert not any(row[0] == "original_check" for row in calls)
        raw = observation(); before = {key: value.copy() if isinstance(value, np.ndarray) else deepcopy(value) for key, value in raw.items()}
        actions = policy.predict(raw, "Unmodified whole instruction")
        assert actions.shape == (8, 7) and actions.dtype == np.float64
        np.testing.assert_array_equal(actions[:, -1], [1., -1.] * 4)
        np.testing.assert_array_equal(actions[:, :6], (np.arange(56).reshape(8, 7) / 100)[:, :6])
        assert len([row for row in calls if row[0] == "action"]) == 1
        assert next(row for row in calls if row[0] == "action")[1:4] == ("libero_90", "libero_10_no_noops", "Unmodified whole instruction")
        assert "mask" not in next(row for row in calls if row[0] == "prepare")[1]
        for key in raw: np.testing.assert_array_equal(raw[key], before[key])
        assert transfer.validate_policy_metadata(extension, policy.metadata) == policy.metadata
        assert policy.metadata["dataset_statistics_sha256"] == hashlib.sha256((Path(extension["adapter_options"]["checkpoint"]) / "dataset_statistics.json").read_bytes()).hexdigest()
        assert policy.metadata["checkpoint_training_suites"] == transfer.TRAINING_SUITES
        assert set(policy.metadata["inference_source_sha256"]) == set(transfer.INFERENCE_SOURCES)
        assert len(policy.metadata["component_checkpoint_sha256"]) == 2
        assert policy.metadata["inference_configuration"]["num_images_in_input"] == 2
        assert policy.metadata["evaluation_track"] == "libero_90_zero_shot"
        assert not policy.metadata["explicit_stop"] and "finish" not in extension
    finally:
        directory = Path(policy.cfg.pretrained_checkpoint); policy.close()
    assert not directory.exists()
    assert transfer.validate_sog10_pair(primary, extension)["checkpoint"] == primary["adapter_options"]["checkpoint"]


def test_primary_selects_actual_existing_key_without_forced_transfer(monkeypatch, tmp_path):
    primary, _ = configs(tmp_path)
    path = Path(primary["adapter_options"]["checkpoint"]) / "dataset_statistics.json"
    path.write_text(json.dumps({"libero_10": {"action": {"q01": [-1.] * 7}}}))
    api, torch, calls = fake_upstream(primary["adapter_options"])
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: (api, torch, transfer.REPO_REVISION))
    policy = openvla_oft.make_policy(primary)
    try:
        assert policy.cfg.task_suite_name == "libero_10" and policy.cfg.unnorm_key == "libero_10"
        assert ("original_check", "libero_10") in calls
        assert policy.metadata["evaluation_track"] == "libero_10_primary"
        assert policy.metadata["suite_transfer"] is None
        transfer.validate_policy_metadata(primary, policy.metadata)
    finally: policy.close()


@pytest.mark.parametrize("fault", ["omitted", "null", "model", "factory", "source", "revision", "suite", "head", "normalization", "track", "flat_override"])
def test_transfer_is_narrow_explicit_and_rejects_before_importing_model(monkeypatch, tmp_path, fault):
    _, config = configs(tmp_path)
    if fault == "omitted": config["adapter_options"].pop("suite_transfer")
    elif fault == "null": config["adapter_options"]["suite_transfer"] = None
    elif fault == "model": config["model_id"] = "openvla"
    elif fault == "factory": config["policy_factory"] = "benchmark.remaining_goals.adapters.openvla:make_policy"
    elif fault == "source": config["checkpoint_source"]["repository"] = "another/model"
    elif fault == "revision": config["adapter_options"]["repo_revision"] = "f" * 40
    elif fault == "suite": config["suite"] = "libero_10"
    elif fault == "head": config["finish"] = {"head_artifact": "forbidden"}
    elif fault == "normalization": config["adapter_options"]["suite_transfer"]["normalization_key"] = "libero_90"
    elif fault == "track": config["adapter_options"]["suite_transfer"]["evaluation_track"] = "primary"
    else: config["adapter_options"]["normalization_suite"] = "libero_10"
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: pytest.fail("invalid transfer must fail before model import"))
    with pytest.raises(ValueError): openvla_oft.make_policy(config)


def test_other_models_never_receive_oft_transfer_exception(tmp_path):
    _, config = configs(tmp_path)
    with pytest.raises(ValueError, match="Unknown"):
        openvla._options(config)
    config["model_id"] = "groot_n1_7"
    checked = evaluation.check_config(config, "libero_90")
    assert not checked["static_configuration_ready"] and any("suite_transfer" in item for item in checked["errors"])


@pytest.mark.parametrize("fault", ["absent_key", "changed_loaded_stats", "loader_error", "skipped_check"])
def test_statistics_failures_never_fallback_and_restore_hook_cleanup(monkeypatch, tmp_path, fault):
    _, config = configs(tmp_path)
    api, torch, calls = fake_upstream(config["adapter_options"])
    original_check, original_init = api.check_unnorm_key, api.initialize_model
    temporary = []
    if fault == "absent_key":
        (Path(config["adapter_options"]["checkpoint"]) / "dataset_statistics.json").write_text('{"libero_10":{}}')
    def initialize(cfg):
        temporary.append(Path(cfg.pretrained_checkpoint))
        if fault == "loader_error": raise RuntimeError("synthetic loader failure")
        if fault == "skipped_check": return api.get_model(cfg), "a", "p", None, "processor"
        loaded = original_init(cfg)
        if fault == "changed_loaded_stats": loaded[0].norm_stats[cfg.unnorm_key] = {"changed": True}
        return loaded
    api.initialize_model = initialize
    monkeypatch.setattr(openvla_oft, "_load_upstream", lambda *args: (api, torch, transfer.REPO_REVISION))
    with pytest.raises((ValueError, RuntimeError)): openvla_oft.make_policy(config)
    assert api.check_unnorm_key is original_check
    assert all(not path.exists() for path in temporary)


@pytest.mark.parametrize("fault", ["checkpoint", "source", "repo", "crop", "precision", "seed", "chunk", "missing_transfer"])
def test_two_track_pair_must_use_same_original_sog10_components(tmp_path, fault):
    primary, extension = configs(tmp_path)
    if fault == "checkpoint": extension["adapter_options"]["checkpoint"] += "-other"
    elif fault == "source": extension["checkpoint_source"]["revision"] = "f" * 40
    elif fault == "repo": extension["adapter_options"]["repo_path"] += "-other"
    elif fault == "crop": extension["adapter_options"]["center_crop"] = False
    elif fault == "precision": extension["adapter_options"]["load_in_8bit"] = True
    elif fault == "seed": extension["execution"]["random_seed"] = 8
    elif fault == "chunk": extension["execution"]["max_chunk_steps"] = 7
    else: extension["adapter_options"].pop("suite_transfer")
    with pytest.raises(ValueError): transfer.validate_sog10_pair(primary, extension)


def test_real_subprocess_transport_preserves_transfer_config_and_actual_metadata(monkeypatch, tmp_path):
    _, config = configs(tmp_path)
    original = subprocess.Popen
    def launch(command, **kwargs):
        assert command[-2:] == ["-m", "benchmark.remaining_goals.policy_worker"]
        # Real Python child + real wire protocol. Only model API is synthetic.
        return original([command[0], "-c", "from tests.test_remaining_oft_transfer import worker_main; raise SystemExit(worker_main())"], **kwargs)
    monkeypatch.setattr(isolated_policy.subprocess, "Popen", launch)
    policy = isolated_policy.SubprocessPolicy(config)
    try:
        metadata = policy.provenance["policy_metadata"]
        assert transfer.validate_policy_metadata(config, metadata) == metadata
        assert metadata["evaluation_suite"] == "libero_90" and metadata["normalization_suite"] == "libero_10"
        assert metadata["suite_transfer"] == config["adapter_options"]["suite_transfer"]
        assert policy.provenance["checkpoint_bytes_verified"] is False
        policy.reset()
        raw = observation()
        with pytest.raises(ValueError, match="not permitted"):
            policy.predict(raw, "same full instruction")
        raw.pop("mask")
        output = policy.predict(raw, "same full instruction")
        assert output.shape == (8, 7)
        np.testing.assert_array_equal(output[:, -1], [1., -1.] * 4)
    finally: policy.close()
    assert policy.process.poll() == 0


@pytest.mark.parametrize("suite", ["libero_spatial", "libero_object", "libero_goal"])
def test_real_same_suite_sog10_worker_keeps_legacy_configuration(monkeypatch, tmp_path, suite):
    config, _ = configs(tmp_path)
    config["suite"] = config["adapter_options"]["suite"] = suite
    # These existing ordinary-worker choices are deliberately outside task011's
    # fixed crop/chunk/seed contract. They must not implicitly opt into it.
    config["adapter_options"]["center_crop"] = False
    config["execution"].update(max_chunk_steps=4, random_seed=11)
    stats = {name + "_no_noops": {"synthetic_suite": name} for name in transfer.TRAINING_SUITES}
    (Path(config["adapter_options"]["checkpoint"]) / "dataset_statistics.json").write_text(json.dumps(stats))
    original = subprocess.Popen
    def launch(command, **kwargs):
        assert command[-2:] == ["-m", "benchmark.remaining_goals.policy_worker"]
        return original([command[0], "-c", "from tests.test_remaining_oft_transfer import worker_main; raise SystemExit(worker_main())"], **kwargs)
    monkeypatch.setattr(isolated_policy.subprocess, "Popen", launch)
    policy = isolated_policy.SubprocessPolicy(config)
    try:
        metadata = policy.provenance["policy_metadata"]
        assert metadata["suite"] == metadata["evaluation_suite"] == metadata["normalization_suite"] == suite
        assert metadata["unnorm_key"] == suite + "_no_noops"
        assert metadata["suite_transfer"] is None and metadata["evaluation_track"] == "same_suite"
        assert metadata["inference_configuration"]["center_crop"] is False
        assert policy.provenance["random_seed"] == 11
        # The separate task011 validator remains narrow; the worker no longer
        # calls it for configurations that never requested task011 transfer.
        with pytest.raises(ValueError):
            transfer.validate_policy_metadata(config, metadata)
        policy.reset()
        raw = observation(); raw.pop("mask")
        output = policy.predict(raw, "Unchanged same-suite instruction")
        assert output.shape == (8, 7)
        np.testing.assert_array_equal(output[:, -1], [1., -1.] * 4)
    finally:
        policy.close()
    assert policy.process.poll() == 0


@pytest.mark.parametrize("field,value", [("suite", "libero_10"), ("evaluation_suite", "libero_10"),
    ("evaluation_track", "libero_10_primary"), ("unnorm_key", "libero_90"),
    ("normalization_statistics_sha256", None), ("checkpoint_training_suites", ["libero_90"]),
    ("component_checkpoint_sha256", {}), ("inference_source_sha256", {}), ("inference_configuration", {})])
def test_worker_refuses_mismatching_actual_transfer_metadata(monkeypatch, tmp_path, field, value):
    _, config = configs(tmp_path)
    monkeypatch.setattr(openvla_oft, "_load_upstream", fake_load)
    policy = openvla_oft.make_policy(config)
    try:
        policy.metadata[field] = value
        with pytest.raises(ValueError): policy_worker.provenance(config, policy)
    finally: policy.close()


def test_file_only_transfer_contract_and_static_checker_import_no_model(tmp_path):
    primary, extension = configs(tmp_path)
    assert evaluation.check_config(extension, "libero_90")["static_configuration_ready"]
    assert evaluation.check_config(extension, "libero_10")["errors"]
    code = '''import builtins, json, sys
real = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'torch','transformers','libero','robosuite','mujoco','mujoco_py'}:
        raise AssertionError(name)
    return real(name,*args,**kwargs)
builtins.__import__=guarded
from benchmark.remaining_goals.adapters.oft_transfer import validate_sog10_pair
print(json.dumps(validate_sog10_pair(*json.loads(sys.argv[1]))))
'''
    completed = subprocess.run([sys.executable, "-B", "-c", code, json.dumps([primary, extension])],
        cwd=Path(__file__).parents[1], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["action_chunk"] == 8
