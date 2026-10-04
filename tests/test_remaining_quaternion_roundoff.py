"""Strict forward synchronization on MuJoCo-shaped fake physical states.

These exercise topology/layout and controller re-forwarding without loading a
renderer. Real simulator acceptance remains a separate build/replay gate.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.libero_env import fresh_observation, restore_raw_state


class QuaternionSim:
    def __init__(self):
        # Hinge, free, ball, hinge: qpos contains both quaternion layouts plus
        # scalar/translation positions. The flat state also has time and qvel.
        self.model = SimpleNamespace(nq=13, nv=11, na=0, njnt=4,
                                     jnt_type=np.array([3, 0, 1, 3]),
                                     jnt_qposadr=np.array([0, 1, 8, 12]))
        self.state = np.zeros(25, dtype=np.float64)
        self.data = SimpleNamespace(qpos=self.state[1:14], qacc_warmstart=np.ones(11))
        self.data.qpos[[4, 8]] = 1.
        self.forward_calls = 0
        self.extra_change = lambda: None
        self.derived = None

    def get_state(self):
        return SimpleNamespace(flatten=lambda: self.state.copy())

    def set_state_from_flattened(self, state):
        self.state[:] = state

    def forward(self):
        self.forward_calls += 1
        for start in (4, 8):
            quaternion = self.data.qpos[start:start + 4]
            quaternion /= np.linalg.norm(quaternion)
        self.extra_change()
        self.derived = self.data.qpos.copy()


def scene():
    sim = QuaternionSim()
    controller = SimpleNamespace()

    def update(force=False):
        assert force
        # Real robosuite BaseController.update(force=True) forwards again.
        sim.forward()
        controller.pose = sim.derived.copy()

    def reset_goal():
        controller.goal = controller.pose.copy()

    controller.update, controller.reset_goal = update, reset_goal
    task = SimpleNamespace(sim=sim, parsed_problem={"goal_state": []},
                           robots=[SimpleNamespace(controller=controller)],
                           _eval_predicate=lambda p: True, _check_success=lambda: True,
                           _post_process=lambda: None)

    def update_observables(force=False):
        assert force
        task.raw = {"agentview_image": np.arange(12, dtype=np.uint8).reshape(2, 2, 3),
                    "robot0_eef_pos": sim.derived[1:4].copy(),
                    "robot0_eef_quat": sim.derived[4:8].copy(),
                    "robot0_gripper_qpos": np.zeros(2)}

    task._update_observables = update_observables
    task._get_observations = lambda: task.raw
    return task


def bits(state):
    return np.asarray(state, dtype=np.float64).view(np.uint64)


@pytest.mark.parametrize("start", [4, 8])
def test_free_and_ball_normalization_roundoff_is_reverted_exactly(start):
    env = scene()
    quaternion = env.sim.data.qpos[start:start + 4]
    quaternion[:] = [np.nextafter(1., 2.), 0., -0., 0.]
    before = env.sim.state.copy()
    observation = fresh_observation(env)
    assert env.sim.forward_calls == 1
    assert np.array_equal(bits(before), bits(env.sim.state))
    assert np.signbit(env.sim.data.qpos[start + 2])
    # Physics was forwarded using a unit quaternion, while saved qpos keeps its
    # exact original representation. Camera convention is untouched.
    assert env.sim.derived[start] == 1.
    np.testing.assert_array_equal(observation["agentview_image"], np.arange(12).reshape(2, 2, 3))


def test_restore_handles_initial_controller_and_observation_forwards():
    env = scene()
    saved = env.sim.state.copy()
    saved[[5, 9]] = np.nextafter(1., 2.)
    first = restore_raw_state(env, saved)
    assert env.sim.forward_calls == 3
    assert np.array_equal(bits(saved), bits(env.sim.state))
    assert not env.sim.data.qacc_warmstart.any()
    assert env.robots[0].controller.goal[4] == 1.
    second = fresh_observation(env)
    assert np.array_equal(bits(saved), bits(env.sim.state))
    for key in first:
        np.testing.assert_array_equal(first[key], second[key])


@pytest.mark.parametrize("index", [0, 1, 2, 13, 14, 24])
def test_one_ulp_outside_quaternion_is_rejected(index):
    env = scene()
    env.sim.state[index] = 1.
    env.sim.extra_change = lambda: env.sim.state.__setitem__(index, np.nextafter(1., 2.))
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)


def test_signed_zero_outside_quaternion_is_also_a_bit_change():
    env = scene()
    env.sim.extra_change = lambda: env.sim.state.__setitem__(0, -0.)
    with pytest.raises(RuntimeError, match="indices=\\[0\\]"):
        fresh_observation(env)


@pytest.mark.parametrize("value", [1. + 64 * np.finfo(float).eps, 1.01])
def test_nonunit_saved_quaternion_is_not_silently_fixed(value):
    env = scene()
    env.sim.data.qpos[4] = value
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)


def test_large_orientation_change_rejected_even_when_both_quaternions_unit():
    env = scene()
    env.sim.extra_change = lambda: env.sim.data.qpos.__setitem__(slice(4, 8), [0., 1., 0., 0.])
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)


def test_observation_hook_cannot_use_forward_roundoff_exception():
    env = scene()
    env._post_process = lambda: env.sim.data.qpos.__setitem__(4, np.nextafter(1., 2.))
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)


def test_no_partial_repair_when_another_component_changed():
    env = scene()
    env.sim.data.qpos[4] = np.nextafter(1., 2.)
    env.sim.extra_change = lambda: env.sim.state.__setitem__(0, .01)
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)
    assert env.sim.data.qpos[4] == 1.  # The rejected operation was not partly repaired.


@pytest.mark.parametrize("field,value", [("na", 1), ("nq", 12), ("jnt_type", [3, 3, 1, 3])])
def test_unrecognized_layout_or_nonquaternion_joint_has_no_tolerance(field, value):
    env = scene()
    env.sim.data.qpos[4] = np.nextafter(1., 2.)
    setattr(env.sim.model, field, value)
    with pytest.raises(RuntimeError, match="changed simulator state"):
        fresh_observation(env)
