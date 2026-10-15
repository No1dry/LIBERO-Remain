"""Actual provider + tiny HDF integration with a nonphysical native test double.

Only native scene creation/restoration/rendering are stubbed. The production
DemonstrationAuditProvider, BasketContract, PandaPoseHold, data audit and typed
observation codec execute. This is not a real LIBERO restoration or label result.
"""
from functools import wraps
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py", reason="tiny synthetic provider/audit integration requires h5py")

from benchmark.remaining_goals.finish import data
from benchmark.remaining_goals.finish import environment as env_module
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from tests.finish_domain_helpers import make_assets
from tests.test_finish_provider_lifecycle import install_native_provider, make_state


def setup_audit(monkeypatch, tmp_path, *, bad_xml=None):
    config = make_assets(tmp_path / "assets")
    states = {}
    with h5py.File(config["hdf5_path"], "a") as source:
        for index in range(50):
            name = f"demo_{index}"
            states[name] = np.stack([
                make_state(fingers=(.01, -.03), complete=False, marker=index + .1),
                make_state(fingers=(.03, -.01), complete=True, marker=index + .2),
            ])
            group = source[f"data/{name}"]
            del group["states"]
            group.create_dataset("states", data=states[name])
            group.attrs["model_file"] = ("<mujoco model='wrong-scene'/>" if name == bad_xml
                else f"<mujoco model='synthetic-{name}'/>")
    # The official-initial-state domain is deliberately different from every
    # demonstration; this regression must not resurrect demo-to-init matching.
    np.save(config["init_states_path"], np.stack([make_state(marker=-100-i) for i in range(50)]))
    config["expected_assets"]["hdf5_sha256"] = data._file_hash(config["hdf5_path"])
    config["expected_assets"]["init_states_sha256"] = data._file_hash(config["init_states_path"])
    native, config = install_native_provider(monkeypatch, tmp_path, config=config)
    providers, events = [], []
    save = data.save_observation_artifact
    hold = env_module.DemonstrationAuditProvider.capture_hold_label

    def save_current(base, relative, observation):
        digest = data.state_sha256(native.sim.value)
        reference = save(base, relative, observation)
        assert (Path(base) / reference["path"]).is_file()
        events.append(("saved_current", digest, reference))
        return reference

    @wraps(hold)
    def observed_hold(self, state, steps, model_xml=None):
        digest = data.state_sha256(state)
        assert events[-1][0:2] == ("saved_current", digest)
        events.append(("hold_begin", digest))
        try:
            return hold(self, state, steps, model_xml=model_xml)
        finally:
            events.append(("hold_end", data.state_sha256(native.sim.value)))

    def factory(value):
        provider = env_module.make_audit_provider(value)
        assert type(provider) is env_module.DemonstrationAuditProvider
        # Constructor reset is allowed to have the upstream one-dimensional
        # command placeholder; no restored-state hold contract may exist yet.
        assert native.gripper.current_action.shape == (1,)
        assert provider.contract is None and native.steps == 0
        providers.append(provider)
        return provider

    monkeypatch.setattr(data, "save_observation_artifact", save_current)
    monkeypatch.setattr(env_module.DemonstrationAuditProvider, "capture_hold_label", observed_hold)
    return native, config, states, factory, providers, events


def test_actual_provider_audits_negative_and_positive_hdf_frames_in_correct_order(monkeypatch, tmp_path):
    native, config, states, factory, providers, events = setup_audit(monkeypatch, tmp_path)
    before_hdf = Path(config["hdf5_path"]).read_bytes()
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, provider_factory=factory, out=out)
    assert report["status"] == "ready_for_feature_export", report["issues"]
    assert len(providers) == 1 and providers[0].env is None and providers[0].contract is None
    assert native.closes == 1 and native.steps == 35 * 4 and native.xml_resets == 35
    assert len(report["rows"]) == 70
    assert report["work_counts"] == {"restore_attempts": 70, "hold_attempts": 35,
        "current_observations": 70, "hold_branches": 35, "recorded_hold_steps": 140,
        "eligible_feature_forwards": 70}
    assert {row["trajectory_id"] for row in report["rows"]} == {f"demo_{i}" for i in range(5, 40)}
    assert Path(config["hdf5_path"]).read_bytes() == before_hdf
    assert sum(event[0] == "saved_current" for event in events) == 70
    assert sum(event[0] == "hold_begin" for event in events) == 35
    for row in report["rows"]:
        state = states[row["trajectory_id"]][row["saved_state_index"]]
        assert row["label"] == row["saved_state_index"]
        assert row["state_sha256"] == data.state_sha256(state)
        observation = load_observation_artifact(out, row["observation"])
        np.testing.assert_array_equal(observation["robot0_eef_pos"], state[1:4])
        if row["label"] == 0:
            assert row["hold_evidence"] is None
        else:
            hold = row["hold_evidence"]
            assert hold["hold_contract"]["version"] == env_module.HOLD_VERSION
            assert hold["hold_contract"]["gripper_command"] == 0
            np.testing.assert_allclose(hold["hold_contract"]["gripper_current_action"], [.5, .5], atol=1e-15)
            assert [frame["step"] for frame in hold["trace"]] == [0, 1, 2, 3, 4]
            assert all(frame["goals"] == [True, True] and frame["released"] is True for frame in hold["trace"])
    # Every independently restored branch returns to its own parent frame.
    assert [event[1] for event in events if event[0] == "hold_end"] == [
        event[1] for event in events if event[0] == "hold_begin"]
    data.validate_audit(report, base_dir=out)


