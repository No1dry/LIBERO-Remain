"""Task013 CPU regression: saved contacts, no MuJoCo/model/renderer invocation."""
from copy import deepcopy
import numpy as np
import pytest

from benchmark.remaining_goals.headless import environment as module
from benchmark.remaining_goals.headless import geometry as geo
from benchmark.remaining_goals.headless.schema import analyze_trace
from tests.test_headless_environment import FakeNative


BODY_Z = 0.43219202665003076
TOP_Z = 0.43676000000000015
CONTACT_Z = 0.4367599203801213
CONTACT_DISTANCE = -7.961987883728483e-8


def numeric_native(key="basket", name="basket_1"):
    """Real reported numbers in explicitly synthetic native-shaped geometry."""
    native = FakeNative(key)
    model, data = native.sim.model, native.sim.data
    data.geom_xpos[:, 2] += TOP_Z
    data.body_xpos[:, 2] += TOP_Z
    data.site_xpos[:, 2] += TOP_Z
    for contact in data.contact:
        contact.pos[2] += TOP_Z
    gid = model.geom_name2id(name + "_geom")
    bid = native.env.obj_body_id[name]
    data.body_xpos[bid, 2] = BODY_Z
    # The object's collision box is above its arbitrary body-frame origin.
    model.geom_pos[gid, 2] = data.geom_xpos[gid, 2] - BODY_Z
    contact = next(c for c in data.contact if c.geom2 == gid)
    contact.pos[2], contact.dist = CONTACT_Z, CONTACT_DISTANCE
    return native


def make_legacy_observer(native, key="basket"):
    """Create a valid historical v1 fixture without mocking either validator."""
    observer = module.HeadlessMeasurements(native, key)
    legacy = observer.measurement_static()
    legacy["schema_version"] = module.LEGACY_SCHEMA
    legacy.pop("support_rule")
    for name in legacy["role_profile"]["table_drop_objects"]:
        initial = legacy["initial_objects"][name]
        initial["table_support"] = module._initial_support(name, initial["position"], legacy["table"],
            legacy["geometry"], legacy["initial_contacts"], legacy["geometry"]["filters"]["contact_filter_callback"],
            support_rule=module.LEGACY_SUPPORT_RULE)
    legacy["static_sha256"] = geo.canonical_hash({k: v for k, v in legacy.items() if k != "static_sha256"})
    module.validate_measurement_static(legacy)
    observer.static = legacy
    return observer


@pytest.fixture(autouse=True)
def synthetic_callback(monkeypatch):
    monkeypatch.setattr(module, "_callback_status", lambda: "absent")


def test_reported_contact_proves_support_despite_low_body_origin_and_legacy_still_reads():
    observer = make_legacy_observer(numeric_native())
    old_static = observer.measurement_static()
    old_fact = observer.evaluator_state([True, True])
    before_static, before_fact = deepcopy(old_static), deepcopy(old_fact)
    tolerance = abs(CONTACT_DISTANCE) / 2 + 1e-7
    assert tolerance == 1.398099394186424e-7
    assert abs(CONTACT_Z - TOP_Z) <= tolerance and BODY_Z < TOP_Z - tolerance
    assert old_static["initial_objects"]["basket_1"]["table_support"]["eligible"] is None
    assert old_fact["event_candidates"]["table_drop"]["basket_1"] is None
    module.validate_evaluator_evidence(old_fact, old_static)
    corrected = module.corrected_measurement_static(old_static)
    assert corrected["schema_version"] == module.SCHEMA
    assert corrected["support_rule"] == module.SUPPORT_RULE
    assert corrected["initial_objects"]["basket_1"]["table_support"]["eligible"] is True
    assert corrected["static_sha256"] != old_static["static_sha256"]
    new_fact = module.recompute_table_drop(old_fact, corrected)
    assert new_fact["event_candidates"]["table_drop"]["basket_1"] is False
    module.validate_evaluator_evidence(new_fact, corrected)
    assert old_static == before_static and old_fact == before_fact
    for key in ("goals", "released", "tcp", "objects"):
        assert new_fact[key] == old_fact[key]
    for key in ("wrong_grasp", "wrong_placement"):
        assert new_fact["event_candidates"][key] == old_fact["event_candidates"][key]
        assert new_fact["event_evidence"][key] == old_fact["event_evidence"][key]


