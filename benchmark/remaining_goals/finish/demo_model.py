"""Fail-closed support for one audited head-demonstration model variant.

This does not modify XML, model, saved state, evaluation or physical labels.
The extra collision mesh is retained and is not claimed physically equivalent.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from .data_profiles import ASSET_KEYS, canonical_hash, validate_domain_config
from .xml_assets import resolve_scanned_xml, validate_scan

RULE_VERSION = "basket-hdf-link7-collision-insertion-v1"
KNOWN_ASSETS = {
    "hdf5_sha256": "3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af",
    "init_states_sha256": "1899fe54c51e24a41d5f9e32254730d6777f4894ab68e0e873f1fa7ae2062030",
    "bddl_sha256": "2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618",
}
KNOWN_BASELINE_LAYOUT_SHA256 = "7f5be5380352eed675813b5cb8692920c15a8e3dffea11c3281f00a919ab0e5e"
KNOWN_LINK7_ASSET_SHA256 = "92ac6afcf7574c034d3170d8a68e95ac9048ab9d0dd5bbd8311b86e551b9ab1c"
EXTRA_NAME, EXTRA_BODY, EXTRA_MESH = "robot0_link7_collision", "robot0_link7", "robot0_link7"
EXTRA_INDEX = 73
MESH_SUFFIX = "robots/panda/meshes/link7.stl"
# These are MuJoCo's default geom contact parameters, overridden by the actual
# XML main/named defaults before comparison. Mesh transforms are not defaults:
# compilation may recenter/rotate mesh geometry, so pos/quat/size are recorded.
_CONTACT_DEFAULTS = {
    "contype": "1", "conaffinity": "1", "condim": "3", "group": "0",
    "friction": "1 0.005 0.0001", "solref": "0.02 1", "solimp": "0.9 0.95 0.001 0.5 2",
    "margin": "0", "gap": "0", "rgba": "0.5 0.5 0.5 1",
}
_ARRAY_WIDTHS = {"rgba": 4, "pos": 3, "quat": 4, "size": 3, "friction": 3, "solref": 2, "solimp": 5}
_INTEGER_FIELDS = ("contype", "conaffinity", "condim", "group")


class DemoModelCompatibilityError(ValueError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = deepcopy(evidence)


class _Mismatch(ValueError):
    def __init__(self, field, expected, actual):
        super().__init__(f"model compatibility mismatch: {field}")
        self.details = {"field": field, "expected": deepcopy(expected), "actual": deepcopy(actual)}


def _check(condition, field, expected, actual):
    if not condition:
        raise _Mismatch(field, expected, actual)


def _sha(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if not isinstance(text, str):
        raise ValueError("XML identity requires text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def layout_diff(baseline, loaded):
    """Whole ordered values preserve anonymous entries and repeated identities."""
    return {key: {"baseline": deepcopy(baseline.get(key)), "loaded": deepcopy(loaded.get(key)),
                  "baseline_present": key in baseline, "loaded_present": key in loaded}
            for key in sorted(set(baseline) | set(loaded))
            if key not in baseline or key not in loaded or canonical_hash(baseline[key]) != canonical_hash(loaded[key])}


def _xml_records(text, tag, *, anonymous=False, name=None):
    root = ET.fromstring(text)
    records = []
    def visit(element, bodies):
        next_bodies = bodies + [element.get("name")] if element.tag == "body" else bodies
        if element.tag == tag and (not anonymous or element.get("name") is None) and (name is None or element.get("name") == name):
            records.append({"body_path": list(bodies), "attributes": dict(element.attrib)})
        for child in element:
            visit(child, next_bodies)
    world = root.find("worldbody")
    if world is not None:
        visit(world, [])
    return records


def _bind_source(config, scan, source_xml, processed_xml):
    profile = validate_domain_config(config)
    if config.get("expected_assets") != KNOWN_ASSETS:
        raise ValueError("known model variant requires the fixed official basket asset identity")
    actual = {}
    for key, digest_key in ASSET_KEYS.items():
        actual[digest_key] = _file_hash(config[key])
        _check(actual[digest_key] == KNOWN_ASSETS[digest_key], key + ".sha256", KNOWN_ASSETS[digest_key], actual[digest_key])
    import h5py
    trajectories = []
    with h5py.File(config["hdf5_path"], "r") as source:
        group = source["data"]
        if set(group) != {f"demo_{index}" for index in range(50)}:
            raise ValueError("known model variant requires all 50 actual HDF trajectories")
        for name in sorted(group):
            if not isinstance(group[name], h5py.Group) or "states" not in group[name]:
                raise ValueError("actual HDF member is not a saved-state trajectory")
            text = group[name].attrs.get("model_file", group.attrs.get("model_file"))
            if isinstance(text, bytes):
                text = text.decode("utf-8")
            if not isinstance(text, str):
                raise ValueError("actual HDF trajectory has no original XML")
            trajectories.append({"trajectory_id": name, "model_xml": text})
    members = [row["trajectory_id"] for row in trajectories if row["model_xml"] == source_xml]
    if not members:
        raise ValueError("source XML is not a byte-exact member of the approved actual HDF")
    validate_scan(scan, trajectories=trajectories, verify_files=True)
    expected_processed, _ = resolve_scanned_xml(source_xml, scan)
    if processed_xml != expected_processed:
        raise ValueError("processed XML differs from the approved resource-only transformation")
    return {"assets": actual, "profile_sha256": canonical_hash(profile), "asset_scan_sha256": scan["scan_sha256"],
            "source_trajectory_ids": members, "actual_hdf_xml_count": len(trajectories),
            "source_xml_sha256": _sha(source_xml), "scope": "fixed_official_basket_head_demonstrations"}


def _merge_geom_defaults(inherited, declared):
    attrs = dict(inherited)
    for key, value in declared.items():
        if key in _CONTACT_DEFAULTS and key in _ARRAY_WIDTHS:
            prefix, prior = value.split(), attrs[key].split()
            if not 1 <= len(prefix) <= _ARRAY_WIDTHS[key] or len(prior) != _ARRAY_WIDTHS[key]:
                raise ValueError(f"invalid source geom default width: {key}")
            value = " ".join(prefix + prior[len(prefix):])
        attrs[key] = value
    return attrs


def _effective_geom(root, target):
    defaults = {"main": dict(_CONTACT_DEFAULTS)}
    def walk_default(element, inherited):
        attrs = dict(inherited)
        for geom in element.findall("geom"):
            attrs = _merge_geom_defaults(attrs, geom.attrib)
        key = element.get("class", "main")
        if key in defaults and key != "main":
            raise ValueError("duplicate geom default class")
        defaults[key] = attrs
        for child in element.findall("default"):
            walk_default(child, attrs)
    for default in root.findall("default"):
        walk_default(default, _CONTACT_DEFAULTS)
    found = []
    def walk(element, current_class):
        current_class = element.get("childclass", current_class) if element.tag == "body" else current_class
        if element is target:
            class_name = element.get("class", current_class)
            if class_name not in defaults:
                raise ValueError("unknown source geom default class")
            found.append(_merge_geom_defaults(defaults[class_name], element.attrib))
        for child in element:
            walk(child, current_class)
    walk(root, "main")
    if len(found) != 1:
        raise ValueError("source geom default resolution is ambiguous")
    return found[0]


def _extra_evidence(source_xml, compiled_xml, model, scan, baseline_compiled_xml):
    root = ET.fromstring(source_xml)
    geoms = [item for item in root.iter("geom") if item.get("name") == EXTRA_NAME]
    records = _xml_records(source_xml, "geom", name=EXTRA_NAME)
    expected = {"name": EXTRA_NAME, "type": "mesh", "rgba": "0 0.5 0 1", "mesh": EXTRA_MESH}
    if len(geoms) != 1 or len(records) != 1 or records[0]["attributes"] != expected or records[0]["body_path"][-1:] != [EXTRA_BODY]:
        raise _Mismatch("source.extra_geom", {"attributes": expected, "parent_body": EXTRA_BODY}, records)
    meshes = [item for item in root.findall("./asset/mesh") if item.get("name") == EXTRA_MESH]
    if len(meshes) != 1 or not meshes[0].get("file"):
        raise ValueError("source mesh identity is missing or ambiguous")
    matching = [row for row in scan["sources"] if row["original_xml"] == source_xml]
    mappings = [entry for entry in matching[0]["mappings"] if entry["tag"] == "mesh" and entry["original"] == meshes[0].get("file")]
    if (len(mappings) != 1 or mappings[0]["root"] != "robosuite" or mappings[0]["relative_suffix"] != MESH_SUFFIX
            or mappings[0]["target_sha256"] != KNOWN_LINK7_ASSET_SHA256):
        raise _Mismatch("source.mesh_asset", {"root": "robosuite", "relative_suffix": MESH_SUFFIX, "target_sha256": KNOWN_LINK7_ASSET_SHA256}, mappings)
    index = int(model.geom_name2id(EXTRA_NAME))
    body_id, mesh_id = int(model.geom_bodyid[index]), int(model.geom_dataid[index])
    if (index != EXTRA_INDEX or int(model.geom_type[index]) != 7 or mesh_id < 0
            or model.body_id2name(body_id) != EXTRA_BODY or model.mesh_id2name(mesh_id) != EXTRA_MESH):
        raise _Mismatch("compiled.extra_geom", {"index": EXTRA_INDEX, "type": 7, "body": EXTRA_BODY, "mesh": EXTRA_MESH},
            {"index": index, "type": int(model.geom_type[index]), "body_id": body_id,
             "body": model.body_id2name(body_id), "mesh_id": mesh_id,
             "mesh": model.mesh_id2name(mesh_id) if mesh_id >= 0 else None})
    native = {"index": index, "body_id": body_id, "body": model.body_id2name(body_id), "type": int(model.geom_type[index]),
              "mesh_id": mesh_id, "mesh": model.mesh_id2name(mesh_id)}
    effective = _effective_geom(root, geoms[0])
    for field in (*_ARRAY_WIDTHS, *_INTEGER_FIELDS, "margin", "gap"):
        value = np.asarray(getattr(model, "geom_" + field)[index])
        expected_shape = (_ARRAY_WIDTHS[field],) if field in _ARRAY_WIDTHS else ()
        if value.shape != expected_shape or value.dtype.kind not in "iuf" or not np.isfinite(value).all():
            raise ValueError(f"compiled geom_{field} is not a finite complete value")
        native[field] = value.tolist()
        if field in _CONTACT_DEFAULTS:
            declared = np.asarray([float(item) for item in effective[field].split()], dtype=value.dtype)
            declared = declared.reshape(expected_shape)
            if not np.isfinite(declared).all():
                raise ValueError(f"source geom_{field} is non-finite")
            if not np.array_equal(value, declared):
                raise _Mismatch("compiled.geom_" + field, declared.tolist(), value.tolist())
    if not isinstance(baseline_compiled_xml, str):
        raise ValueError("known variant requires the actual baseline compiled XML evidence")
    anonymous_before = _xml_records(baseline_compiled_xml, "geom", anonymous=True)
    anonymous_after = _xml_records(compiled_xml, "geom", anonymous=True)
    if len(anonymous_before) != 7 or anonymous_before != anonymous_after:
        raise _Mismatch("compiled.anonymous_geoms", anonymous_before, anonymous_after)
    cameras = {}
    for name in ("agentview", "robot0_eye_in_hand"):
        before = _xml_records(baseline_compiled_xml, "camera", name=name)
        after = _xml_records(compiled_xml, "camera", name=name)
        if len(before) != 1 or before != after:
            raise _Mismatch("compiled.camera." + name, before, after)
        cameras[name] = after[0]
    return {"source": records[0], "mesh_asset": deepcopy(mappings[0]), "source_mesh": dict(meshes[0].attrib),
            "compiled": native, "source_effective_contact_attributes": {key: effective[key] for key in _CONTACT_DEFAULTS},
            "anonymous_geometry_count": len(anonymous_after), "anonymous_geometry_sha256": canonical_hash(anonymous_after),
            "selected_cameras": cameras,
            "limitation": "Retained real collision geometry can affect contact, observations and K4; physical equivalence to evaluation is unproven."}


def validate_demo_model(baseline_layout, loaded_layout, *, source_xml, processed_xml, compiled_model,
                        config, asset_scan, baseline_compiled_xml=None):
    """Validate exact layout or the one source-bound insertion, without mutation."""
    compiled_xml = compiled_model.get_xml()
    if isinstance(compiled_xml, bytes):
        compiled_xml = compiled_xml.decode("utf-8")
    evidence = {"rule_version": RULE_VERSION, "classification": "rejected", "scope": "head_demonstration_only",
        "source_xml_sha256": _sha(source_xml) if source_xml is not None else None,
        "processed_xml_sha256": _sha(processed_xml), "compiled_xml_sha256": _sha(compiled_xml),
        "baseline_compiled_xml_sha256": _sha(baseline_compiled_xml) if baseline_compiled_xml is not None else None,
        "baseline_layout_sha256": canonical_hash(baseline_layout), "loaded_layout_sha256": canonical_hash(loaded_layout),
        "layout_diff": layout_diff(baseline_layout, loaded_layout), "source_binding": None, "extra_geom": None,
        "physically_equivalent_to_evaluation": False}
    try:
        if not evidence["layout_diff"]:
            evidence["classification"] = "exact"
            return evidence
        if evidence["baseline_layout_sha256"] != KNOWN_BASELINE_LAYOUT_SHA256:
            raise ValueError("baseline layout is not the diagnosed basket model")
        names = loaded_layout.get("geom_names", [])
        if (names.count(EXTRA_NAME) != 1 or EXTRA_NAME in baseline_layout["geom_names"]
                or len(names) <= EXTRA_INDEX or names[EXTRA_INDEX] != EXTRA_NAME):
            raise ValueError("expected exactly one link7 collision insertion at diagnosed index 73")
        filtered = deepcopy(loaded_layout)
        filtered["ngeom"] -= 1
        for key in ("geom_names", "geom_bodyid"):
            del filtered[key][EXTRA_INDEX]
        residual = layout_diff(baseline_layout, filtered)
        evidence["filtered_layout_diff"] = residual
        if residual:
            raise ValueError("layout differs beyond the one diagnosed collision insertion")
        body = loaded_layout["geom_bodyid"][EXTRA_INDEX]
        if (type(body) is not int or not 0 <= body < len(loaded_layout["body_names"])
                or loaded_layout["body_names"][body] != EXTRA_BODY):
            raise ValueError("inserted collision has another body assignment")
        evidence["source_binding"] = _bind_source(config, asset_scan, source_xml, processed_xml)
        evidence["extra_geom"] = _extra_evidence(source_xml, compiled_xml, compiled_model, asset_scan, baseline_compiled_xml)
        evidence["classification"] = "known_basket_link7_collision"
        return evidence
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OSError) as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        if hasattr(error, "details"):
            evidence["failure_details"] = deepcopy(error.details)
        raise DemoModelCompatibilityError(str(error), evidence) from error