def test_actual_provider_hold_failure_keeps_current_input_partial_and_closes(monkeypatch, tmp_path):
    native, config, states, factory, providers, events = setup_audit(monkeypatch, tmp_path)
    native.fail_step = 2
    before_hdf = Path(config["hdf5_path"]).read_bytes()
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, provider_factory=factory, out=out)
    assert report["status"] == "insufficient" and native.steps == 1 and native.closes == 1
    assert providers[0].env is None and providers[0].contract is None
    assert len(report["rows"]) == 2 and [row["label"] for row in report["rows"]] == [0, None]
    current = report["rows"][-1]
    expected = states[current["trajectory_id"]][1]
    assert current["hold_evidence"] is None and current["reason"] == "passive_hold_evidence_missing"
    np.testing.assert_array_equal(native.sim.value, expected)
    np.testing.assert_allclose(native.gripper.current_action, [.5, .5], atol=1e-15)
    saved = load_observation_artifact(out, current["observation"])
    np.testing.assert_array_equal(saved["robot0_eef_pos"], expected[1:4])
    assert events[-1] == ("hold_end", data.state_sha256(expected))
    assert data.read_json(out / "audit.json") == report
    assert Path(config["hdf5_path"]).read_bytes() == before_hdf
    assert report["work_counts"]["restore_attempts"] == 2 and report["work_counts"]["hold_attempts"] == 1


def test_actual_provider_later_raw_restore_error_preserves_completed_rows_and_closes(monkeypatch, tmp_path):
    native, config, _, factory, providers, _ = setup_audit(monkeypatch, tmp_path)
    # First two audit frames use restore calls 1 and 2; the positive frame's
    # independent hold/finally use 3 and 4. Fail the next sampled frame itself.
    native.fail_restore_at = 5
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, provider_factory=factory, out=out)
    assert report["status"] == "insufficient" and native.restore_calls == 5
    assert native.steps == 4 and native.closes == 1
    assert providers[0].env is None and providers[0].contract is None
    assert len(report["rows"]) == 2 and [row["label"] for row in report["rows"]] == [0, 1]
    assert report["work_counts"]["restore_attempts"] == 3 and report["work_counts"]["hold_attempts"] == 1
    assert any("synthetic raw restoration failure" in issue.get("message", "") for issue in report["issues"])
    for row in report["rows"]:
        load_observation_artifact(out, row["observation"])
    assert data.read_json(out / "audit.json") == report


def test_actual_provider_still_rejects_unsynchronized_restore_before_truth_or_label(monkeypatch, tmp_path):
    native, config, _, factory, providers, events = setup_audit(monkeypatch, tmp_path)
    restore = env_module.restore_raw_state
    def failed_sync(env, state):
        observation = restore(env, state)
        env.gripper.current_action = np.zeros(1)
        return observation
    monkeypatch.setattr(env_module, "restore_raw_state", failed_sync)
    report = data.audit_demonstrations(config, provider_factory=factory, out=tmp_path / "audit")
    assert report["status"] == "insufficient" and report["rows"] == [] and not events
    assert report["work_counts"]["restore_attempts"] == 1 and report["work_counts"]["hold_attempts"] == 0
    assert native.steps == 0 and native.closes == 1 and providers[0].env is None
    assert any("invalid Panda current_action" in issue.get("message", "") for issue in report["issues"])


def test_actual_provider_later_xml_layout_failure_keeps_prior_audit_rows(monkeypatch, tmp_path):
    # The file reader's deterministic lexical order begins demo_10 then demo_11
    # among the declared head groups; the latter must fail, not be skipped.
    native, config, _, factory, providers, _ = setup_audit(monkeypatch, tmp_path, bad_xml="demo_11")
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, provider_factory=factory, out=out)
    assert report["status"] == "insufficient" and native.steps == 4 and native.closes == 1
    assert providers[0].env is None and providers[0].contract is None
    assert len(report["rows"]) == 2 and {row["trajectory_id"] for row in report["rows"]} == {"demo_10"}
    assert [row["label"] for row in report["rows"]] == [0, 1]
    assert any("layout" in issue.get("message", "") for issue in report["issues"])
    for row in report["rows"]:
        load_observation_artifact(out, row["observation"])
    assert data.read_json(out / "audit.json") == report
