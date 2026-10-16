"""CPU synthetic compiled geometry; no native construction or model inference."""
from copy import deepcopy
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.finish import environment as envmod
from benchmark.remaining_goals.finish import release_geometry as geo
from benchmark.remaining_goals.finish.evaluation import evaluation_contract, canonical_hash
from tests.test_finish_environment import Native

READ_CALLBACK = envmod._contact_filter_status


@pytest.fixture(autouse=True)
def no_native_callback(monkeypatch):
    # Synthetic model has no MuJoCo global module. This models only that global
    # callback absence; all geometry/projection and v1 evaluation remain real.
    monkeypatch.setattr(envmod, "_contact_filter_status", lambda: "absent")


def geometry_native():
    """Small legal group inventory: old spheres overlap, actual z separates.

    Fake compiled mesh uses a wide thin palm; all three hand geoms (both pads)
    and all released objects have independently verified owner-root coverage.
    The real BasketContract and geometry algorithms are used by integration.
    """
    env = Native()
    m = env.sim.model
    m.nbody, m.nmesh, m.npair, m.nexclude = 9, 1, 0, 0
    bodies = ["world", "hand_root", "left_root", "right_root", "soup_root", "sauce_root", "extra_root", "basket_root", "table_root"]
    m.body_id2name = lambda index: bodies[index]
    m.body_name2id = bodies.index
    m.mesh_id2name = lambda index: "compiled_palm" if index == 0 else None
    m.body_parentid = np.array([0, 0, 1, 1, 0, 0, 0, 0, 0])
    m.body_weldid = np.arange(9)
    m.geom_bodyid = np.array([2, 3, 1, 4, 5, 6, 7, 8])
    m.geom_type = np.array([6, 6, 7, 6, 6, 6, 6, 6])
    m.geom_dataid = np.array([-1, -1, 0, -1, -1, -1, -1, -1])
    m.geom_contype = np.ones(8, dtype=int)
    m.geom_conaffinity = np.ones(8, dtype=int)
    m.geom_margin = np.zeros(8)
    m.geom_gap = np.zeros(8)
    m.geom_size = np.full((8, 3), .01)
    m.geom_size[:2] = .008
    m.geom_pos = np.zeros((8, 3))
    m.geom_quat = np.tile([1., 0., 0., 0.], (8, 1))
    m.geom_rbound = np.linalg.norm(m.geom_size, axis=1)
    m.geom_rbound[2] = np.linalg.norm([.2, .01, .01])
    m.mesh_vert = np.array(list(itertools.product([-.2, .2], [-.01, .01], [-.01, .01])), dtype=np.float32)
    m.mesh_vertadr, m.mesh_vertnum = np.array([0]), np.array([8])
    m.pair_geom1 = m.pair_geom2 = m.exclude_signature = np.array([], dtype=int)
    m.opt = SimpleNamespace(collision=0, disableflags=0, enableflags=0)
    env.sim.data.geom_xmat = np.tile(np.eye(3).reshape(9), (8, 1))
    env.sim.data.geom_xpos[:5] = [[-.04, 0, .16], [.04, 0, .16], [0, 0, .12], [0, 0, 0], [.03, 0, 0]]
    env.gripper.root_body = "hand_root"
    for name, root in zip([*envmod.TARGETS, "extra_1", envmod.CONTAINER], ["soup_root", "sauce_root", "extra_root", "basket_root"]):
        env.env.objects_dict[name].root_body = root
    env.env.fixtures_dict["living_room_table"].root_body = "table_root"
    return env


def make_static(env=None):
    env = env or geometry_native()
    objs = {k: v for k, v in env.env.objects_dict.items() if k != envmod.CONTAINER and v.joints}
    return env, geo.build_measurement_static(env.sim.model, objs, env.gripper, contact_filter_status="absent")


def rehash(static):
    static["static_sha256"] = canonical_hash({k: v for k, v in static.items() if k != "static_sha256"})
    return static


def test_rotated_translated_box_negative_coordinates_and_scale():
    theta = np.pi / 4
    rot = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    got = geo.project_geometry(6, [2, 1, .5], None, [-3, -4, -5], rot)
    corners = np.array(list(itertools.product([-2, 2], [-1, 1], [-.5, .5]))) @ rot.T + [-3, -4, -5]
    expected = np.stack([corners.min(0), corners.max(0)], 1)
    assert np.all(got[:, 0] < expected[:, 0]) and np.all(got[:, 1] > expected[:, 1])
    np.testing.assert_allclose(got, expected, rtol=0, atol=3e-14)


