"""CPU path-contract tests using real path strings and explicitly fake bytes.

The inventory is evidence of historical path *shape*, not a source of copied
assets. Every target here is a tiny synthetic file; its digest is deliberately
different from the recorded runtime candidate. No simulator is imported/run.
"""
from copy import deepcopy
import hashlib
from html import escape
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from benchmark.remaining_goals.finish import xml_assets as module


LEGACY = "/home/yifengz/workspace/libero-dev/chiliocosm/assets/"
INVENTORY = Path(__file__).resolve().parents[1] / (
    "docs/stage_summaries/evidence/stage04_task008_xml_assets_2026-10-15.json")


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def roots(tmp_path):
    result = {name: tmp_path / name / "assets" for name in ("libero", "robosuite")}
    for root in result.values():
        root.mkdir(parents=True)
    return result


def asset(roots, name, suffix, content=b"synthetic-test-only"):
    path = roots[name] / suffix
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def xml_for(references, *, compiler=None):
    tree = ET.Element("mujoco", {"model": "synthetic path-contract test"})
    ET.SubElement(tree, "compiler", compiler or {"angle": "radian", "meshdir": "meshes/", "autolimits": "true"})
    assets = ET.SubElement(tree, "asset")
    for index, (tag, path) in enumerate(references):
        attrs = {"name": f"resource_{index}", "file": str(path)}
        attrs.update({"scale": "0.01 0.02 0.03"} if tag == "mesh" else {"type": "2d"})
        ET.SubElement(assets, tag, attrs)
    ET.SubElement(assets, "material", {"name": "wood", "rgba": "0.1 0.2 0.3 1", "shininess": "0.5"})
    world = ET.SubElement(tree, "worldbody")
    body = ET.SubElement(world, "body", {"name": "object", "pos": "1 2 3", "quat": "1 0 0 0"})
    ET.SubElement(body, "joint", {"name": "hinge", "type": "hinge", "range": "-1 1"})
    ET.SubElement(body, "geom", {"type": "box", "size": "0.1 0.2 0.3", "mass": "2"})
    ET.SubElement(world, "camera", {"name": "agentview", "pos": "1 2 3", "quat": "1 0 0 0",
                                     "fovy": "37", "mode": "fixed"})
    return ET.tostring(tree, encoding="unicode")


def nonpath_ast(text):
    def walk(node):
        return (node.tag, sorted((key, value) for key, value in node.attrib.items() if key != "file"),
                node.text, node.tail, tuple(walk(child) for child in node))
    return walk(ET.fromstring(text))


def assert_resolved(text, roots):
    processed, report = module.resolve_xml(text, roots=roots)
    assert isinstance(processed, str) and not report["errors"]
    assert report["status"] == "resolved"
    assert report["original_xml"] == text
    assert report["original_xml_sha256"] == sha(text.encode())
    assert report["processed_xml_sha256"] == sha(processed.encode())
    assert nonpath_ast(processed) == nonpath_ast(text)
    return processed, report


def test_all_87_actual_path_strings_with_24_legacy_suffixes_use_synthetic_targets(roots):
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    entries = inventory["references"]
    assert len(entries) == inventory["unique_file_references"] == 87
    assert sum(item["original"].startswith(LEGACY) for item in entries) == 24
    targets = {}
    for index, item in enumerate(entries):
        name = "libero" if item["original"].startswith(LEGACY) else "robosuite"
        marker = "/libero/libero/assets/" if name == "libero" else "/robosuite/models/assets/"
        # Expected suffix is independently taken from the reviewed candidate.
        suffix = item["candidate"].split(marker, 1)[1]
        target = asset(roots, name, suffix, f"SYNTHETIC ONLY {index} {suffix}".encode())
        assert sha(target.read_bytes()) != item["candidate_sha256"]
        targets[item["original"]] = (name, suffix, target)
    text = xml_for([(item["tag"], item["original"]) for item in entries])
    original_bytes = text.encode()
    processed, report = assert_resolved(text, roots)
    assert text.encode() == original_bytes
    assert report["file_reference_occurrences"] == 87
    assert len(report["mappings"]) == 87
    for mapping in report["mappings"]:
        name, suffix, target = targets[mapping["original"]]
        assert mapping["root"] == name and mapping["relative_suffix"] == suffix
        assert Path(mapping["resolved"]) == target.resolve()
        assert mapping["target_sha256"] == sha(target.read_bytes())
        assert mapping["attribute"] == "file" and mapping["rule"]
    assert len({item["resolved"] for item in report["mappings"]}) == 87
    assert LEGACY not in processed


