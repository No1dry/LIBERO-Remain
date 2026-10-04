"""Panda command restoration with compiled-model-shaped fakes, no simulator."""

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.libero_env import LiberoGoalEnv, restore_raw_state


class PandaGripper:
    dof = 1
    speed = .01
    joints = ["left", "right"]
    actuators = ["left_position", "right_position"]

    def __init__(self):
        self.current_action = np.zeros(1)  # Official initial Python hidden state.
        self.format_calls = 0

    def format_action(self, action):
        self.format_calls += 1
        self.current_action = np.clip(
            self.current_action + np.array([-1., 1.]) * self.speed * np.sign(action), -1., 1.)
        return self.current_action


@pytest.fixture
def env(monkeypatch):
    module = ModuleType("robosuite.models.grippers.panda_gripper")
    module.PandaGripper = PandaGripper
    monkeypatch.setitem(sys.modules, module.__name__, module)
    state = np.zeros(7)  # time, three qpos, three qvel
    gain, bias = np.zeros((3, 10)), np.zeros((3, 10))
    gain[:, 0], bias[:, 1] = 1000., -1000.
    # Actuator order deliberately differs from joint / gripper order.
    model = SimpleNamespace(
        nq=3, nv=3, na=0, njnt=3,
        joint_name2id={"arm": 0, "left": 1, "right": 2}.__getitem__,
        actuator_name2id={"right_position": 0, "arm": 1, "left_position": 2}.__getitem__,
        jnt_type=np.array([3, 2, 2]), jnt_limited=np.ones(3), jnt_qposadr=np.arange(3),
        jnt_range=np.array([[-2., 2.], [0., .04], [-.04, 0.]]),
        actuator_ctrlrange=np.array([[-.04, 0.], [-2., 2.], [0., .04]]),
        actuator_trntype=np.zeros(3), actuator_trnid=np.array([[2, -1], [0, -1], [1, -1]]),
        actuator_gear=np.tile([1., 0., 0., 0., 0., 0.], (3, 1)),
        actuator_dyntype=np.zeros(3), actuator_gaintype=np.zeros(3),
        actuator_biastype=np.ones(3), actuator_ctrllimited=np.ones(3),
        actuator_gainprm=gain, actuator_biasprm=bias)
    data = SimpleNamespace(qpos=state[1:4], qacc_warmstart=np.ones(3), ctrl=np.array([.3, .314, .3]))
    sim = SimpleNamespace(model=model, data=data, forward=lambda: None,
                          get_state=lambda: SimpleNamespace(flatten=lambda: state.copy()),
                          set_state_from_flattened=lambda saved: state.__setitem__(slice(None), saved))
    gripper = PandaGripper()
    controller = SimpleNamespace(update=lambda force: None, reset_goal=lambda: None)
    robot = SimpleNamespace(controller=controller, gripper=gripper, has_gripper=True)
    scene = SimpleNamespace(sim=sim, robots=[robot], state=state, step_calls=0,
                            parsed_problem={"goal_state": []}, _eval_predicate=lambda p: False,
                            _check_success=lambda: False, _post_process=lambda: None,
                            _update_observables=lambda force: None)
    scene._get_observations = lambda: {
        "agentview_image": np.zeros((2, 2, 3), dtype=np.uint8),
        "robot0_eef_pos": np.zeros(3), "robot0_eef_quat": np.array([0., 0., 0., 1.]),
        "robot0_gripper_qpos": data.qpos[1:].copy()}

    def step(action):
        scene.step_calls += 1
        formatted = gripper.format_action(np.asarray(action[-1:]))
        ranges = model.actuator_ctrlrange[[2, 0]]
        data.ctrl[[2, 0]] = ranges.mean(axis=1) + .5 * np.diff(ranges, axis=1)[:, 0] * formatted
        state[0] += .05

    scene.step = step
    return scene