def test_mesh_uses_compiled_vertices_not_size_or_untransformed_bounds():
    vertices = np.array([[-3, -1, 0], [2, 1, -2], [1, 2, 4], [-2, 3, 0]], dtype=np.float32)
    rot = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    expected = vertices @ rot.T + [-5, -4, 2]
    actual = geo.project_geometry(7, [999, 999, 999], vertices, [-5, -4, 2], rot)
    expected = np.stack([expected.min(0), expected.max(0)], 1)
    assert np.all(actual[:, 0] < expected[:, 0]) and np.all(actual[:, 1] > expected[:, 1])
    np.testing.assert_allclose(actual, expected, rtol=0, atol=4e-14)


def test_actual_contract_sphere_false_positive_axis_positive_and_legacy_bytes_unchanged():
    env = geometry_native()
    old = envmod.BasketContract(env).evaluator_state()
    before = json.dumps(old, sort_keys=True, allow_nan=False).encode()
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    result = contract.evaluator_state()
    assert result["released"] is True
    assert old["released"] is None
    assert json.dumps(result["measurement"]["legacy"], sort_keys=True, allow_nan=False).encode() == before
    assert json.dumps(envmod.BasketContract(env).evaluator_state(), sort_keys=True, allow_nan=False).encode() == before
    for name in envmod.TARGETS:
        legacy = old["objects"][name]["release_evidence"]
        assert legacy["hand_sphere_clearance_m"] < 0 and legacy["pinch_capsule_clearance_m"] > .002
        cert = result["objects"][name]["release_evidence"]["axis_certificate"]
        assert cert["certified"] is True and cert["selected_axis"] == "z"
        assert cert["hand_geom_ids"] == [0, 1, 2]
    geo.validate_measurement_frame(result, evaluation_contract(), contract.measurement_static())


@pytest.mark.parametrize("condition,expected", [("held", False), ("contact", None), ("pinch", None), ("overlap", None), ("old_true", True)])
def test_release_order_and_known_positive_safety(condition, expected):
    env = geometry_native()
    if condition == "held":
        env.grasps.add("soup")
    elif condition == "contact":
        env.contacts.add("soup")
    elif condition == "pinch":
        env.sim.data.geom_xpos[3] = [0, 0, .16]
    elif condition == "overlap":
        env.sim.data.geom_xpos[3] = [0, 0, .12]
    else:
        env.sim.data.geom_xpos[3] = [1, 0, 0]
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    value = contract.evaluator_state()
    assert value["objects"][envmod.TARGETS[0]]["released"] is expected
    geo.validate_measurement_frame(value, evaluation_contract(), contract.measurement_static())


def test_union_not_favourable_pair_and_fixed_tie_order():
    env, static = make_static()
    poses = geo.read_geometry_pose(env.sim.model, env.sim.data, static)
    # One palm overlaps target: a separated finger pair is insufficient.
    poses["positions"][poses["geom_ids"].index(2)] = [0, 0, 0]
    assert not geo.separation_certificate(static, poses, envmod.TARGETS[0])["certified"]
    # Three equal box groups: exact x/y tie resolves to x, independently of IDs.
    static["arrays"]["geom_type"][2] = 6
    static["meshes"] = {}
    static["arrays"]["geom_dataid"][2] = -1
    for i in (0, 1, 2, 3):
        static["arrays"]["geom_size"][i] = [.01, .01, .01]
        poses["positions"][poses["geom_ids"].index(i)] = [1, 1, 1] if i < 3 else [0, 0, 0]
    rehash(static)
    geo.validate_measurement_static(static)
    cert = geo.separation_certificate(static, poses, envmod.TARGETS[0])
    assert cert["selected_axis"] == "x" and .98 - 1e-14 < cert["gap_lower_bound_m"] < .98


@pytest.mark.parametrize("change,reason", [("type", "unsupported_geometry_type"), ("margin", "unsupported_nonzero_margin_or_gap"),
    ("gap", "unsupported_nonzero_margin_or_gap"), ("mask", "incompatible_collision_masks"),
    ("pair", "unsupported_collision_filter_configuration"), ("exclude", "unsupported_collision_filter_configuration"),
    ("disable", "unsupported_collision_filter_configuration"), ("enable", "unsupported_collision_filter_configuration"),
    ("collision", "unsupported_collision_filter_configuration")])
