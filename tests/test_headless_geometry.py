"""Pure numerical measurements, with native-shaped synthetic inventories only."""
import itertools
import numpy as np
import pytest
from benchmark.remaining_goals.headless import environment as env
from benchmark.remaining_goals.headless import geometry as geo
from tests.test_headless_environment import FakeNative


@pytest.mark.parametrize("angle", [0., .4, 1.57])
@pytest.mark.parametrize("kind", [6, 7])
def test_outward_projection_contains_every_rotated_vertex(kind, angle):
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
    size, position = np.array([.3, .01, .08]), np.array([.2, -.9, .7])
    vertices = np.array(list(itertools.product(*[[-v, v] for v in size])))
    bounds = geo.project_geometry(kind, size, vertices, position, rotation)
    world = vertices @ rotation.T + position
    assert np.all(world >= bounds[:, 0]) and np.all(world <= bounds[:, 1])
    assert np.all(bounds[:, 0] < world.min(axis=0)) and np.all(bounds[:, 1] > world.max(axis=0))


@pytest.mark.parametrize("fault", ["sphere", "margin", "callback", "mask", "explicit_pairs", "welded"])
def test_unsupported_axis_coverage_is_explicit_not_a_release_proof(monkeypatch, fault):
    monkeypatch.setattr(env, "_callback_status", lambda: "present" if fault == "callback" else "absent")
    native = FakeNative("basket")
    model = native.sim.model
    gid = model.geom_name2id("distractor_1_geom")
    if fault == "sphere": model.geom_type[gid] = 2
    elif fault == "margin": model.geom_margin[gid] = .001
    elif fault == "mask": model.geom_contype[gid], model.geom_conaffinity[gid] = 2, 2
    elif fault == "explicit_pairs":
        model.npair, model.pair_geom1, model.pair_geom2 = 1, np.array([gid]), np.array([0])
    elif fault == "welded":
        bid = model.geom_bodyid[gid]
        model.body_weldid[bid], model.body_weldid[1] = 0, 0
    observer = env.HeadlessMeasurements(native, "basket")
    facts = observer.evaluator_state([True, False])
    evidence = facts["objects"]["distractor_1"]["release_evidence"]
    assert facts["objects"]["distractor_1"]["released"] is None
    assert evidence["axis_certificate"]["coverage"] == "unsupported"
    assert evidence["axis_certificate"]["certified"] is False
    env.validate_evaluator_evidence(facts, observer.measurement_static())


def test_whole_hand_union_and_two_mm_roundoff_boundary(monkeypatch):
    monkeypatch.setattr(env, "_callback_status", lambda: "absent")
    native = FakeNative("basket")
    observer = env.HeadlessMeasurements(native, "basket")
    static = observer.geometry.static
    native.move("distractor_1", [.1, 0, .24])
    assert geo.separation_certificate(static, observer.geometry.pose(), "distractor_1")["certified"] is False
    # Use actual float32 compiled mesh vertices, not decimal source guesses.
    boundary = .25 + float(native.sim.model.mesh_vert[:, 2].min()) - .01 - .002
    native.move("distractor_1", [.1, 0, boundary])
    exact = geo.separation_certificate(static, observer.geometry.pose(), "distractor_1")
    assert exact["certified"] is False and exact["gap_lower_bound_m"] < .002
    native.move("distractor_1", [.1, 0, boundary - .000001])
    safe = geo.separation_certificate(static, observer.geometry.pose(), "distractor_1")
    assert safe["certified"] is True and safe["selected_axis"] == "z"


@pytest.mark.parametrize("fault", ["missing_hand_geom", "missing_pad", "bad_mesh", "mesh_mutation", "model_generation"])
def test_geometry_completeness_and_generation_are_not_optional(monkeypatch, fault):
    monkeypatch.setattr(env, "_callback_status", lambda: "absent")
    native = FakeNative("basket")
    if fault == "missing_hand_geom": native.gripper.contact_geoms.remove("palm")
    elif fault == "missing_pad": native.gripper.important_geoms["left_fingerpad"] = []
    elif fault == "bad_mesh": native.sim.model.geom_dataid[2] = 99
    if fault in {"missing_hand_geom", "missing_pad", "bad_mesh"}:
        with pytest.raises(geo.MeasurementError): env.HeadlessMeasurements(native, "basket")
        return
    observer = env.HeadlessMeasurements(native, "basket")
    if fault == "mesh_mutation": native.sim.model.mesh_vert[0, 0] += .01
    else:
        from copy import deepcopy
        native.sim = deepcopy(native.sim)
    with pytest.raises(geo.MeasurementError): observer.evaluator_state([True, False])
