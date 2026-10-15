"""Actual provider lifecycle with newly allocated CPU-native references.

The real diagnostic layout arrays are replayed, but the state vector, contacts,
controller and rendering are all nonphysical doubles. No real restore runs.
"""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.finish import demo_model
from benchmark.remaining_goals.finish import environment
from tests.test_finish_demo_model import EXTRA, ReplayModel, bind_source, make_case
from tests.test_finish_environment import Controller
from tests.test_finish_provider_lifecycle import NativeLifecycle, install_native_provider, make_state


class ReallocatingNative(NativeLifecycle):
    def __init__(self, case):
        super().__init__()
        self.case = case
        self.generations = []
        self.binding_failure = None
        self.layout_failure = False
        self._replace_native(case.base, case.baseline_xml)
        geometries = {
            "alphabet_soup_1": ("alphabet_soup_1_g0", "alphabet_soup_1_main"),
            "tomato_sauce_1": ("tomato_sauce_1_g0", "tomato_sauce_1_main"),
            "basket_1": ("basket_1_g0", "basket_1_main"),
            "extra_1": ("cream_cheese_1_g0", "cream_cheese_1_main"),
        }
        for name, (geom, body) in geometries.items():
            self.env.objects_dict[name].contact_geoms = [geom]
            self.env.objects_dict[name].root_body = body
        self.env.fixtures_dict["living_room_table"].contact_geoms = ["living_room"]
        self.env.fixtures_dict["living_room_table"].root_body = "living_room_table"
        self.gripper.contact_geoms = ["gripper0_finger1_pad_collision", "gripper0_finger2_pad_collision",
                                     "gripper0_hand_collision"]
        self.gripper.important_geoms = {
            "left_fingerpad": ["gripper0_finger1_pad_collision"],
            "right_fingerpad": ["gripper0_finger2_pad_collision"],
        }
        self._references()

    def _replace_native(self, layout, xml):
        model = ReplayModel(layout, xml)
        model.lookups = []
        lookup = model.geom_name2id
        def name2id(name):
            index = lookup(name)
            model.lookups.append((name, index))
            return index
        model.geom_name2id = name2id
        positions = np.full((model.ngeom, 3), 10., dtype=float)
        for name, position in {
            "gripper0_finger1_pad_collision": [-.04, 0, 0],
            "gripper0_finger2_pad_collision": [.04, 0, 0],
            "gripper0_hand_collision": [0, 0, -.08],
            "alphabet_soup_1_g0": [1, 0, 0],
            "tomato_sauce_1_g0": [2, 0, 0],
            "cream_cheese_1_g0": [3, 0, 0],
            "basket_1_g0": [4, 0, 0],
            "living_room": [0, 0, -1],
        }.items():
            positions[model.geom_name2id(name)] = position
        sim = SimpleNamespace(model=model, value=np.zeros(15),
                              data=SimpleNamespace(geom_xpos=positions))
        sim.get_state = lambda: SimpleNamespace(flatten=lambda: sim.value.copy())
        self.sim = sim
        self.controller = Controller(sim)
        self.robots[0].controller = self.controller
        self.robots[0].sim = sim
        self.env.sim = sim
        self.generations.append(sim)

    def _references(self):
        self.env.obj_body_id = {
            name: self.sim.model.body_name2id(obj.root_body)
            for name, obj in {**self.env.objects_dict, **self.env.fixtures_dict}.items()
        }

    def reset_from_xml_string(self, xml):
        self.gripper.current_action = np.zeros(1)
        self.events.append({"op": "xml_reset", "xml": xml, "action_shape": (1,)})
        if self.fail_xml:
            raise RuntimeError("synthetic XML reset failure")
        old = self.sim
        self.xml_resets += 1
        layout = deepcopy(self.case.loaded if EXTRA in xml else self.case.base)
        if self.layout_failure:
            layout["jnt_qposadr"][0] = 9
        self._replace_native(layout, xml)
        self._references()
        if self.binding_failure == "controller":
            self.controller.sim = old
        elif self.binding_failure == "robot":
            self.robots[0].sim = old
        elif self.binding_failure == "inner":
            self.env.sim = old
        elif self.binding_failure == "body":
            self.env.obj_body_id["alphabet_soup_1"] += 1


def setup_provider(monkeypatch, tmp_path):
    case = make_case(tmp_path, monkeypatch)
    case.branch_xml = case.source.replace("known-shape CPU fixture", "branch CPU fixture")
    case.source_variants = [case.source, case.branch_xml]
    bind_source(case, monkeypatch)
    native = ReallocatingNative(case)
    config = deepcopy(case.config)
    config["_xml_asset_scan"] = case.scan
    native, config = install_native_provider(monkeypatch, tmp_path, config=config, native=native)
    provider = environment.DemonstrationAuditProvider(config)
    return provider, native, case


