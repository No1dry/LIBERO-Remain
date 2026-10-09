"""Synthetic CPU preparation tests; no real LIBERO or policy success is asserted."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import regression_states as prepare
from benchmark.remaining_goals.observation_artifact import load_observation_artifact, save_observation_artifact


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    profile = prepare.TASKS["basket"]
    initial_root = tmp_path / "official_init_files"
    source = initial_root / "suite_folder" / "basket.pruned_init"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic trusted-source placeholder; no pickle is loaded")
    bddl = tmp_path / "basket.bddl"
    bddl.write_text("synthetic BDDL identity", encoding="utf-8")
    task = SimpleNamespace(name=profile["name"], language="official basket instruction",
                           problem_folder="suite_folder", init_states_file="basket.pruned_init")
    # Ensure the catalog name, not a guessed task index, determines the source.
    tasks = [SimpleNamespace(name="unrelated_task_0"), SimpleNamespace(name="unrelated_task_1"), task]
    suite = SimpleNamespace(n_tasks=len(tasks), get_task=lambda index: tasks[index])
    package = ModuleType("libero")
    package.libero = ModuleType("libero.libero")
    package.libero.benchmark = SimpleNamespace(get_benchmark_dict=lambda: {profile["suite"]: lambda: suite})
    package.libero.get_libero_path = lambda key: str(initial_root) if key == "init_states" else None
    monkeypatch.setitem(sys.modules, "libero", package)
    monkeypatch.setitem(sys.modules, "libero.libero", package.libero)
    states = [np.r_[0., np.arange(9, dtype=float) + index * 10, np.zeros(9)] for index in range(5)]
    record = SimpleNamespace(events=[], source=source, bddl=bddl, task=task, tasks=tasks, states=states,
                             seed=None, settle=0, audit_calls=[], closed=False, goals=[False, False],
                             audit_ok=True, audit_bad_state=False, audit_bad_observation=False,
                             restore_error=False, settle_error_at=None, close_error=False)

    class Env:
        def __init__(self):
            self.state = np.zeros_like(states[0])
            self.sim = SimpleNamespace(model=SimpleNamespace(), get_state=lambda: SimpleNamespace(flatten=lambda: self.state.copy()))
            self.env = SimpleNamespace(parsed_problem={"goal_state": deepcopy([goal["predicates"][0] for goal in profile["goals"]])})

        def seed(self, value):
            record.events.append("seed")
            record.seed = value

        def close(self):
            record.events.append("close")
            record.closed = True
            if record.close_error:
                raise RuntimeError("synthetic cleanup error")

    env = Env()
    record.env = env

    def source_states(active_suite, index):
        assert active_suite is suite and index == 2
        record.events.append("load_official_indexed_bank")
        return states

    def create_scene(suite_name, name, **options):
        assert (suite_name, name) == (profile["suite"], profile["name"])
        assert options == {"image_size": 256, "control_freq": 20}
        record.events.append("create_scene")
        return env, task, bddl

    def reset(active_env):
        assert active_env is env
        record.events.append("reset")
        active_env.state[:] = 0

    def restore(active_env, state):
        record.events.append("restore")
        if record.restore_error:
            raise RuntimeError("state restoration/controller/observation refresh changed simulator state")
        active_env.state = state.copy()
        record.restored_state = state.copy()

    def step(active_env, action):
        np.testing.assert_array_equal(action, prepare.builder.HOLD)
        if record.settle_error_at == record.settle:
            raise RuntimeError("synthetic settle failure")
        record.events.append("settle")
        active_env.state[0] += .05
        active_env.state[1] += .001
        record.settle += 1

    def audit(active_env, state, episode, output, relative, **options):
        record.events.append("audit")
        record.audit_calls.append({"state": state.copy(), "episode": deepcopy(episode), "options": options})
        active_env.state = state.copy() + 500  # Must NEVER become the saved policy start.
        observation = {"agentview_image": np.full((4, 4, 3), 17, dtype=np.uint8),
                       "robot0_eye_in_hand_image": np.full((4, 4, 3), 29, dtype=np.uint8),
                       "robot0_eef_pos": state[1:4].copy()}
        reference = save_observation_artifact(output, (relative / "initial_observation.npz").as_posix(), observation)
        episode["initial_observation"] = reference
        initial_state = state.copy()
        if record.audit_bad_state:
            initial_state[1] += .0001
        count = 150 if record.audit_ok else 2
        rows = [{"step": index, "state": initial_state.tolist(), "goals": [False, False],
                 "observation_check": {"returned_sha256": reference["observation_sha256"]}}
                for index in range(count + 1)]
        if record.audit_bad_observation:
            rows[0]["observation_check"]["returned_sha256"] = "0" * 64
        payload = {"technical_acceptance": record.audit_ok, "requested_steps": 150, "completed_steps": count,
                   "error": None if record.audit_ok else {"phase": "step", "message": "synthetic audit failure"}, "trace": rows}
        prepare.builder._write(output / relative / "audit.json", payload)
        return {"technical_acceptance": record.audit_ok, "static_acceptance": True,
                "checks": {"validation_window_complete": record.audit_ok},
                "error": payload["error"], "audit_path": (relative / "audit.json").as_posix()}

    def forbidden(*args, **kwargs):
        raise AssertionError("00 capability preparation must not construct partial masks")

    monkeypatch.setattr(prepare.builder, "_official_initial_states", source_states)
    monkeypatch.setattr(prepare, "environment_identity", lambda freq: {"name": "libero", "fingerprint": "f" * 64,
                                                                        "lock": {"synthetic": True, "control_freq": freq}})
    monkeypatch.setattr(prepare, "create_scene", create_scene)
    monkeypatch.setattr(prepare, "reset_scene", reset)
    monkeypatch.setattr(prepare, "model_xml_hash", lambda active_env: record.events.append("reset_xml") or "e" * 64)
    monkeypatch.setattr(prepare, "restore_raw_state", restore)
    monkeypatch.setattr(prepare.builder, "_step", step)
    monkeypatch.setattr(prepare.builder, "_goals", lambda *args: list(record.goals))
    monkeypatch.setattr(prepare.builder, "_audit_state", audit)
    monkeypatch.setattr(prepare.ms.StateLayout, "from_model", lambda model: "synthetic layout")
    monkeypatch.setattr(prepare.ms, "get_robot_qpos", lambda state, layout, n: state[1:1+n].copy())
    for name in ("_per_goal", "_matched_states", "combine_goal_candidates"):
        monkeypatch.setattr(prepare.builder, name, forbidden)
    return record


@pytest.mark.parametrize("index", range(5))
def test_exact_official_index_and_fixed_preparation_sequence(tmp_path, runtime, index):
    output = tmp_path / f"prepared_{index}"
    report = prepare.prepare_normal00("basket", index, output)
    assert report["status"] == "prepared", report
    assert runtime.events[:6] == ["load_official_indexed_bank", "create_scene", "seed", "reset", "reset_xml", "restore"]
    assert runtime.events[6:86] == ["settle"] * 80
    assert runtime.events[86:] == ["audit", "close"]
    assert runtime.seed == index and runtime.settle == 80 and runtime.closed
    np.testing.assert_array_equal(runtime.restored_state, runtime.states[index])
    episode = report["episode"]
    assert episode["initial_state_index"] == episode["seed"] == index
    assert episode["libero_task_id"] == 2
    assert episode["initial_mask"] == [False, False]
    assert episode["horizon"] == 520 and episode["retention_steps"] == 150
    assert runtime.audit_calls[0]["options"] == {"validation_steps": 150, "velocity_tolerance": .01, "robot_tolerance": .002}
    assert report["preparation"]["policy_steps"] == 0
    assert report["preparation"]["attempted"] == 1 and report["preparation"]["replacement_indices"] == []
    assert report["environment_config"]["manifest_dir"] == str(output.resolve())
    assert report["environment_config"]["environment"] == report["provenance"]["environment"]


def test_saved_start_is_pre_audit_base_with_exact_typed_step0_observation(tmp_path, runtime):
    report = prepare.prepare_normal00("basket", 4, tmp_path / "prepared")
    episode = report["episode"]
    saved = np.load(tmp_path / "prepared" / episode["state_path"], allow_pickle=False)
    np.testing.assert_array_equal(saved, runtime.audit_calls[0]["state"])
    assert not np.array_equal(saved, runtime.env.state)
    np.testing.assert_array_equal(episode["reference_robot_qpos"], saved[1:10])
    observation = load_observation_artifact(tmp_path / "prepared", episode["initial_observation"])
    assert observation["agentview_image"].dtype == np.uint8
    assert np.all(observation["agentview_image"] == 17)
    np.testing.assert_array_equal(observation["robot0_eef_pos"], saved[1:4])
    provenance = report["provenance"]
    assert provenance["official_initial_state_file"]["sha256"] == hashlib.sha256(runtime.source.read_bytes()).hexdigest()
    assert provenance["selected_official_state"]["sha256"] == hashlib.sha256(runtime.states[4].tobytes()).hexdigest()
    assert provenance["saved_state_sha256"] == episode["state_sha256"]
    assert len(provenance["frozen_source_sha256"]) == 7
    assert report["schema_version"] != "remaining-goals-v0.1"
    assert report["purpose"] == "normal00-capability-regression"
    assert report["complete_paired_benchmark"] is False and episode["construction"]["legal"] is False
    assert not list((tmp_path / "prepared").glob("manifest*"))
    assert json.loads((tmp_path / "prepared/preparation.json").read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("defect,phase", [("restore", "reset_and_restore"), ("settle", "settle"),
                                         ("not_zero", "initial_goal_check"), ("audit", "technical_audit"),
                                         ("audit_state", "audit_initial_state_binding"),
                                         ("observation", "audit_initial_state_binding"), ("close", "close_environment")])
def test_preparation_failures_keep_requested_index_and_do_not_fallback(tmp_path, runtime, defect, phase):
    if defect == "restore":
        runtime.restore_error = True
    elif defect == "settle":
        runtime.settle_error_at = 11
    elif defect == "not_zero":
        runtime.goals = [True, False]
    elif defect == "audit":
        runtime.audit_ok = False
    elif defect == "audit_state":
        runtime.audit_bad_state = True
    elif defect == "observation":
        runtime.audit_bad_observation = True
    else:
        runtime.close_error = True
    output = tmp_path / "failed"
    report = prepare.prepare_normal00("basket", 3, output)
    assert report["status"] == "preparation_error" and report["episode"] is None
    assert report["environment_config"] is None and report["error"]["phase"] == phase
    assert report["provenance"]["initial_state_index"] == report["preparation"]["requested_index"] == 3
    assert report["preparation"]["attempted"] == 1 and report["preparation"]["replacement_indices"] == []
    assert runtime.closed and runtime.events.count("load_official_indexed_bank") == 1
    assert (output / "preparation.json").is_file()
    if defect != "close":
        assert not list(output.rglob("*.npy"))
    if defect == "settle":
        assert report["preparation"]["settle_steps_completed"] == 11
    if defect == "audit":
        assert report["preparation"]["audit_steps_completed"] == 2


def test_index_out_of_range_is_a_persisted_preparation_failure(tmp_path, runtime):
    report = prepare.prepare_normal00("basket", 5, tmp_path / "out_of_range")
    assert report["status"] == "preparation_error"
    assert report["error"]["phase"] == "official_initial_state"
    assert report["preparation"]["requested_index"] == 5
    assert runtime.events == ["load_official_indexed_bank"]
    assert report["provenance"]["official_initial_state_file"]["count"] == 5


def test_fingerprint_mismatch_stops_before_environment_or_state_loading(tmp_path, runtime):
    report = prepare.prepare_normal00("basket", 2, tmp_path / "wrong_runtime",
                                      environment_config={"environment": {"name": "libero", "fingerprint": "different"}})
    assert report["status"] == "preparation_error" and report["error"]["phase"] == "environment_identity"
    assert runtime.events == [] and report["preparation"]["settle_steps_completed"] == 0


@pytest.mark.parametrize("index", [True, False, -1, 1.0, "1"])
def test_invalid_indices_are_rejected_before_any_output(tmp_path, runtime, index):
    output = tmp_path / "bad"
    with pytest.raises(ValueError):
        prepare.prepare_normal00("basket", index, output)
    assert not output.exists() and not runtime.events


@pytest.mark.parametrize("task", ["all", "primary", "does_not_exist", "two_pots", "basket,stove"])
def test_single_supported_catalog_key_is_required(tmp_path, runtime, task):
    with pytest.raises(ValueError):
        prepare.prepare_normal00(task, 0, tmp_path / "bad")
    assert not runtime.events


@pytest.mark.parametrize("options", [{"seed": 7}, {"horizon": 10}, {"settle_steps": 10}, {"retention_steps": 0},
                                     {"image_size": 224}, {"control_freq": 10}, {"control_freq": True},
                                     {"hold_action": [0] * 7}, {"manifest_dir": "."}])
def test_callers_cannot_silently_change_preparation_contract(tmp_path, runtime, options):
    with pytest.raises(ValueError):
        prepare.prepare_normal00("basket", 0, tmp_path / "bad", environment_config=options)
    assert not runtime.events


def test_existing_output_is_never_overwritten(tmp_path, runtime):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "original.txt"
    sentinel.write_bytes(b"unchanged")
    with pytest.raises(FileExistsError):
        prepare.prepare_normal00("basket", 0, output)
    assert sentinel.read_bytes() == b"unchanged" and not runtime.events


def test_native_task_mapping_and_official_predicates_must_match(tmp_path, runtime):
    runtime.env.env.parsed_problem["goal_state"].pop()
    report = prepare.prepare_normal00("basket", 0, tmp_path / "wrong_goals")
    assert report["status"] == "preparation_error" and report["error"]["phase"] == "create_scene"
    assert runtime.closed and "restore" not in runtime.events


def test_changed_source_file_is_rejected_instead_of_trusting_loaded_states(tmp_path, runtime, monkeypatch):
    def changed(*args):
        runtime.source.write_bytes(b"modified during loading")
        return runtime.states
    monkeypatch.setattr(prepare.builder, "_official_initial_states", changed)
    report = prepare.prepare_normal00("basket", 1, tmp_path / "changed")
    assert report["status"] == "preparation_error"
    assert "changed while" in report["error"]["message"] and not runtime.events


def test_corrupt_requested_state_does_not_select_another_valid_index(tmp_path, runtime):
    runtime.states[2][1] = np.nan
    report = prepare.prepare_normal00("basket", 2, tmp_path / "corrupt")
    assert report["status"] == "preparation_error" and report["preparation"]["requested_index"] == 2
    assert runtime.events == ["load_official_indexed_bank"]
