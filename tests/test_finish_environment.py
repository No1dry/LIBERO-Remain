"""Fake model/control tests only; no MuJoCo imports, creation or restoration."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.finish import environment as module
from benchmark.remaining_goals.finish.data import state_sha256


class Panda:
    pass


class PandaGripper:
    dof = 1
    speed = .01
    contact_geoms = ["left", "right", "palm"]
    important_geoms = {"left_fingerpad": ["left"], "right_fingerpad": ["right"]}
    def __init__(self):
        self.current_action = np.array([1., -1.])
    def format_action(self, action):
        self.current_action = np.clip(self.current_action + np.array([-1., 1.]) * self.speed * np.sign(action), -1, 1)
        return self.current_action


class Model:
    nq = nv = 7
    nu, nbody, ngeom, nsite, njnt, na = 2, 6, 8, 1, 1, 0
    names = ["left", "right", "palm", "soup", "sauce", "extra", "basket", "table"]
    jnt_type = np.array([3])
    jnt_qposadr = jnt_dofadr = np.array([0])
    body_parentid = np.zeros(6, dtype=int)
    geom_bodyid = np.arange(8) % 6
    site_bodyid = np.zeros(1, dtype=int)
    actuator_trnid = np.array([[0, -1], [0, -1]])
    actuator_trntype = np.zeros(2, dtype=int)
    def __init__(self):
        self.geom_rbound = np.array([.008, .008, .02, .012, .014, .012, .05, .5])
        self.xml = "<mujoco/>"
    def get_xml(self):
        return self.xml
    def geom_name2id(self, name):
        return self.names.index(name)
    def geom_id2name(self, index):
        return self.names[index]
    def joint_id2name(self, index):
        return "joint_" + str(index)
    def body_id2name(self, index):
        return "body_" + str(index)
    def site_id2name(self, index):
        return module.REGION
    def actuator_id2name(self, index):
        return "actuator_" + str(index)


class Sim:
    def __init__(self):
        self.value = np.zeros(15)
        self.model = Model()
        self.data = SimpleNamespace(geom_xpos=np.array([[-.04, 0, 0], [.04, 0, 0], [0, 0, -.08],
            [1., 0, 0], [2., 0, 0], [3., 0, 0], [4., 0, 0], [0, 0, -1.]]))
    def get_state(self):
        return SimpleNamespace(flatten=lambda: self.value.copy())


class Controller:
    name, impedance_mode, control_dim, use_delta, use_ori = "OSC_POSE", "fixed", 6, True, True
    position_limits = orientation_limits = interpolator_pos = interpolator_ori = None
    input_min, input_max = -np.ones(6), np.ones(6)
    output_min, output_max = -np.array([.05, .05, .05, .5, .5, .5]), np.array([.05, .05, .05, .5, .5, .5])
    def __init__(self, sim):
        self.sim = sim
        self.ee_pos, self.ee_ori_mat = np.zeros(3), np.eye(3)
        self.orientation = np.eye(3)
        self.goal_pos, self.goal_ori = np.ones(3), -np.eye(3)
        self.updates = self.sets = 0
    def update(self, force=False):
        assert force is True
        self.updates += 1
        self.ee_pos = self.sim.value[1:4].copy()
        self.ee_ori_mat = self.orientation.copy()
    def set_goal(self, action, set_pos=None, set_ori=None):
        self.sets += 1
        self.goal_pos, self.goal_ori = set_pos.copy(), set_ori.copy()


def obj(geom, joints=True):
    return SimpleNamespace(contact_geoms=[geom], joints=["free"] if joints else [])


class Native:
    def __init__(self):
        self.sim = Sim()
        self.controller, self.gripper = Controller(self.sim), PandaGripper()
        self.robots = [SimpleNamespace(robot_model=Panda(), controller=self.controller, gripper=self.gripper)]
        self.membership = {module.TARGETS[0]: False, module.TARGETS[1]: False, "extra_1": False}
        self.grasps, self.contacts = set(), set()
        self.predicates = []
        self.env = SimpleNamespace(parsed_problem={"goal_state": [["In", name, module.REGION] for name in module.TARGETS]},
            objects_dict={module.TARGETS[0]: obj("soup"), module.TARGETS[1]: obj("sauce"),
                          module.CONTAINER: obj("basket"), "extra_1": obj("extra")},
            fixtures_dict={"living_room_table": obj("table", False)},
            _eval_predicate=self.predicate, _check_grasp=self.grasp, check_contact=self.contact, done=False)
        self.steps = self.closes = self.xml_resets = self.resets = 0
        self.fail_step = None
        self.done = False
    def predicate(self, predicate):
        self.predicates.append(predicate)
        return self.membership[predicate[1]]
    def grasp(self, gripper, geoms):
        return geoms[0] in self.grasps
    def contact(self, hand, geoms):
        return geoms[0] in self.contacts
    def seed(self, seed):
        self.seed_value = seed
    def step(self, action):
        if self.steps + 1 == self.fail_step:
            raise RuntimeError("synthetic physical step failure")
        assert self.done is False and self.env.done is False
        self.steps += 1
        self.sim.value[0] += 1
        self.gripper.format_action(np.array([action[-1]]))
    def reset_from_xml_string(self, xml):
        self.xml_resets += 1
        self.sim.model.xml = xml
        self.sim.model.nq = 99 if "wrong-scene" in xml else 7
    def close(self):
        self.closes += 1


def raw_observation(env):
    return {"agentview_image": np.zeros((4, 5, 3), np.uint8),
            "robot0_eye_in_hand_image": np.ones((4, 5, 3), np.uint8),
            "robot0_eef_pos": env.sim.value[1:4].copy(), "robot0_eef_quat": np.array([0., 0, 0, 1]),
            "robot0_gripper_qpos": np.array([.04, -.04]), "robot0_joint_pos": np.zeros(7), "robot0_joint_vel": np.zeros(7)}


@pytest.mark.parametrize("target", [[1., -1.], [0., 0.], [-1., 1.], [.3, -.7]])
def test_hold_preserves_open_partial_closed_targets_without_goal_reads(target):
    env = Native()
    env.gripper.current_action = np.array(target)
    env.env._eval_predicate = lambda *args: pytest.fail("hold must not read target truth")
    hold = module.PandaPoseHold(env)
    state = env.sim.value.copy()
    contract = hold.begin()
    assert contract["gripper_command"] == 0 and contract["empirical_stability_validated"] is False
    np.testing.assert_array_equal(env.controller.goal_ori, np.eye(3))
    for _ in range(3):
        action = hold.action()
        np.testing.assert_array_equal(action, np.zeros(7))
        env.step(action)
        np.testing.assert_array_equal(env.gripper.current_action, target)
    assert env.controller.sets == 1 and env.predicates == []
    np.testing.assert_array_equal(env.sim.value[1:], state[1:])


def test_hold_corrects_drift_to_original_pose_and_clips_only_controller_bounds():
    env = Native()
    hold = module.PandaPoseHold(env)
    hold.begin()
    env.sim.value[1:4] = [.01, -.025, .2]
    angle = .1
    env.controller.orientation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    action = hold.action()
    np.testing.assert_allclose(action[:3], [-.2, .5, -1], rtol=0, atol=1e-12)
    np.testing.assert_allclose(action[3:], [0, 0, -.2, 0], rtol=0, atol=1e-12)
    np.testing.assert_array_equal(hold.reference_pos, np.zeros(3))
    with pytest.raises(RuntimeError, match="once"):
        hold.begin()


@pytest.mark.parametrize("field,value", [("impedance_mode", "variable"), ("use_delta", False),
                                       ("control_dim", 3), ("interpolator_pos", object())])
def test_unsupported_control_contract_rejected(field, value):
    env = Native()
    setattr(env.controller, field, value)
    with pytest.raises(RuntimeError):
        module.PandaPoseHold(env)


def test_hold_rejects_controller_state_mutation_and_changed_gripper_target():
    env = Native()
    hold = module.PandaPoseHold(env)
    hold.begin()
    env.gripper.current_action += .01
    with pytest.raises(RuntimeError, match="gripper"):
        hold.action()
    env = Native()
    env.controller.update = lambda **kwargs: env.sim.value.__setitem__(1, 1.)
    with pytest.raises(RuntimeError):
        module.PandaPoseHold(env).begin()


def test_release_requires_contact_and_geometry_not_just_absence_of_grasp():
    env = Native()
    contract = module.BasketContract(env)
    truth = contract.evaluator_state()
    assert truth["released"] is True
    assert truth["objects"]["extra_1"]["role"] == "distractor"
    assert truth["objects"][module.CONTAINER]["role"] == "container"
    assert truth["objects"]["living_room_table"]["role"] == "fixture"
    assert {p[1] for p in env.predicates} == {*module.TARGETS, "extra_1"}
    env.contacts.add("soup")
    assert contract.evaluator_state()["released"] is None
    env.grasps.add("soup")
    assert contract.evaluator_state()["released"] is False
    env.contacts.clear()
    env.grasps.clear()
    env.sim.data.geom_xpos[3] = [0, 0, 0]  # clear of pad spheres, but still between pads
    soup = contract.evaluator_state()["objects"][module.TARGETS[0]]
    assert soup["released"] is None
    assert soup["release_evidence"]["hand_sphere_clearance_m"] > .002
    assert soup["release_evidence"]["pinch_capsule_clearance_m"] < 0


def test_missing_contact_geometry_is_unknown_and_wrong_task_rejected():
    env = Native()
    env.sim.model.geom_rbound[3] = np.nan
    truth = module.BasketContract(env).evaluator_state()
    assert truth["released"] is None
    assert truth["objects"][module.TARGETS[0]]["release_evidence"]["reason"] == "release_evidence_unavailable"
    env.env.parsed_problem["goal_state"] = [["on", "x", "y"]]
    with pytest.raises(ValueError, match="fixed"):
        module.BasketContract(env)


@pytest.fixture
def provider(monkeypatch, tmp_path):
    env = Native()
    bddl = tmp_path / "official.bddl"
    bddl.write_text("synthetic BDDL; not an actual scene", encoding="utf-8")
    task = SimpleNamespace(name=module.TASKS["basket"]["name"], language="synthetic original instruction")
    monkeypatch.setattr(module, "create_scene", lambda *args, **kwargs: (env, task, bddl))
    monkeypatch.setattr(module, "environment_identity", lambda *args: {"name": "synthetic", "fingerprint": "fake-only"})
    def reset(native):
        native.resets += 1
    monkeypatch.setattr(module, "reset_scene", reset)
    def restore(native, state):
        state = np.asarray(state)
        if state.shape != native.sim.value.shape:
            raise ValueError("synthetic state layout mismatch")
        native.sim.value = state.copy()
        native.controller.update(force=True)
        return raw_observation(native)
    monkeypatch.setattr(module, "restore_raw_state", restore)
    monkeypatch.setattr(module, "fresh_observation", raw_observation)
    processed = []
    def process(text):
        processed.append(text)
        return text
    monkeypatch.setattr(module, "_processed_demo_xml", process)
    config = {"bddl_path": str(bddl), "original_instruction": task.language}
    return env, config, processed


def test_provider_restores_actual_xml_and_independent_passive_branch(provider):
    env, config, processed = provider
    audit = module.make_audit_provider(config)
    assert audit.metadata["real_correctness_certified"] is False
    state = np.arange(15, dtype=float) / 100
    source = state.copy()
    xml = "<mujoco model='synthetic-demo'/>"
    restored = audit.restore_demonstration(state, model_xml=xml)
    assert processed == [xml] and env.xml_resets == 1
    assert set(restored) == {"observation", "goals", "released", "release_evidence"}
    actual_observation = deepcopy(restored["observation"])
    report = audit.capture_hold_label(state, 4, model_xml=xml)
    assert [row["step"] for row in report["trace"]] == list(range(5)) and env.steps == 4
    assert report["source_state_sha256"] == state_sha256(state)
    assert report["hold_contract"]["version"] == module.HOLD_VERSION
    assert env.xml_resets == 1  # same XML is not repeatedly recreated per frame
    assert env.sim.value.tobytes() == source.tobytes() == state.tobytes()
    for key in actual_observation:
        assert actual_observation[key].tobytes() == restored["observation"][key].tobytes()
    audit.close()
    assert env.closes == 1


def test_provider_restores_parent_state_after_passive_failure(provider):
    env, config, _ = provider
    audit = module.make_audit_provider(config)
    before = env.sim.value.copy()
    env.fail_step = 2
    state = np.arange(15, dtype=float)
    with pytest.raises(RuntimeError, match="synthetic physical"):
        audit.capture_hold_label(state, 4, model_xml="<mujoco/>")
    assert env.steps == 1 and env.sim.value.tobytes() == before.tobytes()


def test_wrong_demo_xml_layout_is_rejected_and_parent_model_restored(provider):
    env, config, _ = provider
    audit = module.make_audit_provider(config)
    before = env.sim.value.copy()
    with pytest.raises(ValueError, match="layout"):
        audit.capture_hold_label(before, 4, model_xml="<mujoco model='wrong-scene'/>")
    assert env.sim.model.nq == 7 and env.sim.model.xml == "<mujoco/>"
    assert env.sim.value.tobytes() == before.tobytes() and env.steps == 0
    assert env.xml_resets == 2


def test_wrong_instruction_or_bddl_fails_without_data_replay(provider, tmp_path):
    env, config, _ = provider
    with pytest.raises(ValueError, match="instruction"):
        module.make_audit_provider({**config, "original_instruction": "remaining goal only"})
    assert env.closes == 1 and env.steps == env.resets == 0
    wrong = tmp_path / "wrong.bddl"
    wrong.write_text("not the actual task", encoding="utf-8")
    with pytest.raises(ValueError, match="BDDL"):
        module.make_audit_provider({**config, "bddl_path": str(wrong)})
    assert env.steps == 0


def test_missing_demonstration_xml_is_insufficient_not_default_scene(provider):
    env, config, _ = provider
    audit = module.make_audit_provider(config)
    state = env.sim.value.copy()
    with pytest.raises(ValueError, match="actual trajectory model_xml"):
        audit.restore_demonstration(state)
    with pytest.raises(ValueError, match="actual trajectory model_xml"):
        audit.capture_hold_label(state, 4)
    assert env.steps == env.xml_resets == 0


def test_finish_env_keeps_strict_parent_reset_and_rejects_constant_hold(monkeypatch):
    env = Native()
    calls = []
    def init(self, config):
        self.env, self._ready = env, False
    def reset(self, episode):
        calls.append(episode)
        self._ready = True
        return raw_observation(env)
    monkeypatch.setattr(module.LiberoGoalEnv, "__init__", init)
    monkeypatch.setattr(module.LiberoGoalEnv, "reset", reset)
    monkeypatch.setattr(module.LiberoGoalEnv, "goal_values", lambda self: [False, False])
    with pytest.raises(ValueError, match="constant"):
        module.make_env({"hold_action": [0] * 7})
    wrapper = module.make_env({})
    profile = module.TASKS["basket"]
    episode = {"suite": profile["suite"], "task_name": profile["name"]}
    wrapper.reset(episode)
    assert calls == [episode] and wrapper.evaluator_state()["goals"] == [False, False]
    contract = wrapper.begin_hold()
    assert contract["version"] == module.HOLD_VERSION
    np.testing.assert_array_equal(wrapper.hold_action(), np.zeros(7))
    with pytest.raises(ValueError, match="only supports"):
        wrapper.reset({"suite": "libero_90", "task_name": "other"})
