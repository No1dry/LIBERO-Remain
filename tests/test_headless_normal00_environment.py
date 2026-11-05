"""Normal00 physical measurements use the unchanged fake native geometry."""
from copy import deepcopy
import pytest

from benchmark.remaining_goals.headless import environment as module
from benchmark.remaining_goals.headless import geometry as geo
from benchmark.remaining_goals.task_catalog import TASKS, COMMON_TEN_TASKS
from tests.test_headless_environment import FakeNative, synthetic_no_native_callback


@pytest.mark.parametrize("key", COMMON_TEN_TASKS)
def test_normal00_both_official_goal_targets_remain_legal_with_v2_geometry(key):
    native = FakeNative(key)
    observer = module.HeadlessMeasurements(native, key, source_reset_model_xml_sha256="a" * 64)
    static = observer.measurement_static()
    ep = {"suite": TASKS[key]["suite"], "task_name": TASKS[key]["name"],
          "initial_mask": [False, False], "model_xml_sha256": "a" * 64}
    module.validate_measurement_static(static, ep, protocol="normal00-control")
    assert static["schema_version"] == module.SCHEMA
    targets = static["role_profile"]["movable_targets"]
    for name in targets:
        native.grasped.add(name + "_geom")
        native.move(name, [.1, 0, .06])
    facts = observer.evaluator_state([False, False])
    module.validate_evaluator_evidence(facts, static)
    assert not set(targets) & set(facts["event_candidates"]["wrong_grasp"])
    assert not set(targets) & set(facts["event_candidates"]["wrong_placement"])
    with pytest.raises(geo.MeasurementError): module.validate_measurement_static(static, ep)
    with pytest.raises(geo.MeasurementError):
        module.validate_measurement_static(static, {**ep, "initial_mask": [True, False]}, protocol="normal00-control")


@pytest.mark.parametrize("actual", [[False, False], [True, False]])
def test_explicit_normal_wrapper_exposes_actual_start_for_runner_classification(monkeypatch, actual):
    native = FakeNative("basket")
    def base_init(self, config): self.env, self._ready = native, False
    def base_reset(self, episode):
        self._ready = True
        return {"original_returned_observation": True}
    monkeypatch.setattr(module.LiberoGoalEnv, "__init__", base_init)
    monkeypatch.setattr(module.LiberoGoalEnv, "reset", base_reset)
    monkeypatch.setattr(module.LiberoGoalEnv, "goal_values", lambda self: deepcopy(actual))
    env = module.make_env({"protocol": "normal00-control"})
    ep = {"suite": TASKS["basket"]["suite"], "task_name": TASKS["basket"]["name"],
          "initial_mask": [False, False], "model_xml_sha256": "a" * 64}
    assert env.reset(ep) == {"original_returned_observation": True}
    assert env.evaluator_state()["goals"] == actual
    module.validate_measurement_static(env.measurement_static(), ep, protocol="normal00-control")
    with pytest.raises(ValueError): env.reset({**ep, "initial_mask": [True, False]})


def test_normal00_physical_distractor_grasp_support_drop_and_unknowns_unchanged():
    native = FakeNative("dual_mugs")
    observer = module.HeadlessMeasurements(native, "dual_mugs")
    native.move("distractor_1", [.1, 0, .06])
    native.grasped.add("distractor_1_geom")
    assert observer.evaluator_state([False, False])["event_candidates"]["wrong_grasp"]["distractor_1"] is True
    native.move("plate_1", [.1, 0, -.04])
    facts = observer.evaluator_state([False, False])
    assert facts["event_candidates"]["table_drop"]["plate_1"] is True
    module.validate_evaluator_evidence(facts, observer.measurement_static())
