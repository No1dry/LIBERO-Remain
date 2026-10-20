"""Synthetic native-shaped data only: never create MuJoCo or load a policy."""
from copy import deepcopy
import itertools
from types import SimpleNamespace
import random
import numpy as np
import pytest

from benchmark.remaining_goals.headless import environment as module
from benchmark.remaining_goals.headless import geometry as geo
from benchmark.remaining_goals.headless.roles import PROFILES
from benchmark.remaining_goals.task_catalog import TASKS, COMMON_TEN_TASKS


class Model:
    def __init__(self, key, objects, fixtures):
        living = key in {"basket", "basket_cheese_butter", "basket_soup_cheese", "dual_mugs", "mug_pudding"}
        self.table_name = "living_room_table" if living else "table"
        self.body_names = ["world", "hand", "left", "right"] + [name + "_root" for name in [*objects, *fixtures]] + [self.table_name]
        self.geom_names = ["left_pad", "right_pad", "palm"] + [name + "_geom" for name in [*objects, *fixtures]] + [None if living else "table_collision"]
        self.nbody, self.ngeom, self.nmesh = len(self.body_names), len(self.geom_names), 1
        self.npair = self.nexclude = 0
        self.body_parentid = np.zeros(self.nbody, dtype=int)
        self.body_parentid[2:4] = 1
        self.body_weldid = np.arange(self.nbody)
        self.body_weldid[-1] = 0
        for name in fixtures: self.body_weldid[self.body_name2id(name + "_root")] = 0
        self.geom_bodyid = np.array([2, 3, 1] + list(range(4, self.nbody)))
        self.geom_type = np.full(self.ngeom, 6)
        self.geom_type[2] = 7
        self.geom_dataid = np.full(self.ngeom, -1)
        self.geom_dataid[2] = 0
        self.geom_contype = self.geom_conaffinity = np.ones(self.ngeom, dtype=int)
        self.geom_margin = np.zeros(self.ngeom)
        self.geom_gap = np.zeros(self.ngeom)
        self.geom_size = np.full((self.ngeom, 3), .01)
        self.geom_size[-1] = [.5, .5, .02]
        self.geom_rbound = np.linalg.norm(self.geom_size, axis=1)
        self.geom_rbound[2] = .45
        self.geom_pos = np.zeros((self.ngeom, 3))
        self.geom_quat = np.tile([1., 0, 0, 0], (self.ngeom, 1))
        self.mesh_vert = np.array(list(itertools.product([-.4, .4], [-.01, .01], [-.01, .01])), np.float32)
        self.mesh_vertadr, self.mesh_vertnum = np.array([0]), np.array([8])
        self.pair_geom1 = self.pair_geom2 = self.exclude_signature = np.array([], dtype=int)
        self.opt = SimpleNamespace(collision=0, disableflags=0, enableflags=0)
        self.joints = [name + "_joint" for name in objects]
        self.jnt_type = np.zeros(len(self.joints), dtype=int)
        self.site_names = ["gripper0_grip_site"] + [ref for ref in PROFILES[key] if ref not in objects and ref not in fixtures]
        self.xml_reads = 0
    def geom_name2id(self, name): return self.geom_names.index(name)
    def geom_id2name(self, index): return self.geom_names[index]
    def body_name2id(self, name): return self.body_names.index(name)
    def body_id2name(self, index): return self.body_names[index]
    def joint_name2id(self, name): return self.joints.index(name)
    def site_name2id(self, name): return self.site_names.index(name)
    def site_id2name(self, index): return self.site_names[index]
    def mesh_id2name(self, index): return "palm_compiled"
    def get_xml(self):
        self.xml_reads += 1
        return "<mujoco model='headless_cpu_synthetic'/>"