def test_valid_unsupported_geometry_and_filters_keep_unknown(change, reason):
    env = geometry_native()
    m = env.sim.model
    if change == "type":
        m.geom_type[3] = 2
    elif change in ("margin", "gap"):
        getattr(m, "geom_" + change)[3] = .001
    elif change == "mask":
        m.geom_contype[3] = m.geom_conaffinity[3] = 2
    elif change == "pair":
        m.npair = 1; m.pair_geom1 = np.array([3]); m.pair_geom2 = np.array([0])
    elif change == "exclude":
        m.nexclude = 1; m.exclude_signature = np.array([(1 << 16) + 4])
    else:
        setattr(m.opt, {"disable": "disableflags", "enable": "enableflags", "collision": "collision"}[change], 1)
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    truth = contract.evaluator_state()
    assert truth["objects"][envmod.TARGETS[0]]["released"] is None
    assert reason in truth["objects"][envmod.TARGETS[0]]["release_evidence"]["axis_certificate"]["coverage_reasons"]


@pytest.mark.parametrize("fault", ["missing", "mesh_id", "mesh_range", "nan_vertices", "nan_pose", "rotation", "size",
    "body", "cycle", "group_omit", "pad_omit", "duplicate", "mask_disabled", "bad_type"])
def test_invalid_measurement_is_technical_not_negative(fault):
    env = geometry_native()
    m = env.sim.model
    if fault == "missing": del m.geom_margin
    elif fault == "mesh_id": m.geom_dataid[2] = 4
    elif fault == "mesh_range": m.mesh_vertnum[0] = 9
    elif fault == "nan_vertices": m.mesh_vert[0, 0] = np.nan
    elif fault == "nan_pose": env.sim.data.geom_xpos[3, 0] = np.nan
    elif fault == "rotation": env.sim.data.geom_xmat[3, 0] = 2
    elif fault == "size": m.geom_size[3, 0] = -1
    elif fault == "body": m.geom_bodyid[3] = 999
    elif fault == "cycle": m.body_parentid[2] = 3; m.body_parentid[3] = 2
    elif fault == "group_omit": env.gripper.contact_geoms = ["left", "right"]
    elif fault == "pad_omit": env.gripper.important_geoms = {"left_fingerpad": ["left"], "right_fingerpad": ["soup"]}
    elif fault == "duplicate": env.gripper.contact_geoms = ["left", "right", "palm", "left"]
    elif fault == "mask_disabled": m.geom_contype[3] = m.geom_conaffinity[3] = 0
    elif fault == "bad_type": m.geom_type[3] = 99
    with pytest.raises(geo.MeasurementError):
        contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
        contract.evaluator_state()


@pytest.mark.parametrize("change", ["replacement", "raw_replacement", "mesh", "xml", "membership", "sim"])
def test_model_reset_and_static_mutations_invalidate_observer(change):
    env = geometry_native()
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    if change == "replacement": env.sim.model = deepcopy(env.sim.model)
    elif change == "raw_replacement": env.sim.model._model = deepcopy(env.sim.model)
    elif change == "mesh": env.sim.model.mesh_vert[0, 0] += .001
    elif change == "xml":
        # Native XML reset compiles a new generation; a fake-only .xml string
        # assignment is not an actual MuJoCo model replacement.
        env.sim.model = deepcopy(env.sim.model)
        env.sim.model.xml = "<mujoco model='new'/>"
    elif change == "sim": env.sim = deepcopy(env.sim)
    else: env.env.objects_dict[envmod.TARGETS[0]].contact_geoms = ["sauce"]
    with pytest.raises(geo.MeasurementError): contract.evaluator_state()


def test_observer_pure_read_and_snapshot_defensive_copies():
    env = geometry_native()
    before = env.sim.value.tobytes(), env.gripper.current_action.tobytes(), random.getstate(), np.random.get_state()
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    truth = contract.evaluator_state()
    static = contract.measurement_static()
    static["meshes"]["0"]["vertices"][0][0] = 999
    assert contract.measurement_static()["meshes"]["0"]["vertices"][0][0] != 999
    assert before[:3] == (env.sim.value.tobytes(), env.gripper.current_action.tobytes(), random.getstate())
    after = np.random.get_state()
    assert before[3][0] == after[0] and np.array_equal(before[3][1], after[1]) and before[3][2:] == after[2:]
    assert env.steps == env.resets == env.xml_resets == env.controller.updates == env.controller.sets == 0
    assert "measurement" in truth