def assert_current_native_contract(provider, native):
    contract = provider._require_contract()
    assert contract.env is native and contract.inner is native.env
    assert contract.hold.env is native and contract.hold.controller is native.controller
    assert contract.hold.controller.sim is native.sim
    assert native.env.sim is native.robots[0].sim is native.sim
    assert native.robots[0].controller is native.controller
    for name, obj in {**native.env.objects_dict, **native.env.fixtures_dict}.items():
        assert native.env.obj_body_id[name] == native.sim.model.body_name2id(obj.root_body)


def test_variant_first_and_continuous_restore_use_current_geometry_ids(monkeypatch, tmp_path):
    provider, native, case = setup_provider(monkeypatch, tmp_path)
    initial_sim = native.sim
    try:
        assert provider.contract is None and native.steps == native.restore_calls == 0
        parent = make_state((.01, -.03), marker=1)
        result = provider.restore_demonstration(parent, model_xml=case.source)
        assert native.sim is not initial_sim and result["released"] is True
        assert_current_native_contract(provider, native)
        for name in ("alphabet_soup_1_g0", "tomato_sauce_1_g0", "gripper0_finger1_pad_collision"):
            old_id = case.base["geom_names"].index(name)
            current_id = case.loaded["geom_names"].index(name)
            assert current_id == old_id + 1
            assert (name, current_id) in native.sim.model.lookups
        first_contract, first_sim = provider.contract, native.sim
        provider.restore_demonstration(make_state((.03, -.01), marker=2), model_xml=case.source)
        assert provider.contract is not first_contract and native.sim is first_sim
        assert native.xml_resets == 1 and native.steps == 0
        assert_current_native_contract(provider, native)
        loads = provider.metadata["demo_model_compatibility"]["loads"]
        assert len(loads) == 1 and loads[0]["classification"] == "known_basket_link7_collision"
        assert loads[0]["native_references"]["task_sim_current"] is True
        assert loads[0]["physically_equivalent_to_evaluation"] is False
    finally:
        provider.close()
    assert native.closes == 1


@pytest.mark.parametrize("fail_step", [None, 2])
def test_variant_xml_branch_hold_restores_parent_on_a_new_native_generation(monkeypatch, tmp_path, fail_step):
    provider, native, case = setup_provider(monkeypatch, tmp_path)
    parent = make_state((.01, -.03), marker=1)
    branch = make_state((.03, -.01), complete=True, marker=2)
    try:
        observation = provider.restore_demonstration(parent, model_xml=case.source)["observation"]
        original_observation = deepcopy(observation)
        original_contract, original_sim = provider.contract, native.sim
        native.fail_step = fail_step
        if fail_step is None:
            hold = provider.capture_hold_label(branch, 4, model_xml=case.branch_xml)
            assert len(hold["trace"]) == 5
        else:
            with pytest.raises(RuntimeError, match="synthetic physical step failure"):
                provider.capture_hold_label(branch, 4, model_xml=case.branch_xml)
        assert native.sim is not original_sim and provider.contract is not original_contract
        assert_current_native_contract(provider, native)
        assert provider.contract.hold.reference_pos is None
        np.testing.assert_array_equal(native.sim.value, parent)
        for key in observation:
            np.testing.assert_array_equal(observation[key], original_observation[key])
        assert native.xml_resets == 3 and len({id(sim) for sim in native.generations}) == 4
        assert native.steps == (4 if fail_step is None else 1)
        assert len(provider.metadata["demo_model_compatibility"]["loads"]) == 3
        assert all(event["action"][-1] == 0 for event in native.events if event["op"] == "step")
    finally:
        provider.close()
    assert native.closes == 1


@pytest.mark.parametrize("failure", ["controller", "robot", "inner", "body"])
def test_stale_native_references_cannot_reach_restore_or_truth(monkeypatch, tmp_path, failure):
    provider, native, case = setup_provider(monkeypatch, tmp_path)
    native.binding_failure = failure
    try:
        with pytest.raises(demo_model.DemoModelCompatibilityError) as error:
            provider.restore_demonstration(make_state(), model_xml=case.source)
        assert error.value.evidence["classification"] == "rejected"
        assert native.restore_calls == native.steps == 0 and provider.contract is None
        assert provider.metadata["demo_model_compatibility"]["loads"][-1] == error.value.evidence
        with pytest.raises(RuntimeError):
            provider._truth()
    finally:
        provider.close()
    assert native.closes == 1


def test_later_layout_error_records_specific_diff_and_closes_without_reusing_contract(monkeypatch, tmp_path):
    provider, native, case = setup_provider(monkeypatch, tmp_path)
    try:
        provider.restore_demonstration(make_state(), model_xml=case.source)
        native.layout_failure = True
        with pytest.raises(demo_model.DemoModelCompatibilityError) as error:
            provider.restore_demonstration(make_state(), model_xml=case.branch_xml)
        evidence = error.value.evidence
        assert "jnt_qposadr" in str(evidence["layout_diff"])
        assert evidence["classification"] == "rejected"
        assert provider.metadata["demo_model_compatibility"]["loads"][-1] == evidence
        assert provider.contract is None and native.restore_calls == 1 and native.steps == 0
        with pytest.raises(RuntimeError):
            provider._truth()
    finally:
        provider.close()
    assert native.closes == 1