class FakeNative:
    def __init__(self, key):
        predicates = [list(p) for goal in TASKS[key]["goals"] for p in goal["predicates"]]
        targets = {p[1] for p in predicates if p[0] in {"in", "on"}}
        owners = set(PROFILES[key].values())
        owners.update(p[1] for p in predicates if p[0] == "turnon")
        movable_supports = {name for name in owners if name.startswith(("basket_", "plate_"))}
        objects = {name: SimpleNamespace(root_body=name + "_root", contact_geoms=[name + "_geom"], joints=[name + "_joint"])
                   for name in sorted(targets | movable_supports | {"distractor_1"})}
        fixtures = {name: SimpleNamespace(root_body=name + "_root", contact_geoms=[name + "_geom"], joints=[])
                    for name in sorted(owners - movable_supports) if not name.endswith("_table")}
        m = Model(key, objects, fixtures)
        positions = np.zeros((m.ngeom, 3))
        positions[:3] = [[-.04, 0, .3], [.04, 0, .3], [0, 0, .25]]
        positions[3:-1] = [.1, 0, .01]
        positions[-1] = [0, 0, -.02]
        bodies = np.zeros((m.nbody, 3))
        bodies[m.geom_bodyid] = positions
        data = SimpleNamespace(geom_xpos=positions, geom_xmat=np.tile(np.eye(3).reshape(9), (m.ngeom, 1)),
                               body_xpos=bodies, site_xpos=np.zeros((len(m.site_names), 3)), contact=[])
        for name in objects:
            gid = m.geom_name2id(name + "_geom")
            data.contact.append(SimpleNamespace(geom1=m.ngeom - 1, geom2=gid, pos=np.array([.1, 0, 0]),
                                frame=np.array([0., 0, 1, 1, 0, 0, 0, 1, 0]), dist=0., includemargin=0.))
        data.ncon = len(data.contact)
        self.sim = SimpleNamespace(model=m, data=data)
        self.gripper = SimpleNamespace(root_body="hand", contact_geoms=["left_pad", "right_pad", "palm"],
            important_geoms={"left_fingerpad": ["left_pad"], "right_fingerpad": ["right_pad"]},
            important_sites={"grip_site": "gripper0_grip_site"})
        self.robots = [SimpleNamespace(gripper=self.gripper, eef_site_id=0, sim=self.sim)]
        regions, sites = {}, {}
        for reference, owner in PROFILES[key].items():
            if reference not in objects and reference not in fixtures:
                regions[reference] = {"target": owner}
                sites[reference] = SimpleNamespace(parent_name=owner, in_box=lambda *args: True, under=lambda *args: True)
        self.grasped, self.touched, self.relations = set(), set(), {}
        self.env = SimpleNamespace(objects_dict=objects, fixtures_dict=fixtures, object_sites_dict=sites,
            workspace_name="living_room_table" if m.table_name == "living_room_table" else "kitchen_table",
            parsed_problem={"goal_state": predicates, "regions": regions},
            obj_body_id={name: m.body_name2id(obj.root_body) for name, obj in {**objects, **fixtures}.items()},
            _eval_predicate=lambda p: self.relations.get(tuple(p), False),
            _check_grasp=lambda gripper, geoms: geoms[0] in self.grasped,
            check_contact=lambda hand, geoms: geoms[0] in self.touched)
        self.steps = self.resets = 0
    def move(self, name, position):
        bid = self.env.obj_body_id[name]
        self.sim.data.body_xpos[bid] = position
        self.sim.data.geom_xpos[self.sim.model.geom_bodyid == bid] = position


@pytest.fixture(autouse=True)
def synthetic_no_native_callback(monkeypatch):
    monkeypatch.setattr(module, "_callback_status", lambda: "absent")


@pytest.mark.parametrize("key", COMMON_TEN_TASKS)
def test_all_ten_native_shaped_role_and_evidence_roundtrip(key):
    native = FakeNative(key)
    observer = module.HeadlessMeasurements(native, key)
    static = observer.measurement_static()
    truth = observer.evaluator_state([True, False])
    module.validate_evaluator_evidence(truth, static)
    assert set(truth) == {"goals", "released", "tcp", "objects", "event_candidates", "event_evidence"}
    assert truth["tcp"]["site_name"] == "gripper0_grip_site"
    assert static["role_profile"]["suite"] == TASKS[key]["suite"]
    assert truth["event_candidates"]["wrong_grasp"] == {"distractor_1": False}
    assert truth["event_candidates"]["wrong_placement"] == {"distractor_1": False}
    assert all(value is False for value in truth["event_candidates"]["table_drop"].values())
    assert native.sim.model.xml_reads == 1 and native.steps == native.resets == 0
    if key == "cabinet_close_bottom_open_top":
        assert static["role_profile"]["movable_targets"] == [] and truth["released"] is True