@pytest.mark.parametrize("tamper", ["gap", "released", "pose", "static", "legacy_false", "contract"])
def test_offline_certificate_and_safety_recompute_reject_tampering(tamper):
    contract = envmod.BasketContract(geometry_native(), evaluation_contract=evaluation_contract())
    frame, static = contract.evaluator_state(), contract.measurement_static()
    if tamper == "gap": frame["objects"][envmod.TARGETS[0]]["release_evidence"]["axis_certificate"]["gap_lower_bound_m"] += 1
    elif tamper == "released": frame["objects"][envmod.TARGETS[0]]["released"] = None
    elif tamper == "pose": frame["measurement"]["poses"]["positions"][0][2] += .03
    elif tamper == "static": static["meshes"]["0"]["vertices"][0][0] = 999
    elif tamper == "legacy_false": frame["measurement"]["legacy"]["objects"][envmod.TARGETS[0]]["released"] = False
    else: frame["measurement"]["contract_sha256"] = "0" * 64
    with pytest.raises(geo.MeasurementError): geo.validate_measurement_frame(frame, evaluation_contract(), static)


def test_task009_external_step280_projection():
    """Opt-in FILES ONLY. Absence is a disclosed skip, never fabricated proof."""
    root = os.environ.get("LIBERO_REMAIN_TASK009_FIXTURE")
    if not root:
        pytest.skip("external 883-file task009 backup not available; set LIBERO_REMAIN_TASK009_FIXTURE")
    from benchmark.remaining_goals.finish.release_audit_native import read_typed_npz
    root = Path(root)
    static = read_typed_npz(root / "static.npz", expected_sha256="9cf8d6654735b949e67a97840b961659fab21e8b11d149a9a2daf41e08ce0626")
    frame = read_typed_npz(root / "native/0280.npz", expected_sha256="b025d3251339def6e393529034adb2841b8ad1d196f243b4a2be88bfdc8b73cd")
    arrays, positions = static["model_arrays"], frame["geometry"]["geom_xpos"]
    rotations = frame["geometry"]["geom_xmat"].reshape(-1, 3, 3)
    intervals = {}
    for group in ("hand", "tomato_sauce_1"):
        values = []
        for gid in static["groups"][group]:
            kind, mid = int(arrays["geom_type"][gid]), int(arrays["geom_dataid"][gid])
            vertices = static["meshes"][str(mid)]["vertices"] if kind == 7 else None
            values.append(geo.project_geometry(kind, arrays["geom_size"][gid], vertices, positions[gid], rotations[gid], conservative=False))
        values = np.asarray(values)
        intervals[group] = [values[:, 2, 0].min(), values[:, 2, 1].max()]
    assert intervals["hand"][0] - intervals["tomato_sauce_1"][1] == pytest.approx(.014728840702336488, abs=2e-16)
    original = frame["original_evaluator_truth"]["objects"]["tomato_sauce_1"]["release_evidence"]
    assert original["hand_sphere_clearance_m"] == -.023432828897614985
    assert original["pinch_capsule_clearance_m"] == .014681542347722397


def test_no_per_frame_xml_serialization_or_native_calls():
    env = geometry_native()
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    env.sim.model.get_xml = lambda: pytest.fail("no per-frame mj_saveLastXML")
    for _ in range(3):
        assert contract.evaluator_state()["released"] is True
    assert env.steps == env.resets == env.xml_resets == env.controller.updates == 0


def test_compound_object_whole_union_prevents_favourable_component_selection():
    env = geometry_native()
    env.env.objects_dict[envmod.TARGETS[0]].contact_geoms = ["soup", "extra"]
    del env.env.objects_dict["extra_1"]
    env.sim.model.geom_bodyid[5] = 4
    env.sim.data.geom_xpos[5] = [0, 0, .12]
    env, static = make_static(env)
    poses = geo.read_geometry_pose(env.sim.model, env.sim.data, static)
    cert = geo.separation_certificate(static, poses, envmod.TARGETS[0])
    assert cert["object_geom_ids"] == [3, 5]
    assert not cert["certified"]
    assert cert["axes_evidence"][2]["object_extreme_geom_ids"] == [3, 5]


@pytest.mark.parametrize("delta,certified", [(0., False), (-1e-12, False), (1e-16, False), (1e-10, True)])
def test_two_mm_roundoff_boundary_never_rounds_up_to_certificate(delta, certified):
    env = geometry_native()
    env.sim.model.geom_type[2] = 6
    env.sim.model.geom_dataid[2] = -1
    env.sim.model.geom_size[:4] = .01
    env.sim.data.geom_xpos[:3] = [0, 0, .022 + delta]
    env, static = make_static(env)
    cert = geo.separation_certificate(static, geo.read_geometry_pose(env.sim.model, env.sim.data, static), envmod.TARGETS[0])
    assert cert["certified"] is certified
    assert cert["gap_lower_bound_m"] < .002 + delta
    assert cert["floating_point_bound"].startswith("float64 gamma(16)")


