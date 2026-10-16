"""Actual audit-provider lifecycle on a native reset/synchronization CPU fake.

No MuJoCo, LIBERO initialization or real model is executed. Unlike an alternate
FakeProvider, this exercises DemonstrationAuditProvider and BasketContract.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.finish import environment as module
from tests.test_finish_environment import Native, raw_observation


def make_state(fingers=(.02, -.02), complete=False, marker=0):
    state = np.zeros(15, dtype=np.float64)
    state[1] = marker
    state[6:8] = fingers
    state[8] = float(complete)
    return state


def expected_action(state):
    """Known two-finger position-servo inverse, without clipping bad qpos."""
    qpos = np.asarray(state)[6:8]
    return 2 * (qpos - np.array([0., -.04])) / .04 - 1


class NativeLifecycle(Native):
    def __init__(self):
        super().__init__()
        self.events = []
        self.restore_calls = 0
        self.fail_restore_at = None
        self.restore_override = None
        self.fail_native_reset = False
        self.fail_xml = False
        self.gripper.current_action = np.zeros(1)

    def native_reset(self):
        self.resets += 1
        self.gripper.current_action = np.zeros(1)
        self.events.append({"op": "native_reset", "action_shape": (1,)})
        if self.fail_native_reset:
            raise RuntimeError("synthetic native reset failure")

    def reset_from_xml_string(self, xml):
        self.gripper.current_action = np.zeros(1)
        self.events.append({"op": "xml_reset", "xml": xml, "action_shape": (1,)})
        if self.fail_xml:
            raise RuntimeError("synthetic XML reset failure")
        super().reset_from_xml_string(xml)

    def step(self, action):
        self.events.append({"op": "step", "action": np.asarray(action).copy()})
        super().step(action)

    def close(self):
        self.events.append({"op": "close"})
        super().close()


def install_native_provider(monkeypatch, tmp_path, *, config=None, native=None, target=module):
    """Patch only native I/O; retain the actual provider, contract and hold code.

    Events are dictionaries with an ``op`` key. This is shared with the separate
    tiny-HDF audit integration tests and can also target an isolated old module.
    """
    native = NativeLifecycle() if native is None else native
    if config is None:
        Path(tmp_path).mkdir(parents=True, exist_ok=True)
        bddl = Path(tmp_path) / "official.bddl"
        bddl.write_text("synthetic basket BDDL; no physical scene", encoding="utf-8")
        config = {"bddl_path": str(bddl), "original_instruction": "synthetic original instruction"}
    else:
        config = deepcopy(config)
        bddl = Path(config["bddl_path"])
    task = SimpleNamespace(name=target.TASKS["basket"]["name"], language=config["original_instruction"])
    monkeypatch.setattr(target, "create_scene", lambda *args, **kwargs: (native, task, bddl))
    monkeypatch.setattr(target, "environment_identity", lambda *args: {"name": "synthetic", "fingerprint": "test-only"})
    monkeypatch.setattr(target, "reset_scene", lambda env: env.native_reset())
    # Tiny XML has no resource dependencies. Keep the actual CPU resolver so
    # the audit's frozen scan reaches the provider without a test-only bypass.

    def observe(env):
        result = raw_observation(env)
        result["robot0_gripper_qpos"] = env.sim.value[6:8].copy()
        env.events.append({"op": "fresh", "state": env.sim.value.copy()})
        return result

    def restore(env, state):
        env.restore_calls += 1
        state = np.asarray(state, dtype=np.float64)
        env.events.append({"op": "restore", "call": env.restore_calls, "state": state.copy(),
                           "xml": env.sim.model.xml})
        if env.restore_calls == env.fail_restore_at:
            raise RuntimeError("synthetic raw restoration failure")
        if state.shape != (15,):
            raise ValueError("synthetic state layout mismatch")
        env.sim.value = state.copy()
        # This is the only fake operation that synchronizes current_action.
        env.gripper.current_action = expected_action(state)
        if env.restore_override is not None:
            env.gripper.current_action = np.asarray(env.restore_override, dtype=np.float64).copy()
        env.membership.update({name: bool(state[8]) for name in target.TARGETS})
        env.controller.update(force=True)
        return observe(env)

    actual_contract = target.BasketContract
    def contract(env):
        env.events.append({"op": "contract", "state": env.sim.value.copy(), "xml": env.sim.model.xml,
                           "action": env.gripper.current_action.copy()})
        result = actual_contract(env)
        result.test_bound_state = env.sim.value.copy()
        return result

    monkeypatch.setattr(target, "restore_raw_state", restore)
    monkeypatch.setattr(target, "fresh_observation", observe)
    monkeypatch.setattr(target, "BasketContract", contract)
    return native, config


@pytest.fixture
def native_setup(monkeypatch, tmp_path):
    return install_native_provider(monkeypatch, tmp_path)


def assert_rebound(provider, native, state):
    assert provider.contract is not None
    np.testing.assert_array_equal(provider.contract.test_bound_state, state)
    np.testing.assert_array_equal(provider.contract.gripper.current_action, expected_action(state))
    assert provider.contract.hold.reference_pos is None


def test_constructor_retains_native_shape_one_until_first_real_restore(native_setup):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    try:
        assert provider.contract is None and native.gripper.current_action.shape == (1,)
        assert native.steps == native.restore_calls == native.xml_resets == 0
        assert [event["op"] for event in native.events] == ["native_reset"]
        with pytest.raises(RuntimeError):
            provider._truth()
        state = make_state((.01, -.03))
        provider.restore_demonstration(state, model_xml="<mujoco model='first'/>")
        assert [event["op"] for event in native.events] == ["native_reset", "xml_reset", "restore", "fresh", "contract"]
        assert_rebound(provider, native, state)
        assert native.steps == 0
    finally:
        provider.close()
    assert native.closes == 1


def test_xml_switch_and_continuous_frames_bind_new_gripper_targets(native_setup):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    try:
        states = [make_state((.01, -.03)), make_state((.03, -.01)), make_state((.04, -.04))]
        contracts = []
        for state, xml in zip(states, ("<mujoco model='a'/>", "<mujoco model='a'/>", "<mujoco model='b'/>")):
            provider.restore_demonstration(state, model_xml=xml)
            contracts.append(provider.contract)
            assert_rebound(provider, native, state)
        assert len({id(value) for value in contracts}) == 3
        assert native.xml_resets == 2 and native.restore_calls == 3 and native.steps == 0
        operations = [event["op"] for event in native.events]
        assert operations == ["native_reset", "xml_reset", "restore", "fresh", "contract",
                              "restore", "fresh", "contract", "xml_reset", "restore", "fresh", "contract"]
    finally:
        provider.close()


@pytest.mark.parametrize("fail_step", [None, 2])
def test_independent_hold_restores_parent_xml_state_and_rebinds_contract(native_setup, fail_step):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    parent, branch = make_state((.01, -.03), marker=1), make_state((.03, -.01), complete=True, marker=2)
    parent_xml, branch_xml = "<mujoco model='parent'/>", "<mujoco model='branch'/>"
    try:
        saved_observation = provider.restore_demonstration(parent, model_xml=parent_xml)["observation"]
        before_observation = deepcopy(saved_observation)
        before_contract = provider.contract
        native.fail_step = fail_step
        if fail_step is None:
            report = provider.capture_hold_label(branch, 4, model_xml=branch_xml)
            assert len(report["trace"]) == 5
            np.testing.assert_allclose(report["hold_contract"]["gripper_current_action"], expected_action(branch), atol=0, rtol=0)
        else:
            with pytest.raises(RuntimeError, match="synthetic physical step failure"):
                provider.capture_hold_label(branch, 4, model_xml=branch_xml)
        assert provider.contract is not before_contract and native.sim.model.xml == parent_xml
        assert_rebound(provider, native, parent)
        np.testing.assert_array_equal(native.sim.value, parent)
        for key in saved_observation:
            np.testing.assert_array_equal(saved_observation[key], before_observation[key])
        assert native.steps == (4 if fail_step is None else 1)
        assert all(event["action"][-1] == 0 for event in native.events if event["op"] == "step")
        assert [event["op"] for event in native.events[-4:]] == ["xml_reset", "restore", "fresh", "contract"]
    finally:
        provider.close()


@pytest.mark.parametrize("bad_action", [np.zeros(1), np.zeros(3), np.array([np.nan, 0.]), np.array([1.001, 0.])])
def test_unsynchronized_or_illegal_restored_target_still_fails_strict_contract(native_setup, bad_action):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    native.restore_override = bad_action
    try:
        with pytest.raises((ValueError, RuntimeError), match="Panda current_action"):
            provider.restore_demonstration(make_state(), model_xml="<mujoco/>")
        assert provider.contract is None and native.steps == 0
        assert native.restore_calls == 1
        with pytest.raises(RuntimeError):
            provider._truth()
    finally:
        provider.close()
    assert native.closes == 1


@pytest.mark.parametrize("failure", ["restore", "xml_layout", "xml_reset"])
def test_failed_transition_invalidates_old_contract_until_owner_closes(native_setup, failure):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    provider.restore_demonstration(make_state(), model_xml="<mujoco model='parent'/>")
    if failure == "restore":
        native.fail_restore_at = 2
        xml = "<mujoco model='parent'/>"
    elif failure == "xml_layout":
        xml = "<mujoco model='wrong-scene'/>"
    else:
        native.fail_xml = True
        xml = "<mujoco model='new'/>"
    try:
        with pytest.raises((ValueError, RuntimeError)):
            provider.restore_demonstration(make_state((.01, -.03)), model_xml=xml)
        assert provider.contract is None and native.steps == 0
        with pytest.raises(RuntimeError):
            provider._truth()
    finally:
        # audit_demonstrations owns closure after restoration failures; the
        # end-to-end companion test exercises that owner explicitly.
        provider.close()
    assert native.closes == 1


@pytest.mark.parametrize("failure", ["restore", "exact_state"])
def test_failed_finally_parent_restore_cannot_leave_branch_contract_live(native_setup, monkeypatch, failure):
    native, config = native_setup
    provider = module.DemonstrationAuditProvider(config)
    parent = make_state((.01, -.03), marker=1)
    branch = make_state((.03, -.01), complete=True, marker=2)
    xml = "<mujoco model='shared'/>"
    provider.restore_demonstration(parent, model_xml=xml)
    if failure == "restore":
        native.fail_restore_at = 3  # parent setup, branch setup, finally parent
    else:
        actual_restore = module.restore_raw_state
        def changed_state(env, state):
            observation = actual_restore(env, state)
            if env.restore_calls == 3:
                env.sim.value[1] += 1.0
            return observation
        monkeypatch.setattr(module, "restore_raw_state", changed_state)
    try:
        with pytest.raises(RuntimeError):
            provider.capture_hold_label(branch, 4, model_xml=xml)
        assert native.restore_calls == 3 and native.steps == 4
        assert provider.contract is None
        # Parent contract is not constructed before exact-state verification.
        assert len([event for event in native.events if event["op"] == "contract"]) == 2
        with pytest.raises(RuntimeError):
            provider._truth()
    finally:
        provider.close()
    assert native.closes == 1 and provider.env is None


@pytest.mark.parametrize("failure", ["instruction", "bddl", "native_reset"])
def test_constructor_failure_closes_created_native_without_any_step(native_setup, tmp_path, failure):
    native, config = native_setup
    if failure == "instruction":
        config["original_instruction"] = "wrong task"
    elif failure == "bddl":
        wrong = tmp_path / "different.bddl"
        wrong.write_text("different bytes", encoding="utf-8")
        config["bddl_path"] = str(wrong)
    else:
        native.fail_native_reset = True
    with pytest.raises((ValueError, RuntimeError)):
        module.DemonstrationAuditProvider(config)
    assert native.closes == 1 and native.steps == native.restore_calls == 0