def test_wrong_grasp_requires_real_dualpad_and_two_cm_rise():
    native = FakeNative("basket")
    observer = module.HeadlessMeasurements(native, "basket")
    native.move("distractor_1", [.1, 0, .06])
    assert observer.evaluator_state([True, False])["event_candidates"]["wrong_grasp"]["distractor_1"] is False
    native.touched.add("distractor_1_geom")
    assert observer.evaluator_state([True, False])["event_candidates"]["wrong_grasp"]["distractor_1"] is False
    native.grasped.add("distractor_1_geom")
    truth = observer.evaluator_state([True, False])
    assert truth["event_candidates"]["wrong_grasp"]["distractor_1"] is True
    module.validate_evaluator_evidence(truth, observer.measurement_static())
    native.move("distractor_1", [.1, 0, .02])
    assert observer.evaluator_state([True, False])["event_candidates"]["wrong_grasp"]["distractor_1"] is False


def test_allowed_support_interaction_is_not_wrong_but_full_drop_is_recorded():
    native = FakeNative("dual_mugs")
    observer = module.HeadlessMeasurements(native, "dual_mugs")
    native.grasped.add("plate_1_geom")
    native.move("plate_1", [.1, 0, .06])
    truth = observer.evaluator_state([True, False])
    assert "plate_1" not in truth["event_candidates"]["wrong_grasp"]
    assert "plate_1" not in truth["event_candidates"]["wrong_placement"]
    assert truth["event_candidates"]["table_drop"]["plate_1"] is False
    native.move("plate_1", [.1, 0, -.04])
    assert observer.evaluator_state([True, False])["event_candidates"]["table_drop"]["plate_1"] is True


def test_new_wrong_relation_requires_release_and_initial_relation_is_exempt():
    native = FakeNative("basket")
    predicate = ("in", "distractor_1", "basket_1_contain_region")
    observer = module.HeadlessMeasurements(native, "basket")
    native.relations[predicate] = True
    native.grasped.add("distractor_1_geom")
    assert observer.evaluator_state([True, False])["event_candidates"]["wrong_placement"]["distractor_1"] is False
    native.grasped.clear()
    assert observer.evaluator_state([True, False])["event_candidates"]["wrong_placement"]["distractor_1"] is True
    existing = module.HeadlessMeasurements(native, "basket")
    assert existing.evaluator_state([True, False])["event_candidates"]["wrong_placement"]["distractor_1"] is False


def test_unsupported_placement_predicate_is_unknown_not_false():
    native = FakeNative("stove")
    native.env.object_sites_dict["flat_stove_1_cook_region"].under = None
    observer = module.HeadlessMeasurements(native, "stove")
    truth = observer.evaluator_state([True, False])
    assert truth["event_candidates"]["wrong_placement"]["distractor_1"] is None


def test_table_side_contact_and_unsupported_object_geometry_remain_unknown():
    native = FakeNative("basket")
    gid = native.sim.model.geom_name2id("distractor_1_geom")
    contact = next(c for c in native.sim.data.contact if c.geom2 == gid)
    contact.frame[:3] = [1, 0, 0]
    observer = module.HeadlessMeasurements(native, "basket")
    native.move("distractor_1", [.1, 0, -.04])
    assert observer.evaluator_state([True, False])["event_candidates"]["table_drop"]["distractor_1"] is None
    native2 = FakeNative("basket")
    native2.sim.model.geom_type[gid] = 2
    observer2 = module.HeadlessMeasurements(native2, "basket")
    native2.move("distractor_1", [.1, 0, -.04])
    assert observer2.evaluator_state([True, False])["event_candidates"]["table_drop"]["distractor_1"] is None