@pytest.mark.parametrize("positions,expected", [([0., 0.], [-1., 1.]),
                                                ([.02, -.02], [0., 0.]),
                                                ([.04, -.04], [1., -1.]),
                                                ([.01, -.025], [-.5, -.25])])
def test_closed_partial_open_and_asymmetric_positions_restore_commands(env, positions, expected):
    saved = env.state.copy()
    saved[2:4] = positions
    obs = restore_raw_state(env, saved)
    gripper = env.robots[0].gripper
    np.testing.assert_allclose(gripper.current_action, expected, atol=1e-15)
    np.testing.assert_allclose(env.sim.data.ctrl[[2, 0]], positions, atol=1e-17)
    assert env.sim.data.ctrl[1] == .314  # Other actuator commands untouched.
    assert gripper.format_calls == env.step_calls == 0
    assert np.array_equal(env.state.view(np.uint64), saved.view(np.uint64))
    np.testing.assert_array_equal(obs["robot0_gripper_qpos"], positions)


@pytest.mark.parametrize("positions", [[0., 0.], [.02, -.02], [.04, -.04]])
def test_first_policy_step_advances_gripper_once_from_restored_command(env, positions):
    saved = env.state.copy()
    saved[2:4] = positions
    restore_raw_state(env, saved)
    gripper = env.robots[0].gripper
    expected = np.clip(gripper.current_action + [.01, -.01], -1., 1.)
    wrapped = LiberoGoalEnv.__new__(LiberoGoalEnv)
    wrapped.env, wrapped._ready = env, True
    wrapped.step([0., 0., 0., 0., 0., 0., -1.])
    np.testing.assert_array_equal(gripper.current_action, expected)
    assert gripper.format_calls == env.step_calls == 1


def test_repeat_restore_discards_previous_episode_incremental_command(env):
    saved = env.state.copy()
    saved[2:4] = [.04, -.04]
    restore_raw_state(env, saved)
    saved[2:4] = [.01, -.01]
    restore_raw_state(env, saved)
    np.testing.assert_allclose(env.robots[0].gripper.current_action, [-.5, .5])
    assert env.robots[0].gripper.format_calls == 0


def test_soft_limit_overshoot_clips_only_command_not_physical_state(env):
    saved = env.state.copy()
    saved[2:4] = [.04001, -.04001]
    restore_raw_state(env, saved)
    np.testing.assert_array_equal(env.robots[0].gripper.current_action, [1., -1.])
    np.testing.assert_array_equal(env.sim.data.ctrl[[2, 0]], [.04, -.04])
    np.testing.assert_array_equal(env.state, saved)


@pytest.mark.parametrize("field,index,value", [
    ("actuator_trntype", 2, 1), ("actuator_trnid", (2, 0), 2),
    ("actuator_gear", (2, 0), 2.), ("actuator_gear", (2, 1), 1.),
    ("actuator_dyntype", 2, 1), ("actuator_gaintype", 2, 1),
    ("actuator_biastype", 2, 0), ("actuator_gainprm", (2, 0), -1000.),
    ("actuator_gainprm", (2, 1), 1.), ("actuator_biasprm", (2, 2), -1.),
    ("actuator_ctrllimited", 2, 0), ("actuator_ctrlrange", (2, 1), .03),
    ("jnt_type", 1, 3), ("jnt_limited", 1, 0),
])
def test_unsupported_position_servo_contract_is_rejected_before_command_write(env, field, index, value):
    getattr(env.sim.model, field)[index] = value
    before_ctrl = env.sim.data.ctrl.copy()
    with pytest.raises(RuntimeError, match="unsupported restored gripper contract"):
        restore_raw_state(env, env.state.copy())
    np.testing.assert_array_equal(env.sim.data.ctrl, before_ctrl)
    assert env.robots[0].gripper.format_calls == 0


def test_unknown_gripper_type_is_not_guessed(env):
    env.robots[0].gripper = SimpleNamespace()
    with pytest.raises(RuntimeError, match="expected official PandaGripper"):
        restore_raw_state(env, env.state.copy())