@pytest.mark.parametrize("original, root, suffix", [
    (LEGACY + "scenes/../textures/floor.png", "libero", "textures/floor.png"),
    ("/other/libero/libero/assets/textures/floor.png", "libero", "textures/floor.png"),
    ("/other/libero/assets/textures/floor.png", "libero", "textures/floor.png"),
    ("/other/robosuite/models/assets/robots/panda/hand.stl", "robosuite", "robots/panda/hand.stl"),
])
def test_declared_legacy_and_official_complete_suffixes(roots, original, root, suffix):
    expected = asset(roots, root, suffix)
    _, report = assert_resolved(xml_for([("mesh", original)]), roots)
    assert Path(report["mappings"][0]["resolved"]) == expected.resolve()


def test_same_basename_objects_never_substitute_for_one_another(roots):
    paths = ["stable_hope_objects/alphabet_soup/texture_map.png", "stable_hope_objects/tomato_sauce/texture_map.png"]
    targets = [asset(roots, "libero", path, f"distinct object {i}".encode()) for i, path in enumerate(paths)]
    _, report = assert_resolved(xml_for([("texture", LEGACY + path) for path in paths]), roots)
    assert [Path(item["resolved"]) for item in report["mappings"]] == [target.resolve() for target in targets]
    assert len({item["target_sha256"] for item in report["mappings"]}) == 2
    targets[1].unlink()
    processed, report = module.resolve_xml(xml_for([("texture", LEGACY + paths[1])]), roots=roots)
    assert processed is None and report["status"] == "unresolved"


@pytest.mark.parametrize("original", [
    LEGACY + "../outside.png",
    LEGACY + "scenes/../../outside.png",
    "/unknown/chiliocosm/assets/textures/floor.png",
    "/other/notlibero/assets/textures/floor.png",
    "/other/libero-dev/chiliocosm/assets/textures/floor.png",
])
def test_escape_unknown_roots_and_substring_aliases_are_rejected(roots, original):
    asset(roots, "libero", "textures/floor.png")
    processed, report = module.resolve_xml(xml_for([("texture", original)]), roots=roots)
    assert processed is None and report["status"] == "unresolved" and report["errors"]


def test_existing_original_path_cannot_bypass_fixed_resource_binding(roots, tmp_path):
    old = tmp_path / "old" / "libero" / "libero" / "assets" / "textures" / "floor.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"historical-path-exists-but-unapproved-bytes")
    text = xml_for([("texture", old.as_posix())])
    processed, report = module.resolve_xml(text, roots=roots)
    assert processed is None and report["errors"]
    target = asset(roots, "libero", "textures/floor.png", b"fixed-runtime-bytes")
    _, report = assert_resolved(text, roots)
    assert Path(report["mappings"][0]["resolved"]) == target.resolve()
    assert report["mappings"][0]["target_sha256"] != sha(old.read_bytes())


def test_existing_unknown_absolute_path_is_not_implicitly_approved(roots, tmp_path):
    path = tmp_path / "unknown.png"
    path.write_bytes(b"exists")
    processed, report = module.resolve_xml(xml_for([("texture", path.as_posix())]), roots=roots)
    assert processed is None and report["errors"]