@pytest.mark.parametrize("fault", ["tcp_nan", "tcp_site", "model", "table_pose", "body_ref", "goal", "owner"])
def test_native_identity_missing_evidence_and_stale_references_fail(fault):
    native = FakeNative("basket")
    if fault == "goal": native.env.parsed_problem["goal_state"][0][1] = "distractor_1"
    elif fault == "owner": native.env.object_sites_dict["basket_1_contain_region"].parent_name = "other"
    if fault in {"goal", "owner"}:
        with pytest.raises(ValueError): module.HeadlessMeasurements(native, "basket")
        return
    observer = module.HeadlessMeasurements(native, "basket")
    if fault == "tcp_nan": native.sim.data.site_xpos[0, 0] = np.nan
    elif fault == "tcp_site": native.robots[0].eef_site_id = 1
    elif fault == "model": native.sim.model = deepcopy(native.sim.model)
    elif fault == "table_pose": native.sim.data.geom_xpos[-1, 2] -= .1
    elif fault == "body_ref": native.env.obj_body_id["distractor_1"] = 0
    with pytest.raises(geo.MeasurementError): observer.evaluator_state([True, False])


@pytest.mark.parametrize("fault", ["event", "lift", "release", "pose", "static_hash", "tcp"])
def test_offline_numeric_evidence_tampering_is_rejected(fault):
    observer = module.HeadlessMeasurements(FakeNative("basket"), "basket")
    static, truth = observer.measurement_static(), observer.evaluator_state([True, False])
    if fault == "event": truth["event_candidates"]["wrong_grasp"]["distractor_1"] = True
    elif fault == "lift": truth["event_evidence"]["wrong_grasp"]["distractor_1"]["lift_m"] = 100.
    elif fault == "release": truth["objects"]["distractor_1"]["released"] = False
    elif fault == "pose": truth["objects"][static["pose_carrier"]]["geometry_poses"]["positions"][0][0] += .4
    elif fault == "static_hash": static["geometry"]["arrays"]["geom_size"][0][0] = 99.
    else: truth["tcp"]["site_name"] = "palm_proxy"
    with pytest.raises(geo.MeasurementError): module.validate_evaluator_evidence(truth, static)


def test_no_physics_rng_controller_or_model_calls_and_independent_static_copies():
    native = FakeNative("basket")
    before = random.getstate(), np.random.get_state(), native.sim.data.geom_xpos.tobytes()
    observer = module.HeadlessMeasurements(native, "basket")
    for _ in range(3): observer.evaluator_state([True, False])
    assert random.getstate() == before[0]
    after = np.random.get_state()
    assert np.array_equal(before[1][1], after[1]) and before[1][2:] == after[2:]
    assert native.sim.data.geom_xpos.tobytes() == before[2]
    assert native.steps == native.resets == 0 and native.sim.model.xml_reads == 1
    one = observer.measurement_static()
    one["table"]["geometries"][0]["position"][0] = 999
    assert observer.measurement_static()["table"]["geometries"][0]["position"][0] != 999


def rehash_static(value):
    value["static_sha256"] = geo.canonical_hash({k: v for k, v in value.items() if k != "static_sha256"})


@pytest.mark.parametrize("fault", ["target", "event_set", "source_task", "body", "support", "table_height", "relations"])
def test_rehashed_static_cannot_change_catalog_or_support_derivation(fault):
    static = module.HeadlessMeasurements(FakeNative("basket"), "basket").measurement_static()
    role = static["role_profile"]
    if fault == "target": role["movable_targets"] = []
    elif fault == "event_set": role["wrong_grasp_objects"] = []
    elif fault == "source_task": role["suite"] = "libero_90"
    elif fault == "body": role["roles"]["distractor_1"]["body_id"] = 1
    elif fault == "support": static["initial_objects"]["distractor_1"]["table_support"]["eligible"] = False
    elif fault == "table_height": static["table"]["geometries"][0]["top_lower_bound_m"] += .1
    else: static["initial_objects"]["distractor_1"]["relations"][0]["value"] = 1
    rehash_static(static)
    with pytest.raises(geo.MeasurementError): module.validate_measurement_static(static)


@pytest.mark.parametrize("fault", ["method", "reason", "sphere", "pinch", "nan", "bool_contact"])
def test_raw_release_branches_are_verified_not_trusted(fault):
    observer = module.HeadlessMeasurements(FakeNative("basket"), "basket")
    facts = observer.evaluator_state([True, False])
    evidence = facts["objects"]["distractor_1"]["raw_evidence"]["legacy_release_evidence"]
    if fault == "method": evidence["method"] = "unspecified"
    elif fault == "reason": evidence["reason"] = "released"
    elif fault == "sphere": evidence["hand_sphere_clearance_m"] += .1
    elif fault == "pinch": evidence["pinch_capsule_clearance_m"] += .1
    elif fault == "nan": evidence["pinch_capsule_clearance_m"] = float("nan")
    else: evidence["any_gripper_contact"] = 0
    with pytest.raises(geo.MeasurementError): module.validate_evaluator_evidence(facts, observer.measurement_static())