@pytest.mark.parametrize("tamper", ["method", "unavailable", "nan", "no_contact_bool", "reason", "sphere", "released", "aggregate", "excluded"])
def test_legacy_measurement_technical_errors_never_become_calibration_unknown(tamper):
    env, static = make_static()
    poses = geo.read_geometry_pose(env.sim.model, env.sim.data, static)
    legacy = envmod.BasketContract(env).evaluator_state()
    evidence = legacy["objects"][envmod.TARGETS[0]]["release_evidence"]
    if tamper == "method": evidence["method"] = "unknown"
    elif tamper == "unavailable": evidence.update(reason="release_evidence_unavailable", error="failed native lookup")
    elif tamper == "nan": evidence["pinch_capsule_clearance_m"] = float("nan")
    elif tamper == "no_contact_bool": evidence["any_gripper_contact"] = None
    elif tamper == "reason": evidence["reason"] = "arbitrary unknown"
    elif tamper == "sphere": evidence["hand_sphere_clearance_m"] += 1e-4
    elif tamper == "released": legacy["objects"][envmod.TARGETS[0]]["released"] = True
    elif tamper == "aggregate": legacy["released"] = True
    else: legacy["objects"][envmod.CONTAINER]["release_evidence"]["method"] = "unknown"
    with pytest.raises(geo.MeasurementError): geo.measurement_frame(legacy, evaluation_contract(), static, poses)


@pytest.mark.parametrize("status", ["present", "unverified"])
def test_unverified_or_custom_contact_callback_never_certifies(monkeypatch, status):
    monkeypatch.setattr(envmod, "_contact_filter_status", lambda: status)
    contract = envmod.BasketContract(geometry_native(), evaluation_contract=evaluation_contract())
    frame = contract.evaluator_state()
    assert frame["released"] is None
    cert = frame["objects"][envmod.TARGETS[0]]["release_evidence"]["axis_certificate"]
    assert "contact_filter_callback_" + status in cert["coverage_reasons"]
    geo.validate_measurement_frame(frame, evaluation_contract(), contract.measurement_static())


def test_contact_callback_changes_invalidate_bound_static(monkeypatch):
    contract = envmod.BasketContract(geometry_native(), evaluation_contract=evaluation_contract())
    # This is the captured getter used by the observer, not a model API.
    contract.geometry_observer.contact_filter_getter = lambda: "present"
    with pytest.raises(geo.MeasurementError, match="identity changed"):
        contract.evaluator_state()


@pytest.mark.parametrize("kind,expected", [("missing", "unverified"), ("no_getter", "unverified"),
    ("raises", "unverified"), ("none", "absent"), ("callback", "present")])
def test_getter_reads_only_already_loaded_callback(monkeypatch, kind, expected):
    import sys
    calls = []
    def getter():
        calls.append("get")
        if kind == "raises": raise RuntimeError("synthetic unavailable getter")
        return None if kind == "none" else lambda *args: 1
    if kind == "missing": monkeypatch.delitem(sys.modules, "mujoco", raising=False)
    elif kind == "no_getter": monkeypatch.setitem(sys.modules, "mujoco", SimpleNamespace())
    else: monkeypatch.setitem(sys.modules, "mujoco", SimpleNamespace(get_mjcb_contactfilter=getter))
    assert READ_CALLBACK() == expected
    assert calls == ([] if kind in {"missing", "no_getter"} else ["get"])
    if kind == "missing": assert "mujoco" not in sys.modules


def test_welded_filter_and_invalid_weld_reference_are_distinct():
    env = geometry_native()
    # Both groups welded to world are a legal compiled structure with an
    # unsupported same-weld filter. No collision geometry was removed.
    env.sim.model.body_weldid[:] = 0
    contract = envmod.BasketContract(env, evaluation_contract=evaluation_contract())
    cert = contract.evaluator_state()["objects"][envmod.TARGETS[0]]["release_evidence"]["axis_certificate"]
    assert cert["body_filtered_pairs"] and "unsupported_welded_or_parent_body_filter" in cert["coverage_reasons"]
    assert not cert["certified"]
    bad = geometry_native()
    bad.sim.model.body_weldid[4] = 3  # unrelated branch, not an ancestor
    with pytest.raises(geo.MeasurementError, match="welded body reference"):
        envmod.BasketContract(bad, evaluation_contract=evaluation_contract())