def test_multiple_declared_roots_in_one_reference_are_ambiguous(roots):
    suffix = "robosuite/models/assets/shared.png"
    asset(roots, "libero", suffix, b"libero interpretation")
    asset(roots, "robosuite", "shared.png", b"robosuite interpretation")
    processed, report = module.resolve_xml(xml_for([("texture", "/old/libero/libero/assets/" + suffix)]), roots=roots)
    assert processed is None and report["status"] == "unresolved"
    assert "ambig" in json.dumps(report["errors"]).lower()


def test_resolved_symlink_escape_is_rejected_without_os_symlink_privileges(roots, tmp_path, monkeypatch):
    target = asset(roots, "libero", "textures/linked.png")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside approved assets")
    original_resolve = Path.resolve
    lexical_target = original_resolve(target)
    resolved_outside = original_resolve(outside)

    def fake_symlink_resolve(self, *args, **kwargs):
        resolved = original_resolve(self, *args, **kwargs)
        return resolved_outside if resolved == lexical_target else resolved

    monkeypatch.setattr(Path, "resolve", fake_symlink_resolve)
    processed, report = module.resolve_xml(xml_for([("texture", LEGACY + "textures/linked.png")]), roots=roots)
    assert processed is None and report["errors"]


@pytest.mark.parametrize("dependency", [
    '<include file="known.xml"/>',
    '<asset><material name="x" file="known.png"/></asset>',
    '<asset><mesh name="x" file="relative.stl"/></asset>',
    '<asset><texture name="x" file="relative.png"/></asset>',
    '<asset><texture name="x" fileleft="relative.png"/></asset>',
])
def test_unknown_file_attributes_includes_and_compiler_relative_dependencies_fail(roots, dependency):
    text = '<mujoco><compiler meshdir="meshes/" texturedir="textures/"/>' + dependency + '</mujoco>'
    processed, report = module.resolve_xml(text, roots=roots)
    assert processed is None and report["status"] == "unresolved" and report["errors"]


def test_scan_aggregates_all_source_errors_and_preserves_input(roots):
    missing_a, missing_b = LEGACY + "textures/missing_a.png", LEGACY + "textures/missing_b.png"
    unknown = "/unknown/resources/unknown.png"
    trajectories = [
        {"trajectory_id": "demo_0", "model_xml": xml_for([("texture", missing_a), ("texture", unknown)])},
        {"trajectory_id": "demo_49", "model_xml": xml_for([("texture", missing_b)])},
    ]
    before = deepcopy(trajectories)
    report = module.scan_xml_assets(trajectories, roots=roots)
    assert trajectories == before
    assert report["status"] == "unresolved" and report["trajectory_count"] == 2
    assert report["file_reference_occurrences"] == 3 and len(report["errors"]) == 3
    assert {item["trajectory_id"] for item in report["sources"]} == {"demo_0", "demo_49"}
    errors = json.dumps(report["errors"])
    assert all(path in errors for path in (missing_a, missing_b, unknown))
    with pytest.raises(ValueError):
        module.validate_scan(report, trajectories=trajectories)


def test_scan_validates_current_bytes_and_source_xml_binding(roots):
    path = asset(roots, "libero", "textures/floor.png")
    text = xml_for([("texture", LEGACY + "textures/floor.png")])
    trajectories = [{"trajectory_id": "demo_0", "model_xml": text}]
    report = module.scan_xml_assets(trajectories, roots=roots)
    assert report["status"] == "resolved" and report["resolved_reference_occurrences"] == 1
    assert report["schema_version"] == "remaining-finish-xml-assets-scan-v1"
    assert module.validate_scan(report, trajectories=trajectories) == report
    changed_xml = [{"trajectory_id": "demo_0", "model_xml": text.replace('fovy="37"', 'fovy="38"')}]
    with pytest.raises(ValueError):
        module.validate_scan(report, trajectories=changed_xml)
    path.write_bytes(b"changed at same path after scan")
    with pytest.raises(ValueError):
        module.validate_scan(report, trajectories=trajectories)