def test_indirect_or_absent_initial_table_support_stays_unknown():
    native = FakeNative("basket")
    gid = native.sim.model.geom_name2id("distractor_1_geom")
    native.sim.data.contact = [c for c in native.sim.data.contact if c.geom2 != gid]
    native.sim.data.ncon = len(native.sim.data.contact)
    observer = module.HeadlessMeasurements(native, "basket")
    native.move("distractor_1", [.1, 0, -.1])
    facts = observer.evaluator_state([True, False])
    assert facts["event_candidates"]["table_drop"]["distractor_1"] is None
    assert facts["event_evidence"]["table_drop"]["distractor_1"]["initial_support"]["reason"] == "initial_direct_table_support_unproven"


def test_drop_boundary_uses_conservative_lower_table_face():
    native = FakeNative("basket")
    observer = module.HeadlessMeasurements(native, "basket")
    native.move("distractor_1", [.1, 0, -.03])  # upper face is exactly the -2 cm threshold
    assert observer.evaluator_state([True, False])["event_candidates"]["table_drop"]["distractor_1"] is False
    native.move("distractor_1", [.1, 0, -.030001])
    assert observer.evaluator_state([True, False])["event_candidates"]["table_drop"]["distractor_1"] is True
    table = observer.measurement_static()["table"]["geometries"][0]
    assert table["top_lower_bound_m"] < table["top_z"] == 0


def test_wrapper_keeps_strict_source_xml_gate_and_separate_restored_visual_xml(monkeypatch):
    native = FakeNative("stove")
    original = {"agentview_image": np.zeros((4, 4, 3), np.uint8)}
    episode = {"suite": TASKS["stove"]["suite"], "task_name": TASKS["stove"]["name"],
               "initial_mask": [True, False], "model_xml_sha256": "a" * 64}
    def base_init(self, config):
        self.env, self._ready = native, False
    def base_reset(self, incoming):
        native.resets += 1
        if incoming["model_xml_sha256"] != "a" * 64:
            raise ValueError("strict source XML mismatch")
        self._ready = True
        return original
    monkeypatch.setattr(module.LiberoGoalEnv, "__init__", base_init)
    monkeypatch.setattr(module.LiberoGoalEnv, "reset", base_reset)
    monkeypatch.setattr(module.LiberoGoalEnv, "goal_values", lambda self: [True, False])
    env = module.make_env({})
    assert env.reset(episode) is original
    static = env.measurement_static()
    assert static["source_reset_model_xml_sha256"] == "a" * 64
    assert static["geometry"]["compiled_model_xml_sha256"] != "a" * 64
    module.validate_measurement_static(static, episode)
    assert native.resets == 1 and native.steps == 0
    with pytest.raises(ValueError, match="strict source XML"):
        env.reset({**episode, "model_xml_sha256": "b" * 64})
    with pytest.raises(RuntimeError): env.evaluator_state()
    with pytest.raises(RuntimeError, match="no hold"): env.hold_action()
    with pytest.raises(geo.MeasurementError, match="XML identity"):
        module.validate_measurement_static(static, {**episode, "model_xml_sha256": "b" * 64})


def test_observer_setup_failure_cannot_leave_wrapper_executable(monkeypatch):
    native = FakeNative("basket")
    def base_init(self, config): self.env, self._ready = native, False
    def base_reset(self, episode):
        self._ready = True
        return {}
    monkeypatch.setattr(module.LiberoGoalEnv, "__init__", base_init)
    monkeypatch.setattr(module.LiberoGoalEnv, "reset", base_reset)
    monkeypatch.setattr(module.LiberoGoalEnv, "goal_values", lambda self: [True, True])
    env = module.make_env({})
    with pytest.raises(ValueError, match="source mask10"):
        env.reset({"suite": TASKS["basket"]["suite"], "task_name": TASKS["basket"]["name"], "initial_mask": [True, False]})
    assert env._ready is False and env.measurements is None