@pytest.mark.parametrize("key,name", [("basket", "basket_1"), ("dual_mugs", "plate_1"), ("basket", "distractor_1")])
def test_rule_applies_to_every_eligible_object_not_specific_basket_or_episode(key, name):
    native = numeric_native(key, name)
    current = module.HeadlessMeasurements(native, key)
    assert current.measurement_static()["initial_objects"][name]["table_support"]["eligible"] is True
    legacy = make_legacy_observer(native, key)
    assert legacy.measurement_static()["initial_objects"][name]["table_support"]["eligible"] is None


@pytest.mark.parametrize("case", ["side", "no_contact", "unsupported", "wrong_direction", "outside_plane"])
def test_corrected_rule_does_not_certify_ambiguous_support(case):
    native = numeric_native()
    gid = native.sim.model.geom_name2id("basket_1_geom")
    contact = next(c for c in native.sim.data.contact if c.geom2 == gid)
    if case == "side": contact.frame[:3] = [1, 0, 0]
    elif case == "no_contact":
        native.sim.data.contact = [item for item in native.sim.data.contact if item is not contact]
        native.sim.data.ncon -= 1
    elif case == "unsupported": native.sim.model.geom_type[-1] = 2
    elif case == "wrong_direction": contact.frame[:3] = [0, 0, -1]
    else: contact.pos[2] -= .001
    observer = module.HeadlessMeasurements(native, "basket")
    assert observer.measurement_static()["initial_objects"]["basket_1"]["table_support"]["eligible"] is None


def test_contact_geometry_order_is_respected():
    native = numeric_native()
    gid = native.sim.model.geom_name2id("basket_1_geom")
    contact = next(c for c in native.sim.data.contact if c.geom2 == gid)
    contact.geom1, contact.geom2 = contact.geom2, contact.geom1
    contact.frame[:3] *= -1
    assert module.HeadlessMeasurements(native, "basket").measurement_static()["initial_objects"]["basket_1"]["table_support"]["eligible"] is True


def test_real_drop_still_needs_full_geometry_below_two_cm_and_five_frames():
    native = numeric_native()
    observer = make_legacy_observer(native)
    corrected = module.corrected_measurement_static(observer.measurement_static())
    trace, original = [], []
    for step in range(7):
        # Two initial above-table frames, then a true whole-box drop.
        if step >= 2:
            native.move("basket_1", [.1, 0, TOP_Z - .04])
        row = observer.evaluator_state([True, True])
        row.update(step=step, action=None if step == 0 else [0.] * 7)
        original.append(row)
        trace.append(module.recompute_table_drop(row, corrected))
    assert analyze_trace(trace[:-1])["confirmed_events"] == []
    result = analyze_trace(trace)
    assert result["confirmed_events"] == [{"event": "table_drop", "object": "basket_1", "start_step": 2, "confirmation_step": 6}]
    assert all(row["event_candidates"]["table_drop"]["basket_1"] is False for row in trace[:2])
    assert result["path_length_m"] == analyze_trace(original)["path_length_m"]


def test_pure_projection_reuses_saved_bounds_without_native_or_release_recomputation(monkeypatch):
    observer = make_legacy_observer(numeric_native())
    static, facts = observer.measurement_static(), observer.evaluator_state([True, True])
    corrected = module.corrected_measurement_static(static)
    def forbidden(*args, **kwargs): raise AssertionError("unnecessary native/geometry/release work")
    monkeypatch.setattr(geo, "object_bounds", forbidden)
    monkeypatch.setattr(geo, "release_measurement", forbidden)
    monkeypatch.setattr(module, "_release", forbidden)
    assert module.recompute_table_drop(facts, corrected)["event_candidates"]["table_drop"]["basket_1"] is False


@pytest.mark.parametrize("fault", ["old_tag_new_rule", "new_without_rule", "new_wrong_rule", "legacy_support_in_v2"])
def test_version_dispatch_cannot_silently_reinterpret_old_support(fault):
    old = make_legacy_observer(numeric_native()).measurement_static()
    if fault == "old_tag_new_rule": old["support_rule"] = module.SUPPORT_RULE
    elif fault == "new_without_rule": old["schema_version"] = module.SCHEMA
    elif fault == "new_wrong_rule": old.update(schema_version=module.SCHEMA, support_rule=module.LEGACY_SUPPORT_RULE)
    else: old.update(schema_version=module.SCHEMA, support_rule=module.SUPPORT_RULE)
    old["static_sha256"] = geo.canonical_hash({k: v for k, v in old.items() if k != "static_sha256"})
    with pytest.raises(geo.MeasurementError): module.validate_measurement_static(old)