def test_bytes_outside_file_value_are_preserved_with_comments_pi_and_unicode(roots):
    suffix = "textures/纹理 & stone.png"
    target = asset(roots, "libero", suffix)
    old = escape(LEGACY + suffix, quote=True)
    text = ("<?xml version='1.0' encoding='UTF-8'?>\n"
            "<?audit original='keep this processing instruction'?>\n"
            "<mujoco model='合成测试'>\n"
            "  <!-- keep spacing and file=\"not-a-dependency.png\" -->\n"
            "  <asset><texture name=\"wood\" type='2d' file = '" + old + "' /></asset>\n"
            "  <worldbody><camera name='agentview' fovy = \"37\" pos='1 2 3'/></worldbody>\n"
            "</mujoco>\n")
    processed, _ = assert_resolved(text, roots)
    expected = text.replace(old, escape(target.resolve().as_posix(), quote=True))
    assert processed.encode("utf-8") == expected.encode("utf-8")


def test_runtime_processing_and_scan_share_the_same_resolver(roots, monkeypatch):
    from benchmark.remaining_goals.finish import environment
    asset(roots, "libero", "textures/floor.png")
    text = xml_for([("texture", LEGACY + "textures/floor.png")])
    expected, _ = assert_resolved(text, roots)
    seen = []
    original = module._resolve

    def traced(value, *args, **kwargs):
        seen.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(module, "_resolve", traced)
    scan = module.scan_xml_assets([{"trajectory_id": "demo_0", "model_xml": text}], roots=roots)
    assert text in seen
    seen.clear()
    actual = environment._processed_demo_xml(text, roots=roots, expected_scan=scan)
    assert actual == expected and text in seen
    assert nonpath_ast(actual) == nonpath_ast(text)


@pytest.mark.parametrize("change", ["target_bytes", "source_camera"])
def test_runtime_refuses_xml_or_target_changed_after_scan(roots, change):
    from benchmark.remaining_goals.finish import environment
    path = asset(roots, "libero", "textures/floor.png")
    text = xml_for([("texture", LEGACY + "textures/floor.png")])
    scan = module.scan_xml_assets([{"trajectory_id": "demo_0", "model_xml": text}], roots=roots)
    if change == "target_bytes":
        path.write_bytes(b"same path replaced after preflight")
    else:
        text = text.replace('fovy="37"', 'fovy="38"')
    with pytest.raises((ValueError, RuntimeError)):
        environment._processed_demo_xml(text, roots=roots, expected_scan=scan)


def test_discovery_does_not_execute_package_initializers(tmp_path, monkeypatch):
    for package in ("libero", "libero/libero", "robosuite", "robosuite/models"):
        path = tmp_path / package
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").write_text('raise RuntimeError("package import is forbidden in CPU discovery")\n', encoding="utf-8")
    libero, robosuite = tmp_path / "libero/libero/assets", tmp_path / "robosuite/models/assets"
    libero.mkdir()
    robosuite.mkdir()
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    before = {name for name in sys.modules if name.startswith(("libero", "robosuite"))}
    result = module.discover_asset_roots()
    assert {name: Path(path) for name, path in result.items()} == {"libero": libero.resolve(), "robosuite": robosuite.resolve()}
    assert {name for name in sys.modules if name.startswith(("libero", "robosuite"))} == before


def test_no_reference_xml_does_not_discover_or_import_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dependency-free synthetic XML must not discover a runtime")
    monkeypatch.setattr(module, "discover_asset_roots", forbidden)
    text = '<mujoco><worldbody><camera name="agentview" fovy="39"/></worldbody></mujoco>'
    processed, report = module.resolve_xml(text)
    assert processed == text and report["file_reference_occurrences"] == 0 and not report["errors"]
