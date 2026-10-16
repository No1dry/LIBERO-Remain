"""Replay diagnosed layouts with synthetic files/native doubles, never physics.

The names/address arrays are the committed real diagnostic. HDF, meshes, XML
and compiled model accessors below are explicit CPU fakes; known-source digests
are monkeypatched only for these tiny fixtures. No real LIBERO model is loaded.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import h5py
import numpy as np
import pytest

from benchmark.remaining_goals.finish import demo_model as module
from benchmark.remaining_goals.finish import environment
from benchmark.remaining_goals.finish.data_profiles import ASSET_KEYS, DEFAULT_PROFILE
from benchmark.remaining_goals.finish.xml_assets import resolve_xml, scan_xml_assets
from tests.finish_domain_helpers import make_assets


EVIDENCE = json.loads((Path(__file__).resolve().parents[1] /
    "docs/stage_summaries/evidence/stage04_task008_layout_diagnosis_2026-10-15.json").read_text(encoding="utf-8"))
EXTRA = "robot0_link7_collision"
MESH = "robot0_link7"
MESH_SOURCE = "/old/robosuite/models/assets/robots/panda/meshes/link7.stl"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def source_xml(*, extra=True):
    root = ET.Element("mujoco", {"model": "SYNTHETIC known-shape CPU fixture"})
    assets = ET.SubElement(root, "asset")
    ET.SubElement(assets, "mesh", {"name": MESH, "file": MESH_SOURCE})
    world = ET.SubElement(root, "worldbody")
    body = ET.SubElement(world, "body", {"name": "robot0_link7"})
    if extra:
        ET.SubElement(body, "geom", deepcopy(EVIDENCE["first_HDF_variant"]["extra"][0]["attributes"]))
    anonymous = ET.SubElement(world, "body", {"name": "living_room_table_col"})
    for index in range(7):
        ET.SubElement(anonymous, "geom", {"type": "box", "size": ".1 .2 .3", "pos": f"{index} 0 0"})
    for camera in EVIDENCE["first_HDF_variant"]["selected_cameras"].values():
        ET.SubElement(world, "camera", deepcopy(camera))
    return ET.tostring(root, encoding="unicode")


class ReplayModel:
    """Read-only-like model fields populated from all real layout entries."""
    def __init__(self, layout, xml):
        self.layout = deepcopy(layout)
        self.xml = xml
        for key, value in layout.items():
            setattr(self, key, deepcopy(value) if not isinstance(value, list) else np.array(value))
        # Compiled arrays are synthetic. In particular mesh compilation can
        # recenter a geom; these are deliberately nonzero/nonidentity.
        self.geom_type = np.full(self.ngeom, 7, dtype=int)
        self.geom_dataid = np.zeros(self.ngeom, dtype=int)
        self.geom_rgba = np.tile([.3, .4, .5, 1.], (self.ngeom, 1))
        self.geom_contype = np.ones(self.ngeom, dtype=int)
        self.geom_conaffinity = np.ones(self.ngeom, dtype=int)
        self.geom_condim = np.full(self.ngeom, 3, dtype=int)
        self.geom_group = np.zeros(self.ngeom, dtype=int)
        self.geom_pos = np.tile([.01, -.02, .03], (self.ngeom, 1))
        self.geom_quat = np.tile([.5, .5, .5, .5], (self.ngeom, 1))
        self.geom_size = np.tile([.1, .2, .3], (self.ngeom, 1))
        self.geom_friction = np.tile([1., .005, .0001], (self.ngeom, 1))
        self.geom_solref = np.tile([.02, 1.], (self.ngeom, 1))
        self.geom_solimp = np.tile([.9, .95, .001, .5, 2.], (self.ngeom, 1))
        self.geom_margin = np.zeros(self.ngeom)
        self.geom_gap = np.zeros(self.ngeom)
        self.geom_rbound = np.full(self.ngeom, .01)
        self.mesh_name = MESH
        if EXTRA in layout["geom_names"]:
            self.geom_rgba[layout["geom_names"].index(EXTRA)] = [0., .5, 0., 1.]

    def get_xml(self):
        return self.xml

    def mesh_id2name(self, index):
        return self.mesh_name if index == 0 else None

    def mesh_name2id(self, name):
        return 0 if name == self.mesh_name else -1

    def geom_name2id(self, name):
        return self.layout["geom_names"].index(name)

    def geom_id2name(self, index):
        return self.layout["geom_names"][index]

    def body_id2name(self, index):
        return self.layout["body_names"][index]

    def body_name2id(self, name):
        return self.layout["body_names"].index(name)

    def joint_id2name(self, index):
        return self.layout["joint_names"][index]

    def site_id2name(self, index):
        return self.layout["site_names"][index]

    def actuator_id2name(self, index):
        return self.layout["actuator_names"][index]


def make_case(tmp_path, monkeypatch):
    config = make_assets(tmp_path / "source")
    roots = {"robosuite": tmp_path / "runtime/robosuite/models/assets"}
    target = roots["robosuite"] / "robots/panda/meshes/link7.stl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"SYNTHETIC mesh contents; not a compiled mesh or historical SHA")
    case = SimpleNamespace(config=config, roots=roots, target=target, source=source_xml(),
                           baseline_xml=source_xml(extra=False),
                           base=deepcopy(EVIDENCE["baseline_layout"]),
                           loaded=deepcopy(EVIDENCE["demonstration_layout"]))
    bind_source(case, monkeypatch)
    return case


def bind_source(case, monkeypatch):
    with h5py.File(case.config["hdf5_path"], "a") as source:
        for i in range(50):
            source[f"data/demo_{i}"].attrs["model_file"] = getattr(case, "source_variants", [case.source])[i % len(getattr(case, "source_variants", [case.source]))]
    case.config["expected_assets"] = {name: sha(Path(case.config[key]).read_bytes())
                                      for key, name in ASSET_KEYS.items()}
    # The production source pin has no public permissive switch. Only the tiny
    # local fixture's known bytes are substituted in this unit-test process.
    monkeypatch.setattr(module, "KNOWN_ASSETS", deepcopy(case.config["expected_assets"]))
    monkeypatch.setattr(module, "KNOWN_LINK7_ASSET_SHA256", sha(case.target.read_bytes()))
    case.scan = scan_xml_assets(
        [{"trajectory_id": f"demo_{i}", "model_xml": getattr(case, "source_variants", [case.source])[i % len(getattr(case, "source_variants", [case.source]))]} for i in sorted(range(50), key=lambda value: f"demo_{value}")],
        roots=case.roots)
    case.processed, report = resolve_xml(case.source, roots=case.roots)
    assert report["status"] == "resolved"
    case.model = ReplayModel(case.loaded, case.processed)


def validate(case, **overrides):
    arguments = {"source_xml": case.source, "processed_xml": case.processed,
                 "compiled_model": case.model, "config": case.config, "asset_scan": case.scan,
                 "baseline_compiled_xml": case.baseline_xml}
    arguments.update(overrides)
    return module.validate_demo_model(case.base, case.loaded, **arguments)


@pytest.fixture
def case(tmp_path, monkeypatch):
    return make_case(tmp_path, monkeypatch)


def test_actual_layout_exact_path_does_not_require_variant_authorization(case):
    case.loaded = deepcopy(case.base)
    case.model = ReplayModel(case.loaded, "<mujoco/>")
    evidence = validate(case, source_xml="<mujoco/>", processed_xml="<mujoco/>",
                        config={}, asset_scan=None)
    assert evidence["classification"] == "exact"
    assert evidence["baseline_layout_sha256"] == evidence["loaded_layout_sha256"]
    assert not evidence["layout_diff"]


def test_actual_161_to_162_layout_preserves_all_seven_anonymous_entries_and_inputs(case):
    before = deepcopy((case.base, case.loaded, case.config, case.scan, case.source))
    evidence = validate(case)
    assert evidence["classification"] == "known_basket_link7_collision"
    assert evidence["physically_equivalent_to_evaluation"] is False
    assert evidence["baseline_layout_sha256"] != evidence["loaded_layout_sha256"]
    assert case.base["ngeom"] == 161 and case.loaded["ngeom"] == 162
    assert case.base["geom_names"].count(None) == case.loaded["geom_names"].count(None) == 7
    assert (case.base, case.loaded, case.config, case.scan, case.source) == before
    assert evidence["source_xml_sha256"] == sha(case.source.encode())
    assert evidence["processed_xml_sha256"] == sha(case.processed.encode())
    assert evidence["compiled_xml_sha256"] == sha(case.model.get_xml().encode())
    assert evidence["source_binding"] and evidence["extra_geom"] and evidence["rule_version"]
    assert EXTRA in json.dumps(evidence["extra_geom"])


def reject(case, field=None, **overrides):
    with pytest.raises(module.DemoModelCompatibilityError) as captured:
        validate(case, **overrides)
    evidence = captured.value.evidence
    assert evidence["classification"] == "rejected" and evidence["error"]
    assert evidence["source_xml_sha256"] == sha(overrides.get("source_xml", case.source).encode())
    if field is not None:
        assert field in json.dumps(evidence["layout_diff"])
        assert evidence["layout_diff"]
    return evidence


@pytest.mark.parametrize("field", [
    "nq", "nv", "nu", "nbody", "nsite", "njnt",
    "joint_names", "jnt_type", "jnt_qposadr", "jnt_dofadr",
    "body_names", "body_parentid", "site_names", "site_bodyid",
    "actuator_names", "actuator_trnid", "actuator_trntype",
])
def test_every_non_geometry_layout_and_address_semantic_remains_strict(case, field):
    value = case.loaded[field]
    if isinstance(value, list):
        if isinstance(value[0], list):
            value[0][0] += 1
        elif isinstance(value[0], str):
            value[0] += "_changed"
        else:
            value[0] += 1
    else:
        case.loaded[field] += 1
    reject(case, field)


@pytest.mark.parametrize("field", ["joint_names", "jnt_type", "jnt_qposadr", "jnt_dofadr"])
def test_equal_joint_counts_do_not_authorize_reordered_semantics(case, field):
    values = case.loaded[field]
    left, right = (0, 7) if field == "jnt_type" else (0, 1)
    values[left], values[right] = values[right], values[left]
    reject(case, field)


@pytest.mark.parametrize("change", [
    "unknown_extra", "two_extras", "duplicate_permitted_name", "wrong_body",
    "target_missing", "gripper_missing", "anonymous_count", "anonymous_order", "anonymous_parent",
])
def test_geometry_sequence_cannot_drop_merge_or_relabel_entries(case, change):
    names, bodies = case.loaded["geom_names"], case.loaded["geom_bodyid"]
    extra = names.index(EXTRA)
    if change == "unknown_extra":
        names[extra] = "other_collision"
    elif change in {"two_extras", "duplicate_permitted_name"}:
        names.insert(extra, EXTRA if change == "duplicate_permitted_name" else "unknown")
        bodies.insert(extra, bodies[extra])
        case.loaded["ngeom"] += 1
    elif change == "wrong_body":
        bodies[extra] = case.loaded["body_names"].index("gripper0_right_gripper")
    elif change in {"target_missing", "gripper_missing"}:
        victim = "alphabet_soup_1_g0" if change == "target_missing" else "gripper0_finger1_pad_collision"
        names[names.index(victim)] = "renamed_same_count"
    elif change == "anonymous_count":
        names[names.index(None)] = "invented_anonymous_name"
    elif change == "anonymous_order":
        left, right = names.index(None), names.index("floor")
        names[left], names[right] = names[right], names[left]
        bodies[left], bodies[right] = bodies[right], bodies[left]
    else:
        bodies[names.index(None)] += 1
    evidence = reject(case)
    assert "geom" in json.dumps(evidence["layout_diff"])


@pytest.mark.parametrize("change", ["mesh", "type", "rgba"])
def test_compiled_extra_geometry_is_checked_beyond_its_permitted_name(case, change):
    index = case.loaded["geom_names"].index(EXTRA)
    if change == "mesh":
        case.model.mesh_name = "wrong_mesh"
    elif change == "type":
        case.model.geom_type[index] = 6
    else:
        case.model.geom_rgba[index] = [1., 0., 0., 1.]
    reject(case)


@pytest.mark.parametrize("change", ["wrong_body", "wrong_mesh", "two_geoms", "wrong_type"])
def test_source_xml_permitted_name_cannot_disguise_another_geometry(case, monkeypatch, change):
    tree = ET.fromstring(case.source)
    body = tree.find("./worldbody/body")
    geom = body.find("geom")
    if change == "wrong_body":
        body.set("name", "gripper0_right_gripper")
    elif change == "wrong_mesh":
        geom.set("mesh", "robot0_other_link")
    elif change == "two_geoms":
        body.append(deepcopy(geom))
    else:
        geom.set("type", "box")
    case.source = ET.tostring(tree, encoding="unicode")
    bind_source(case, monkeypatch)
    reject(case)


@pytest.mark.parametrize("change", [
    "profile", "expected_hdf", "actual_hdf", "actual_bddl", "actual_init",
    "source_xml_not_member", "processed_xml", "scan_digest", "no_scan", "no_source_pins",
])
def test_known_variant_cannot_be_enabled_with_forged_source_or_scan_identity(case, change):
    overrides = {}
    if change == "profile":
        case.config["data_profile"]["domains"]["head_demonstration"]["groups"]["head_train"][0] = "demo_0"
    elif change == "expected_hdf":
        case.config["expected_assets"]["hdf5_sha256"] = "0" * 64
    elif change in {"actual_hdf", "actual_bddl", "actual_init"}:
        key = {"actual_hdf": "hdf5_path", "actual_bddl": "bddl_path", "actual_init": "init_states_path"}[change]
        with Path(case.config[key]).open("ab") as stream:
            stream.write(b"same-path bytes changed after identity binding")
    elif change == "source_xml_not_member":
        overrides["source_xml"] = case.source.replace("SYNTHETIC", "NOT-A-MEMBER")
    elif change == "processed_xml":
        overrides["processed_xml"] = case.processed.replace('rgba="0 0.5 0 1"', 'rgba="1 0 0 1"')
    elif change == "scan_digest":
        case.scan["scan_sha256"] = "0" * 64
    elif change == "no_scan":
        overrides["asset_scan"] = None
    else:
        case.config.pop("expected_assets")
    reject(case, **overrides)


def test_runtime_layout_extraction_preserves_none_and_order_from_actual_diagnostic(case):
    assert environment._layout(ReplayModel(case.base, "<mujoco/>")) == case.base
    assert environment._layout(case.model) == case.loaded


@pytest.mark.parametrize("change", ["position", "size", "body", "count", "order"])
def test_anonymous_compiled_geometries_preserve_attributes_and_order(case, change):
    tree = ET.fromstring(case.model.xml)
    body = tree.find("./worldbody/body[@name='living_room_table_col']")
    anonymous = list(body)
    if change in {"position", "size"}:
        anonymous[2].set("pos" if change == "position" else "size", "9 8 7")
    elif change == "body":
        body.set("name", "another_parent")
    elif change == "count":
        body.remove(anonymous[2])
    else:
        body.remove(anonymous[1])
        body.insert(3, anonymous[1])
    case.model.xml = ET.tostring(tree, encoding="unicode")
    evidence = reject(case)
    assert "anonymous" in json.dumps(evidence).lower()


def test_matching_mutations_to_both_layouts_do_not_evade_the_fixed_baseline_pin(case):
    case.base["jnt_qposadr"][0] = case.loaded["jnt_qposadr"][0] = 9
    reject(case)


def test_source_link7_asset_same_path_replacement_is_rejected(case):
    case.target.write_bytes(b"replacement mesh with same path but different bytes")
    reject(case)


def test_partial_geometry_details_cannot_be_recorded_as_verified(case):
    del case.model.geom_friction
    reject(case)


def test_nonfinite_compiled_physical_attribute_is_rejected(case):
    case.model.geom_pos[case.loaded["geom_names"].index(EXTRA), 1] = np.nan
    evidence = reject(case)
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize("wrong_tail", [False, True])
def test_nested_contact_defaults_keep_parent_tail_for_valid_short_solimp(case, monkeypatch, wrong_tail):
    tree = ET.fromstring(case.source)
    defaults = ET.Element("default")
    ET.SubElement(defaults, "geom", {"solimp": "0.8 0.9 0.002 0.6 3"})
    child = ET.SubElement(defaults, "default", {"class": "child_contact"})
    ET.SubElement(child, "geom", {"solimp": "0.7 0.85 0.003"})
    tree.insert(0, defaults)
    tree.find("./worldbody/body[@name='robot0_link7']").set("childclass", "child_contact")
    case.source = ET.tostring(tree, encoding="unicode")
    bind_source(case, monkeypatch)
    index = case.loaded["geom_names"].index(EXTRA)
    case.model.geom_solimp[index] = [.7, .85, .003, .5 if wrong_tail else .6, 2 if wrong_tail else 3]
    if wrong_tail:
        evidence = reject(case)
        assert evidence["failure_details"]["field"] == "compiled.geom_solimp"
        assert evidence["failure_details"]["expected"] == [.7, .85, .003, .6, 3.]
    else:
        evidence = validate(case)
        assert evidence["extra_geom"]["compiled"]["solimp"] == [.7, .85, .003, .6, 3.]


@pytest.mark.parametrize("camera_name", ["agentview", "robot0_eye_in_hand"])
def test_actual_policy_camera_change_is_not_covered_by_geometry_variant(case, camera_name):
    tree = ET.fromstring(case.model.xml)
    tree.find(f"./worldbody/camera[@name='{camera_name}']").set("fovy", "99")
    case.model.xml = ET.tostring(tree, encoding="unicode")
    evidence = reject(case)
    assert evidence["failure_details"]["field"] == f"compiled.camera.{camera_name}"


def test_same_mesh_basename_from_another_directory_is_not_the_bound_robot_asset(case, monkeypatch):
    other = case.roots["robosuite"] / "other/meshes/link7.stl"
    other.parent.mkdir(parents=True)
    other.write_bytes(case.target.read_bytes())
    case.source = case.source.replace(MESH_SOURCE, "/old/robosuite/models/assets/other/meshes/link7.stl")
    bind_source(case, monkeypatch)
    evidence = reject(case)
    assert evidence["failure_details"]["field"] == "source.mesh_asset"
