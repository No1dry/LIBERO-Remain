"""Read-only UIR workflows using toy runs and explicitly synthetic video bytes.

The .mp4 fixtures below only exercise file/path/hash binding. They are not
encoded movies, human reviews, or evidence about a robot policy.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmark.remaining_goals import cli
from benchmark.remaining_goals.toy import build_toy_manifest


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tree_hashes(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


@pytest.fixture
def synthetic_run(tmp_path):
    manifest = build_toy_manifest(tmp_path / "fixture", scenes=1)
    output = tmp_path / "source_run"
    summary = cli.evaluate(manifest, output, policy_factory="benchmark.remaining_goals.toy:make_policy",
                           policy_config={"mode": "idle"}, policy_id="synthetic-uir-binding-test",
                           max_chunk_steps=1)
    (output / "videos").mkdir()
    for index, path in enumerate(sorted((output / "episodes").glob("*.json"))):
        row = read(path)
        video = f"videos/{index:06d}.mp4"
        (output / video).write_bytes(b"SYNTHETIC TEST BYTES; not an encoded video: " + row["episode_id"].encode())
        row["video"] = {"status": "saved", "path": video, "error": None, "synthetic": True,
                        "episode_id": row["episode_id"], "stride": 1,
                        "frames": row["n_steps"] + 1, "frame_steps": list(range(row["n_steps"] + 1))}
        write(path, row)
    # Distinct legacy formatting and an unrelated file expose accidental
    # in-place summarize/rescore calls, beyond numerical score equality.
    (output / "summary.json").write_text("\n" + json.dumps(summary, indent=5) + "\n\n", encoding="utf-8")
    with (output / "episodes.csv").open("ab") as file:
        file.write(b"\r\n")
    (output / "original_notes.txt").write_bytes(b"SYNTHETIC fixture; preserve source bytes.\n")
    return output, summary


def reviewed_annotations(run_dir, destination):
    annotations = cli.annotation_template(run_dir, destination, reviewer="synthetic-test-reviewer")
    assert annotations["synthetic"] is True
    _, _, results = cli.read_run(run_dir)
    by_id = {result["episode_id"]: result for result in results}
    for index, row in enumerate(annotations["annotations"]):
        result = by_id[row["episode_id"]]
        row.update(unnecessary_intervention=bool(index % 2), review_status="reviewed",
                   reviewed_full_episode=True, reason="Synthetic label for path/hash integration only.",
                   evidence=[{"video_path": result["video"]["path"], "start_step": 0,
                              "end_step": result["n_steps"]}])
    write(destination, annotations)
    return annotations


def assert_default_main_table(text):
    primary = text.split("## Main results", 1)[1].split("## Diagnostics", 1)[0]
    rows = [line for line in primary.splitlines() if line.startswith("|")]
    assert rows[0] == "| Task | Mask / stratum | Joint Success Rate | Unnecessary Intervention Rate (UIR) |"
    assert rows[2:] and all(row.split("|")[-2].strip() == "N/A" for row in rows[2:])
    assert "remaining_success" not in primary and "preservation_success" not in primary


def test_read_run_and_unannotated_derivation_preserve_every_source_file(synthetic_run, tmp_path):
    run_dir, original = synthetic_run
    before = tree_hashes(run_dir)
    assert {"summary.json", "episodes.csv", "original_notes.txt"} <= before.keys()
    metadata, manifest, results = cli.read_run(run_dir)
    assert metadata == read(run_dir / "run.json")
    assert manifest == read(run_dir / "manifest.json")
    assert len(results) == 4
    output = tmp_path / "derived"
    report = cli.derived_report(run_dir, output)
    assert tree_hashes(run_dir) == before
    # Full equality includes every existing numerator, denominator, count,
    # conservative rate, task/mask aggregation, and run/video metadata field.
    assert report["summary"] == read(output / "summary.json") == original
    assert report["uir"] is None and report["legacy_metrics_unchanged"] is True
    assert all(set(row) == {"task_id", "mask", "joint_success_rate", "unnecessary_intervention_rate"}
               for row in report["display"]["main"])
    assert all(row["unnecessary_intervention_rate"] is None for row in report["display"]["main"])
    assert {row["mask"] for row in report["display"]["main"]} == {
        "00", "10", "01", "11", "normal_00", "partial_macro", "terminal_11"}
    assert_default_main_table((output / "report.md").read_text(encoding="utf-8"))
    assert_default_main_table((run_dir / "report.md").read_text(encoding="utf-8"))
    assert all(before[name] == digest for name, digest in report["source_file_sha256"].items())


def test_annotated_derivation_binds_raw_annotation_and_synthetic_videos_without_rewriting(synthetic_run, tmp_path):
    run_dir, original = synthetic_run
    before = tree_hashes(run_dir)
    annotations_path = tmp_path / "synthetic_annotations.json"
    reviewed_annotations(run_dir, annotations_path)
    annotation_bytes = annotations_path.read_bytes()
    output = tmp_path / "annotated_report"
    report = cli.derived_report(run_dir, output, annotations_path=annotations_path)
    assert tree_hashes(run_dir) == before
    assert report["summary"] == original
    assert report["uir"]["synthetic"] is True
    counts = report["uir"]["counts"]
    assert (counts["numerator"], counts["denominator"], counts["rate"]) == (2, 4, .5)
    assert counts["unknown"] == counts["unannotated"] == 0
    assert report["uir"]["annotation_file_sha256"] == hashlib.sha256(annotation_bytes).hexdigest()
    assert report["uir"]["video_evidence_sha256"] == {name: digest for name, digest in before.items()
                                                       if name.startswith("videos/")}
    assert (output / "annotations.json").read_bytes() == annotation_bytes
    assert "SYNTHETIC" in (output / "report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("fault", ["duplicate_root", "duplicate_nested", "NaN", "Infinity", "-Infinity"])
def test_ambiguous_or_nonfinite_annotation_json_is_rejected_before_derivation(synthetic_run, tmp_path, fault):
    run_dir, _ = synthetic_run
    path = tmp_path / "synthetic_annotations.json"
    annotations = reviewed_annotations(run_dir, path)
    raw = json.dumps(annotations)
    if fault == "duplicate_root":
        raw = raw.replace('"run_id":', '"run_id": "discarded-wrong-run", "run_id":', 1)
    elif fault == "duplicate_nested":
        raw = raw.replace('"unnecessary_intervention": false',
                          '"unnecessary_intervention": true, "unnecessary_intervention": false', 1)
    else:
        raw = raw[:-1] + ', "synthetic_extra_value": ' + fault + '}'
    path.write_text(raw, encoding="utf-8")
    before = tree_hashes(run_dir)
    output = tmp_path / "rejected"
    message = "duplicate annotation JSON key" if fault.startswith("duplicate") else "annotation JSON requires finite values"
    with pytest.raises(ValueError, match=message):
        cli.derived_report(run_dir, output, annotations_path=path)
    assert not output.exists() and tree_hashes(run_dir) == before


def test_backslash_evidence_becomes_posix_before_filesystem_lookup_and_hashing(synthetic_run, tmp_path, monkeypatch):
    run_dir, original = synthetic_run
    path = tmp_path / "synthetic_annotations.json"
    annotations = reviewed_annotations(run_dir, path)
    for row in annotations["annotations"]:
        row["evidence"][0]["video_path"] = row["evidence"][0]["video_path"].replace("/", "\\")
    write(path, annotations)
    raw_bytes = path.read_bytes()
    before = tree_hashes(run_dir)
    original_join = Path.__truediv__
    def posix_separator_guard(parent, child):
        if parent == run_dir and isinstance(child, str):
            # Windows would accept a raw backslash separator and conceal a
            # Linux-only failure. Require portable input at this boundary.
            assert "\\" not in child, "untranslated Windows path reached filesystem lookup"
        return original_join(parent, child)
    monkeypatch.setattr(Path, "__truediv__", posix_separator_guard)
    output = tmp_path / "normalized_report"
    report = cli.derived_report(run_dir, output, annotations_path=path)
    evidence = [item for row in report["uir"]["by_episode"] for item in row["evidence"]]
    expected_hashes = {name: digest for name, digest in before.items() if name.startswith("videos/")}
    assert {item["video_path"] for item in evidence} == set(expected_hashes)
    assert report["uir"]["video_evidence_sha256"] == expected_hashes
    assert report["summary"] == original and tree_hashes(run_dir) == before
    # Normalization affects the derived summary, not the raw annotation evidence.
    assert (output / "annotations.json").read_bytes() == raw_bytes


@pytest.mark.parametrize("operation", ["template", "report"])
@pytest.mark.parametrize("destination", ["inside", "same", "existing"])
def test_outputs_must_be_new_and_outside_source_run(synthetic_run, tmp_path, operation, destination):
    run_dir, _ = synthetic_run
    if destination == "same":
        output = run_dir
    elif destination == "inside":
        output = run_dir / "new_subdir" / ("annotation.json" if operation == "template" else "report")
    else:
        output = tmp_path / ("existing.json" if operation == "template" else "existing_report")
        if operation == "template":
            output.write_bytes(b"original external bytes")
        else:
            output.mkdir()
            (output / "sentinel.txt").write_bytes(b"original external bytes")
    before = tree_hashes(tmp_path)
    call = cli.annotation_template if operation == "template" else cli.derived_report
    with pytest.raises(FileExistsError if destination == "existing" else ValueError):
        call(run_dir, output)
    assert tree_hashes(tmp_path) == before


@pytest.mark.parametrize("field", ["run_id", "manifest_hash"])
def test_wrong_annotation_identity_cannot_create_report(synthetic_run, tmp_path, field):
    run_dir, _ = synthetic_run
    path = tmp_path / "synthetic_annotations.json"
    annotations = reviewed_annotations(run_dir, path)
    annotations[field] = "wrong-run-identity"
    write(path, annotations)
    before = tree_hashes(run_dir)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="run_id/manifest_hash"):
        cli.derived_report(run_dir, output, annotations_path=path)
    assert not output.exists() and tree_hashes(run_dir) == before


@pytest.mark.parametrize("fault", ["missing", "parent", "absolute", "resolved_escape"])
def test_missing_or_escaping_video_cannot_supply_annotation_evidence(synthetic_run, tmp_path, monkeypatch, fault):
    run_dir, _ = synthetic_run
    path = tmp_path / "synthetic_annotations.json"
    annotations = reviewed_annotations(run_dir, path)
    selected = run_dir / annotations["annotations"][0]["evidence"][0]["video_path"]
    if fault == "missing":
        selected.unlink()
    elif fault in ("parent", "absolute"):
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"SYNTHETIC outside video bytes")
        annotations["annotations"][0]["evidence"][0]["video_path"] = "../outside.mp4" if fault == "parent" else str(outside)
        write(path, annotations)
    else:
        # Portable simulation of an in-run symlink resolving outside the run;
        # no Windows symlink privileges are required to exercise containment.
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"SYNTHETIC outside video bytes")
        original_resolve = Path.resolve
        def resolved(path, *args, **kwargs):
            return outside if path == selected else original_resolve(path, *args, **kwargs)
        monkeypatch.setattr(Path, "resolve", resolved)
    before = tree_hashes(run_dir)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="video"):
        cli.derived_report(run_dir, output, annotations_path=path)
    assert not output.exists() and tree_hashes(run_dir) == before


@pytest.mark.parametrize("module", ["benchmark.remaining_goals.cli", "benchmark.remaining_goals.evaluation"])
def test_both_real_cli_entrypoints_template_and_report_are_read_only(synthetic_run, tmp_path, module):
    run_dir, original = synthetic_run
    before = tree_hashes(run_dir)
    template_path, output = tmp_path / "cli_annotations.json", tmp_path / "cli_report"
    def invoke(arguments):
        process = subprocess.run([sys.executable, "-X", "utf8", "-m", module, *arguments],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                 text=True, encoding="utf-8", timeout=30)
        assert process.returncode == 0, process.stdout + process.stderr
        return process
    invoke(["uir-template", "--run-dir", str(run_dir), "--out", str(template_path),
            "--reviewer", "synthetic CLI reviewer"])
    annotations = read(template_path)
    assert annotations["synthetic"] is True
    assert all(row["reviewer"] == "synthetic CLI reviewer" and row["unnecessary_intervention"] is None
               and row["review_status"] == "unreviewed" for row in annotations["annotations"])
    process = invoke(["report", "--run-dir", str(run_dir), "--out", str(output),
                      "--annotations", str(template_path)])
    report = read(output / "report.json")
    assert report["summary"] == original
    assert report["uir"]["counts"]["denominator"] == 0
    assert report["uir"]["counts"]["rate"] is None
    assert_default_main_table(process.stdout)
    assert tree_hashes(run_dir) == before
