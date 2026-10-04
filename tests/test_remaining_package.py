"""Delivery integrity tests use a tiny fake repo; no network or simulator."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from benchmark.remaining_goals import package_audit as package
from benchmark.remaining_goals import replay_candidates as replay
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.observation_artifact import load_observation_artifact, save_observation_artifact
from benchmark.remaining_goals.validation import compare_observations, RGB_QUANTIZATION_AUDIT
from tests.test_remaining_replay_candidates import pack, write_json


PROJECT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6rZEAAAAASUVORK5CYII=")


@pytest.fixture
def delivery(pack, tmp_path):
    manifest_path, replay_directory, manifest, record = pack
    root = tmp_path
    for relative in ("benchmark/__init__.py", "benchmark/remaining_goals/__init__.py",
                     "benchmark/remaining_goals/package_audit.py", "scripts/package_remaining_benchmark.py"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / relative, destination)
    # Check the transitive import / package-initializer closure independently of
    # the full project's evolving builder and adapters.
    (root / "benchmark/remaining_goals/example.py").write_text("from benchmark.example import helper\n")
    (root / "benchmark/example").mkdir()
    (root / "benchmark/example/__init__.py").write_text("from .helper import value\n")
    (root / "benchmark/example/helper.py").write_text("value = 3\n")
    (root / "scripts/check_remaining_baseline_config.py").write_text("VALUE = 'template validator, not an adapter'\n")
    (root / "configs/remaining_goals").mkdir(parents=True)
    write_json(root / "configs/remaining_goals/model_template.json", {"adapter_ready": False})
    (root / "docs").mkdir()
    private_path = "C:" + "/Users/" + "alice/private/python.exe"
    (root / "docs/remaining_goals_benchmark.md").write_text(private_path, encoding="utf-8")
    for episode in manifest["episodes"]:
        (manifest_path.parent / episode["construction"]["technical_audit"]).with_name("start.png").write_bytes(PNG)
    write_json(manifest_path.parent / "construction_report.json", {
        "kind": "real_libero_candidate_construction", "toy": False,
        "environment": manifest["environment"], "candidate_episodes": 4, "complete_groups": 1,
    })
    replay.replay(manifest_path, replay_directory, steps=2, repeats=2)
    commit = "a" * 40
    (root / "scripts/setup_remaining_libero.py").write_text(f"COMMIT = {commit!r}\n")
    runtime = root / ".runtime/remaining_libero"
    source = runtime / f"LIBERO-{commit}"
    bodies = {"LICENSE": b"MIT test fixture, not a project license\n", "setup.py": b"# official setup\n",
              "libero/libero/envs/tiny.py": b"# pinned upstream\n", "libero/libero/assets/background.png": PNG}
    entries = []
    for relative, body in bodies.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        entries.append({"path": relative, "type": "blob", "size": len(body),
                        "sha": hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()})
    write_json(runtime / "upstream_tree.json", {"sha": commit, "truncated": False, "tree": entries})
    write_json(runtime / "source_tree.json", {"commit": commit, "profile": {"name": "fixture"}, "entries": entries})
    write_json(runtime / "runtime.json", {"libero_commit": commit, "python": private_path,
               "parent_python": private_path, "libero_config_path": private_path, "requirements": ["numpy==1.26.4"]})
    # These deliberately exist but are outside the selected source/evidence scope.
    (runtime / "venv").mkdir()
    (runtime / "venv/private.pth").write_text("not included")
    (root / "unrelated_history.txt").write_text("not included")
    write_json(root / "reports/remaining_goals_runtime_packages_20261003.json", [{"name": "numpy", "version": "1.26.4"}])
    output = root / "delivery.zip"
    return root, manifest_path, replay_directory / "replay_report.json", output


def create(delivery, **kwargs):
    root, manifest, replay_path, output = delivery
    return package.create_bundle(root, manifest, replay_path, output, **kwargs)


def second_track(delivery, *, suite="libero_90", fingerprint=None):
    root, first_manifest, first_replay, _ = delivery
    destination = root / "source90"
    replay_destination = root / "replay90"
    shutil.copytree(first_manifest.parent, destination)
    shutil.copytree(first_replay.parent, replay_destination)
    path = destination / first_manifest.name
    manifest = json.loads(path.read_text())
    for episode in manifest["episodes"]:
        episode["suite"] = suite
    if fingerprint:
        manifest["environment"]["fingerprint"] = fingerprint
    manifest["content_hash"] = manifest_hash(manifest)
    write_json(path, manifest)
    construction_path = destination / "construction_report.json"
    construction = json.loads(construction_path.read_text())
    construction["environment"] = manifest["environment"]
    write_json(construction_path, construction)
    replay_path = replay_destination / first_replay.name
    report = json.loads(replay_path.read_text())
    report["source_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    report["source_content_hash"] = manifest["content_hash"]
    write_json(replay_path, report)
    return path, replay_path


def rewrite_zip(path, mutate):
    with zipfile.ZipFile(path) as archive:
        bodies = {name: archive.read(name) for name in archive.namelist()}
    mutate(bodies)
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in bodies.items():
            archive.writestr(name, body)


def test_candidate_bundle_is_complete_scoped_private_path_free_and_source_unchanged(delivery):
    root, manifest, _, output = delivery
    before = manifest.read_bytes()
    result = create(delivery)
    assert result["valid"] and result["coverage"] == {"episodes": 4, "groups": 1, "tasks": 1}
    assert result["replay"]["technical_acceptance"] is True
    assert result["release_authorized"] is False
    assert manifest.read_bytes() == before
    with zipfile.ZipFile(output) as archive:
        index = json.loads(archive.read(package.INDEX))
        names = archive.namelist()
        assert "benchmark/example/helper.py" in names
        assert "configs/remaining_goals/model_template.json" in names
        assert "scripts/check_remaining_baseline_config.py" in names
        assert "reports/remaining_goals_runtime_packages_20261003.json" in names
        assert not any("venv" in name or "unrelated_history" in name for name in names)
        assert not any(name.endswith("/runtime.json") for name in names)
        assert any(name.endswith("/assets/background.png") for name in names)
        assert archive.read(manifest.relative_to(root).as_posix()) == before
        doc = next(row for row in index["files"] if row["path"] == "docs/remaining_goals_benchmark.md")
        assert doc["transformation"] == "local_path_redaction_and_relativization"
        assert doc["source_sha256"] == hashlib.sha256((root / doc["path"]).read_bytes()).hexdigest()
        assert b"alice" not in archive.read("docs/remaining_goals_benchmark.md")
        assert b"alice" not in archive.read("provenance/libero_runtime.json")
        assert all(e["construction"]["legal"] is False for e in json.loads(archive.read(index["candidate_manifest"]))["episodes"])
        assert {"reviewed_release", "vla_experiments", "project_license"} <= {gap["id"] for gap in result["research_release_gaps"]}


def test_optional_upstream_omission_keeps_checksum_inventory_and_downloader(delivery):
    create(delivery, include_upstream=False)
    with zipfile.ZipFile(delivery[3]) as archive:
        assert not any("/assets/background.png" in name for name in archive.namelist())
        inventory = json.loads(archive.read("provenance/libero_runtime.json"))
        assert inventory["assets_included"] is False
        assert len(inventory["installed_files"]) == 4
        assert "scripts/setup_remaining_libero.py" in archive.namelist()


def test_manifest_and_source_bytes_are_preserved_including_utf8_bom(delivery):
    root, manifest, replay_path, output = delivery
    manifest.write_bytes(b"\xef\xbb\xbf" + manifest.read_bytes())
    helper = root / "benchmark/example/helper.py"
    helper.write_bytes(b"\xef\xbb\xbf" + helper.read_bytes())
    report = json.loads(replay_path.read_text())
    report["source_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    write_json(replay_path, report)
    create(delivery)
    with zipfile.ZipFile(output) as archive:
        assert archive.read(manifest.relative_to(root).as_posix()) == manifest.read_bytes()
        assert archive.read("benchmark/example/helper.py") == helper.read_bytes()


@pytest.mark.parametrize("fault", ["change", "missing", "extra", "index"])
def test_verify_rejects_corruption_missing_and_unlisted_files(delivery, fault):
    create(delivery)
    def mutate(bodies):
        target = "benchmark/example/helper.py"
        if fault == "change":
            bodies[target] = b"value = 4\n"
        elif fault == "missing":
            bodies.pop(target)
        elif fault == "extra":
            bodies["unlisted.txt"] = b"unlisted"
        else:
            index = json.loads(bodies[package.INDEX])
            index["release_authorized"] = True
            bodies[package.INDEX] = json.dumps(index).encode()
    rewrite_zip(delivery[3], mutate)
    with pytest.raises(ValueError):
        package.verify_bundle(delivery[3])


@pytest.mark.parametrize("bad_name", ["../outside", "/absolute", "C:/absolute", "a\\b", "a/../b", "CON.txt", "file:stream"])
def test_verify_rejects_unsafe_zip_names_without_extracting(tmp_path, bad_name):
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(bad_name, b"bad")
    with pytest.raises(ValueError):
        package.verify_bundle(archive_path)
    assert not (tmp_path / "outside").exists()


def test_verify_rejects_symlinks(delivery):
    create(delivery)
    with zipfile.ZipFile(delivery[3], "a") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"target")
    with pytest.raises(ValueError, match="symlink"):
        package.verify_bundle(delivery[3])


def test_verify_rejects_case_collisions(delivery):
    create(delivery)
    with zipfile.ZipFile(delivery[3], "a") as archive:
        archive.writestr("DELIVERY_readme.md", b"collision")
    with pytest.raises(ValueError, match="duplicate"):
        package.verify_bundle(delivery[3])


def test_cannot_overwrite_existing_bundle(delivery):
    create(delivery)
    before = delivery[3].read_bytes()
    with pytest.raises(FileExistsError):
        create(delivery)
    assert delivery[3].read_bytes() == before


def test_wrong_replay_or_missing_visual_frame_fails(delivery):
    root, manifest, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    report["source_content_hash"] = "0" * 64
    write_json(replay_path, report)
    with pytest.raises(ValueError, match="matching"):
        create(delivery)
    report["source_content_hash"] = json.loads(manifest.read_text())["content_hash"]
    write_json(replay_path, report)
    (root / "source/validation/episode_0/start.png").unlink()
    with pytest.raises(ValueError, match="visual review"):
        create(delivery)


def test_source_and_upstream_mutations_are_detected(delivery):
    root, manifest, _, _ = delivery
    report_path = manifest.parent / "construction_report.json"
    report = json.loads(report_path.read_text())
    report["builder_sources_sha256"] = {"construction.py": "0" * 64}
    (root / "benchmark/remaining_goals/construction.py").write_text("# changed\n")
    write_json(report_path, report)
    with pytest.raises(ValueError, match="frozen construction"):
        create(delivery)
    report.pop("builder_sources_sha256")
    write_json(report_path, report)
    next((root / ".runtime/remaining_libero").glob("LIBERO-*/libero/libero/assets/background.png")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="modified pinned upstream"):
        create(delivery)


def test_partial_failed_replay_is_preserved_not_promoted(delivery):
    _, _, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    report["episodes"] = report["episodes"][:1]
    report["technical_acceptance"] = False
    write_json(replay_path, report)
    result = create(delivery)
    assert result["replay"]["complete"] is False
    assert result["replay"]["technical_acceptance"] is False
    assert result["release_authorized"] is False


def test_false_aggregate_pass_rejected(delivery):
    _, _, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    report["episodes"] = report["episodes"][:1]
    write_json(replay_path, report)
    with pytest.raises(ValueError, match="aggregate acceptance"):
        create(delivery)


def test_passing_replay_cannot_point_to_a_different_state(delivery):
    _, _, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    audit["trace"][0]["state"][1] += .001
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="not bound"):
        create(delivery)


@pytest.mark.parametrize("fault", ["short_trace", "duplicate_step", "false_check", "wrong_mask"])
def test_public_replay_validator_rejects_false_pass_in_trace(delivery, fault):
    _, manifest_path, replay_path, _ = delivery
    manifest, _, states, observation_hashes = replay._candidate_pack(manifest_path)
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    if fault == "short_trace":
        audit["trace"].pop()
    elif fault == "duplicate_step":
        audit["trace"][1]["step"] = 0
    elif fault == "false_check":
        audit["trace"][1]["checks"]["predicate_mask_matches"] = False
    else:
        audit["trace"][1]["goals"] = [True, False]
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="trace window"):
        package.validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes)


def test_replay_validator_allows_consistent_bounded_dynamic_observation_diagnostics(delivery):
    _, manifest_path, replay_path, _ = delivery
    manifest, _, states, observation_hashes = replay._candidate_pack(manifest_path)
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    left = {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8), "proprio": np.zeros(1)}
    right = deepcopy(left)
    right["agentview_image"][0, 0, 0] = 1
    # Dynamic images are not stored, so check their recorded fixed bounds and
    # hashes for consistency without imposing raw hash equality.
    audit["trace"][1]["observation_check"] = compare_observations(
        left, right, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
    write_json(audit_path, audit)
    files, summary = package.validate_replay_evidence(
        manifest_path, manifest, replay_path, states, observation_hashes)
    assert audit_path in files
    assert summary["technical_acceptance"] is True


def test_replay_validator_binds_initial_returned_hash_to_saved_actual_artifact(delivery):
    _, manifest_path, replay_path, _ = delivery
    manifest, _, states, observation_hashes = replay._candidate_pack(manifest_path)
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    audit["trace"][0]["observation_check"]["returned_sha256"] = "1" * 64
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="state-bound hashes"):
        package.validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes)


def test_bounded_reset_pixels_are_recomputed_from_both_saved_artifacts_and_packaged(delivery, pack):
    root, path, _, output = delivery
    pack[3].rgb_rounding = True
    replay_dir = root / "rounded_replay"
    replay.replay(path, replay_dir, steps=2, repeats=2)
    result = package.create_bundle(root, path, replay_dir / "replay_report.json", output)
    assert result["replay"]["technical_acceptance"] is True
    report = json.loads((replay_dir / "replay_report.json").read_text())
    audit_path = replay_dir / report["episodes"][1]["audit_path"]
    audit = json.loads(audit_path.read_text())
    assert audit["reset_observation_comparison"]["bit_exact"] is False
    with zipfile.ZipFile(output) as archive:
        for episode in json.loads(path.read_text())["episodes"]:
            name = (path.parent / episode["initial_observation"]["path"]).relative_to(root).as_posix()
            assert hashlib.sha256(archive.read(name)).hexdigest() == episode["initial_observation"]["sha256"]
        for row in report["episodes"]:
            recorded = json.loads((replay_dir / row["audit_path"]).read_text())
            actual = recorded["reset_initial_observation"]
            name = (replay_dir / row["audit_path"]).parent / actual["path"]
            assert hashlib.sha256(archive.read(name.relative_to(root).as_posix())).hexdigest() == actual["sha256"]


@pytest.mark.parametrize("fault", ["missing_actual", "bad_bytes", "false_comparison", "out_of_bound_pixels", "tiny_non_rgb_change"])
def test_saved_actual_observation_cannot_be_omitted_or_used_to_forge_a_pass(delivery, fault):
    _, manifest_path, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    if fault == "missing_actual":
        audit.pop("reset_initial_observation")
    elif fault == "bad_bytes":
        actual_path = audit_path.parent / audit["reset_initial_observation"]["path"]
        actual_path.write_bytes(actual_path.read_bytes() + b"changed")
    elif fault == "false_comparison":
        audit["reset_observation_comparison"]["max_abs_error"] = 1
    else:
        actual = load_observation_artifact(audit_path.parent, audit["reset_initial_observation"])
        if fault == "out_of_bound_pixels":
            actual["agentview_image"][0, 0, 0] += 2
        else:
            actual["robot0_joint_pos"][0] += 1e-12
        reference = save_observation_artifact(audit_path.parent, "forged_actual.npz", actual)
        audit["reset_initial_observation"] = reference
        # Even if an attacker updates both raw hashes, the claimed pass cannot
        # override the actual saved two-level RGB / tiny non-RGB difference.
        audit["reset_observation_comparison"]["returned_sha256"] = reference["observation_sha256"]
        audit["trace"][0]["observation_check"]["returned_sha256"] = reference["observation_sha256"]
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="artifact|recomputed"):
        create(delivery)


def test_unselected_joint_attempt_observation_is_preserved_without_becoming_a_sample(delivery):
    root, path, _, output = delivery
    episode = json.loads(path.read_text())["episodes"][0]
    observation = load_observation_artifact(path.parent, episode["initial_observation"])
    relative = "validation/unselected_attempt/initial_observation.npz"
    reference = save_observation_artifact(path.parent, relative, observation)
    audit = json.loads((path.parent / episode["construction"]["technical_audit"]).read_text())
    audit["initial_observation"] = reference
    write_json(path.parent / "validation/unselected_attempt/audit.json", audit)
    result = create(delivery)
    assert result["coverage"]["episodes"] == 4
    with zipfile.ZipFile(output) as archive:
        assert (path.parent / relative).relative_to(root).as_posix() in archive.namelist()


@pytest.mark.parametrize("fault", ["inflate_dynamic_image_area", "change_initial_typed_digest"])
def test_trace_cannot_invent_camera_area_or_initial_non_rgb_dtype_identity(delivery, fault):
    _, _, replay_path, _ = delivery
    report = json.loads(replay_path.read_text())
    audit_path = replay_path.parent / report["episodes"][0]["audit_path"]
    audit = json.loads(audit_path.read_text())
    if fault == "inflate_dynamic_image_area":
        image = next(iter(audit["trace"][1]["observation_check"]["image_diagnostics"].values()))
        image.update(total_pixels=65536, max_changed_pixels=6)
    else:
        check = audit["trace"][0]["observation_check"]
        check["returned_non_rgb_sha256"] = check["fresh_non_rgb_sha256"] = "9" * 64
    write_json(audit_path, audit)
    with pytest.raises(ValueError, match="camera geometry|initial non-RGB digest"):
        create(delivery)


@pytest.mark.parametrize("fault", ["npz_bytes", "comparison_bounds"])
def test_offline_verifier_checks_artifact_binding_and_fixed_bounds_after_index_rehash(delivery, fault):
    create(delivery)
    def mutate(bodies):
        index = json.loads(bodies[package.INDEX])
        report_path = index["replay_report"]
        report = json.loads(bodies[report_path])
        audit_path = (Path(report_path).parent / report["episodes"][0]["audit_path"]).as_posix()
        audit = json.loads(bodies[audit_path])
        if fault == "npz_bytes":
            changed = (Path(audit_path).parent / audit["reset_initial_observation"]["path"]).as_posix()
            bodies[changed] += b"changed"
        else:
            changed = audit_path
            camera = next(iter(audit["reset_observation_comparison"]["image_diagnostics"].values()))
            camera["max_changed_pixels"] = 99
            bodies[changed] = package._json_bytes(audit)
        row = next(row for row in index["files"] if row["path"] == changed)
        row.update(size=len(bodies[changed]), sha256=hashlib.sha256(bodies[changed]).hexdigest())
        index["content_hash"] = package._manifest_hash(index)
        bodies[package.INDEX] = package._json_bytes(index)
    rewrite_zip(delivery[3], mutate)
    with pytest.raises(ValueError, match="artifact byte hash|RGB diagnostics"):
        package.verify_bundle(delivery[3])


def test_additional_evidence_redaction_is_json_valid(delivery):
    root = delivery[0]
    extra = root / "reports/doctor.json"
    private_path = "C:" + "\\Users\\" + "alice\\runtime\\python.exe"
    write_json(extra, {"python": private_path, "not_policy_benchmark": True})
    create(delivery, evidence=[extra])
    with zipfile.ZipFile(delivery[3]) as archive:
        public = json.loads(archive.read("reports/doctor.json"))
        assert public["python"] == "LOCAL_USER_HOME\\runtime\\python.exe"
        assert public["not_policy_benchmark"] is True


def test_logs_and_weights_cannot_be_added_as_extra_evidence(delivery):
    root = delivery[0]
    extra = root / "private.log"
    extra.write_text("installation details")
    with pytest.raises(ValueError, match="not logs, weights"):
        create(delivery, evidence=[extra])


def test_doctor_frames_are_included_and_report_paths_are_portable(delivery):
    root = delivery[0]
    frame = root / "reports/doctor_frames/start.png"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(PNG)
    doctor = root / "reports/doctor.json"
    write_json(doctor, {"schema_version": "remaining-libero-doctor-v1", "snapshots": [{"images": {
        "agentview_image": {"path": str(frame), "sha256": hashlib.sha256(PNG).hexdigest()}}}]})
    create(delivery, evidence=[doctor])
    with zipfile.ZipFile(delivery[3]) as archive:
        assert archive.read("reports/doctor_frames/start.png") == PNG
        report = json.loads(archive.read("reports/doctor.json"))
        relative = report["snapshots"][0]["images"]["agentview_image"]["path"].replace("\\", "/")
        assert relative == "./reports/doctor_frames/start.png"


def test_explicit_html_preview_is_included_redacted_and_linked(delivery):
    root = delivery[0]
    preview = root / "reports/preview.html"
    private_path = "C:" + "/Users/" + "alice/private"
    preview.write_text(f"<!doctype html><p>{private_path}</p><img src='data:image/png;base64,{base64.b64encode(PNG).decode()}'>", encoding="utf-8")
    create(delivery, evidence=[preview])
    with zipfile.ZipFile(delivery[3]) as archive:
        body = archive.read("reports/preview.html")
        assert b"alice" not in body and b"data:image/png;base64," in body
        assert b"[reports/preview.html](reports/preview.html)" in archive.read("DELIVERY_README.md")


def test_verify_extracted_delivery_uses_standard_library_only(delivery, tmp_path):
    create(delivery)
    extracted = tmp_path / "unpacked"
    with zipfile.ZipFile(delivery[3]) as archive:
        archive.extractall(extracted)
    result = subprocess.run([sys.executable, "-S", str(extracted / "scripts/package_remaining_benchmark.py"),
                             "verify", "--directory", str(extracted)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"] is True
    assert not list(extracted.rglob("__pycache__"))
    (extracted / "unexpected.txt").write_text("extra")
    with pytest.raises(ValueError, match="unlisted"):
        package.verify_bundle(extracted)


def test_multi_suite_collection_preserves_manifests_and_shares_upstream(delivery):
    root, first_manifest, first_replay, output = delivery
    other_manifest, other_replay = second_track(delivery)
    original = {path: path.read_bytes() for path in (first_manifest, other_manifest)}
    result = package.create_bundle(root, [first_manifest, other_manifest], [first_replay, other_replay], output)
    assert result["format"] == package.COLLECTION_FORMAT
    assert "coverage" not in result and "replay" not in result
    assert [track["suite"] for track in result["tracks"]] == ["libero_10", "libero_90"]
    assert [track["coverage"]["episodes"] for track in result["tracks"]] == [4, 4]
    assert all(track["replay"]["passed_records"] == 8 for track in result["tracks"])
    assert result["release_authorized"] is False
    with zipfile.ZipFile(output) as archive:
        assert sum(name.endswith("/assets/background.png") for name in archive.namelist()) == 1
        for path, body in original.items():
            assert archive.read(path.relative_to(root).as_posix()) == body
        index = json.loads(archive.read(package.INDEX))
        assert "coverage" not in index and "candidate_manifest" not in index
        assert "checkpoint" in archive.read("DELIVERY_README.md").decode()
    extracted = root / "multi_extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
    check = subprocess.run([sys.executable, "-S", str(extracted / "scripts/package_remaining_benchmark.py"),
                            "verify", "--directory", str(extracted)], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    assert len(json.loads(check.stdout)["tracks"]) == 2


@pytest.mark.parametrize("fault,match", [("counts", "matching nonzero"), ("pairing", "matching, policy-free"),
                                        ("duplicate_suite", "suite may appear only once"),
                                        ("runtime", "share one frozen runtime")])
def test_multi_pack_rejects_mismatched_pairs_suites_and_runtime(delivery, fault, match):
    root, manifest, replay_path, output = delivery
    other_manifest, other_replay = second_track(delivery,
        suite="libero_10" if fault == "duplicate_suite" else "libero_90",
        fingerprint="other-runtime" if fault == "runtime" else None)
    packs, reports = [manifest, other_manifest], [replay_path, other_replay]
    if fault == "counts":
        reports.pop()
    elif fault == "pairing":
        reports.reverse()
    with pytest.raises(ValueError, match=match):
        package.create_bundle(root, packs, reports, output)
    assert not output.exists()


def test_offline_verifier_rejects_swapped_track_labels_even_with_rehashed_index(delivery):
    root, manifest, replay_path, output = delivery
    other_manifest, other_replay = second_track(delivery)
    package.create_bundle(root, [manifest, other_manifest], [replay_path, other_replay], output)
    def mutate(bodies):
        index = json.loads(bodies[package.INDEX])
        for track, suite in zip(index["tracks"], ("libero_90", "libero_10")):
            track["suite"] = track["track_id"] = suite
        index["content_hash"] = package._manifest_hash(index)
        bodies[package.INDEX] = package._json_bytes(index)
    rewrite_zip(output, mutate)
    with pytest.raises(ValueError, match="suite does not match"):
        package.verify_bundle(output)


def test_mixed_suites_inside_one_candidate_manifest_are_rejected(delivery):
    _, path, _, _ = delivery
    manifest = json.loads(path.read_text())
    extras = deepcopy(manifest["episodes"])
    for episode in extras:
        episode["episode_id"] = "extension_" + episode["episode_id"]
        episode["task_id"] = "extension_task"
        episode["source_id"] = "extension_source"
        episode["suite"] = "libero_90"
    manifest["episodes"].extend(extras)
    manifest["content_hash"] = manifest_hash(manifest)
    write_json(path, manifest)
    with pytest.raises(ValueError, match="exactly one suite"):
        create(delivery)


def test_old_single_pack_index_without_tracks_remains_verifiable(delivery):
    create(delivery)
    def mutate(bodies):
        index = json.loads(bodies[package.INDEX])
        index.pop("tracks")
        index.pop("suite_evaluation_contract")
        index["content_hash"] = package._manifest_hash(index)
        bodies[package.INDEX] = package._json_bytes(index)
    rewrite_zip(delivery[3], mutate)
    assert package.verify_bundle(delivery[3])["coverage"]["episodes"] == 4


@pytest.mark.parametrize("multiple", [False, True])
def test_cli_single_and_repeated_pack_arguments(delivery, monkeypatch, capsys, multiple):
    from scripts import package_remaining_benchmark as command
    root, manifest, replay_path, output = delivery
    monkeypatch.setattr(command, "ROOT", root)
    args = ["create", "--state-pack", str(manifest), "--replay", str(replay_path),
            "--out", str(output), "--no-include-upstream"]
    if multiple:
        other_manifest, other_replay = second_track(delivery)
        args.extend(["--state-pack", str(other_manifest), "--replay", str(other_replay)])
    capsys.readouterr()
    assert command.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["format"] == (package.COLLECTION_FORMAT if multiple else package.FORMAT)
