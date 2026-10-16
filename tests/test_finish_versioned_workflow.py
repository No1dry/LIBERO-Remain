"""Task010 CPU/file integration; no real model, simulator or scientific claim."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from benchmark.remaining_goals.finish import workflow as w
from benchmark.remaining_goals.finish.evaluation import (
    evaluation_contract, validate_evaluation_contract, budget_plan,
    JOB_SCHEMA_V3, PLAN_SCHEMA_V3, RUN_SCHEMA_V3, RESULT_SCHEMA_V2,
    CALIBRATION_SCHEMA_V3, RELEASE_V1, RELEASE_V2)
from benchmark.remaining_goals.finish.data import LABEL_CONTRACT
from tests.test_finish_workflow_domains import fixture, rehash
from tests.test_finish_workflow import tree_bytes, FakePolicy, TinyRecorder
from tests.test_finish_runner import observation


def versioned_fixture(tmp_path):
    job, registry, _ = fixture(tmp_path)
    from tests.test_finish_release_geometry import geometry_native
    xml = geometry_native().sim.model.get_xml()
    xml_sha256 = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    # The source fixture is still synthetic, but its saved physics identity must
    # name the very same fake compiled model as the actual measurement observer.
    bank_path = Path(job["source"]["manifest"])
    bank = w.read_json(bank_path)
    for episode, reference in zip(bank["episodes"], bank["preparations"]):
        episode["model_xml_sha256"] = xml_sha256
        path = bank_path.parent / reference["path"]
        preparation = w.read_json(path)
        preparation["episode"]["model_xml_sha256"] = xml_sha256
        preparation["provenance"]["model_xml_sha256"] = xml_sha256
        w.write_json(path, preparation, update=True)
        reference["sha256"] = w.file_sha(path)
    rehash(bank, "content_hash")
    w.write_json(bank_path, bank, update=True)
    job.update(schema_version=JOB_SCHEMA_V3, evaluation_contract=evaluation_contract())
    return job, registry


class GeometryEnvironment:
    """Fake state progression, real BasketContract/compiled-geometry evaluator.

    No native model is created. The shared tiny arrays are explicitly synthetic;
    this exercises wiring and revalidation, not physical trajectory validity.
    """
    def __init__(self, config, *, held=False):
        self.config, self.held = deepcopy(config), held
        self.steps = self.closed = self.resets = 0
        self.actions, self.begin_steps = [], []

    def reset(self, episode):
        from benchmark.remaining_goals.finish import environment
        from tests.test_finish_release_geometry import geometry_native
        self.native = geometry_native()
        self.steps = 0
        self.resets += 1
        self.initial_mask = deepcopy(episode["initial_mask"])
        for name, value in zip(environment.TARGETS, self.initial_mask):
            self.native.membership[name] = value
        if self.held:
            self.native.grasps.add("soup")
        self.contract = environment.BasketContract(
            self.native, evaluation_contract=self.config.get("evaluation_contract"))
        return observation(0)

    def measurement_static(self):
        return self.contract.measurement_static()

    def evaluator_state(self):
        return self.contract.evaluator_state()

    def step(self, action):
        from benchmark.remaining_goals.finish.environment import TARGETS
        self.actions.append(np.asarray(action).copy())
        self.native.step(action)
        self.steps += 1
        if self.steps >= 8:
            for name in TARGETS:
                self.native.membership[name] = True
        return observation(self.steps)

    def begin_hold(self):
        self.begin_steps.append(self.steps)
        return self.contract.hold.begin()

    def hold_action(self):
        return self.contract.hold.action()

    def close(self):
        self.closed += 1


class BoundPolicy(FakePolicy):
    def __init__(self, config):
        super().__init__(finish_at=8)
        self.config = deepcopy(config)
        self.head = w.head_manifest(config["finish"]["head_artifact"])

    def predict(self, obs, instruction):
        result = super().predict(obs, instruction)
        result["threshold"] = self.config["finish"]["threshold"]
        result["head_decision"] = "finish" if result["p"] >= result["threshold"] else "continue"
        result["head_identity"]["artifact_sha256"] = self.head["artifact_sha256"]
        result["head_identity"]["base_identity_sha256"] = self.head["identity_sha256"]["base_identity"]
        return result


def tiny_run(job, output, monkeypatch, *, held=False, expected_status="completed"):
    """Only the CPU fixture shortens H/W; production dry-plan remains 520/150."""
    plan = w.dry_plan(job)
    plan["configuration"] = {"horizon": 16, "retention_steps": 4, "max_chunk_steps": 8}
    for episode in plan["episodes"]:
        episode.update(horizon=16, retention_steps=4)
    rehash(plan, "plan_sha256")
    made = {}
    def env_factory(config):
        made["environment"] = GeometryEnvironment(config, held=held)
        return made["environment"]
    def policy_factory(config):
        made["policy"] = BoundPolicy(config)
        return made["policy"]
    with monkeypatch.context() as scoped:
        from benchmark.remaining_goals.finish import environment as environment_module
        # No native module exists in this CPU fixture. Declare only the fake
        # process-global callback state; all compiled-geometry math stays real.
        scoped.setattr(environment_module, "_contact_filter_status", lambda: "absent")
        scoped.setattr(w, "dry_plan", lambda _: deepcopy(plan))
        metadata = w.run(job, output, policy_factory=policy_factory,
                         env_factory=env_factory, recorder_factory=TinyRecorder)
    assert metadata["status"] == expected_status, metadata.get("error")
    assert made["environment"].closed == made["policy"].closed == 1
    return metadata, made


def test_versioned_dry_plan_reuses_frozen_head_bank_runtime_without_policy_truth(tmp_path):
    job, registry = versioned_fixture(tmp_path)
    before = tree_bytes(tmp_path)
    head = w.head_manifest(job["head_artifact"])
    plan = w.dry_plan(job)
    assert plan["schema_version"] == PLAN_SCHEMA_V3
    assert plan["evaluation_contract"] == evaluation_contract()
    assert plan["environment_config"]["evaluation_contract"] == evaluation_contract()
    assert plan["environment_config"]["environment"] == w.read_json(job["source"]["manifest"])["environment"]
    assert plan["head_sha256"] == head["artifact_sha256"]
    assert head["identities"]["label_contract"] == LABEL_CONTRACT
    assert plan["source_identity"]["registry_sha256"] == registry["registry_sha256"]
    assert plan["configuration"] == {"horizon": 520, "retention_steps": 150, "max_chunk_steps": 8}
    assert plan["expected"] == 5 and plan["maximum_physical_steps"] == 3350
    assert [row["initial_state_index"] for row in plan["episodes"]] == list(range(35, 40))
    policy_text = json.dumps(plan["policy_config"], sort_keys=True)
    assert "evaluation_contract" not in policy_text and RELEASE_V2 not in policy_text
    assert "measurement_static" not in policy_text and "eval_source" not in policy_text
    assert tree_bytes(tmp_path) == before


def test_existing_two_domain_job_stays_legacy_without_new_fields_or_writes(tmp_path):
    job, _, _ = fixture(tmp_path)
    before = tree_bytes(tmp_path)
    first, second = w.dry_plan(job), w.dry_plan(deepcopy(job))
    assert first == second
    assert first["schema_version"] == "remaining-finish-plan-v2"
    assert "evaluation_contract" not in first
    assert "evaluation_contract" not in first["environment_config"]
    assert "measurement_static" not in first
    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize("fault", ["missing", "method", "rule", "margin", "training", "legacy_job"])
def test_job_cannot_mix_or_rehash_an_unregistered_evaluation_contract(tmp_path, fault):
    job, _ = versioned_fixture(tmp_path)
    if fault == "missing":
        job.pop("evaluation_contract")
    elif fault == "legacy_job":
        job["schema_version"] = "remaining-finish-job-v2"
    else:
        key, value = {"method": ("release_method", RELEASE_V1),
                      "rule": ("calibration_rule", "first-hit-full-trajectory-known-v1"),
                      "margin": ("clearance_margin_m", 0.),
                      "training": ("training_labels_changed", True)}[fault]
        job["evaluation_contract"][key] = value
        rehash(job["evaluation_contract"], "contract_sha256")
    with pytest.raises(ValueError):
        w.dry_plan(job)


def test_real_geometry_record_read_calibrate_active_and_gt_noninterference(tmp_path, monkeypatch):
    job, _ = versioned_fixture(tmp_path / "inputs")
    inputs_before = tree_bytes(tmp_path / "inputs")
    shadow = tmp_path / "new-shadow"
    metadata, shadow_made = tiny_run(job, shadow, monkeypatch)
    assert metadata["schema_version"] == RUN_SCHEMA_V3
    assert metadata["evaluation_contract"] == evaluation_contract()
    saved = tree_bytes(shadow)
    loaded, results = w.read_run(shadow)
    assert loaded == metadata and len(results) == 5
    for result in results:
        assert result["schema_version"] == RESULT_SCHEMA_V2
        assert result["evaluation_contract"] == evaluation_contract()
        assert result["measurement_static"]
        assert result["evidence_validation"]["verified"]
        assert result["finish_step"] is None and result["n_steps"] == 20
        assert result["trace"][8]["released"] is True
        assert result["trace"][8]["measurement"]["legacy"]["released"] is None
        assert result["trace"][8]["measurement"]["contract_sha256"] == evaluation_contract()["contract_sha256"]
    from benchmark.remaining_goals.finish.release_geometry import validate_measurement_static
    from benchmark.remaining_goals.finish.schema import validate_finish_result
    changed = deepcopy(results[0])
    changed_static = changed["measurement_static"]
    changed_static["compiled_model_xml"] += "<!-- another self-consistent synthetic model -->"
    changed_static["compiled_model_xml_sha256"] = hashlib.sha256(
        changed_static["compiled_model_xml"].encode("utf-8")).hexdigest()
    rehash(changed_static, "static_sha256")
    assert validate_measurement_static(changed_static)
    with pytest.raises(ValueError, match="frozen source episode"):
        validate_finish_result(changed, metadata["episodes"][0])
    changed["model_xml_sha256"] = changed_static["compiled_model_xml_sha256"]
    with pytest.raises(ValueError, match="frozen source episode"):
        validate_finish_result(changed, metadata["episodes"][0])
    shadow_summary = w.rescore(shadow, tmp_path / "shadow-rescore")
    assert shadow_summary["counts"]["expected"] == 5 and shadow_summary["counts"]["successful"] is None
    calibrated = w.calibrate(shadow, tmp_path / "calibration")
    assert calibrated["schema_version"] == CALIBRATION_SCHEMA_V3 and calibrated["calibrated"]
    assert calibrated["active_eligible"] and calibrated["sensitivity_only"] is False
    assert calibrated["selected_threshold"] == .95 and calibrated["expected"] == 5
    assert not calibrated["ordinary_stopping_capability_established"]
    sensitivity = w.sensitivity(shadow, tmp_path / "sensitivity")
    assert sensitivity["sensitivity_only"] and not sensitivity["active_eligible"]
    assert sensitivity["selected_threshold"] is None and len(sensitivity["cells"]) == 4
    assert all(cell["expected"] == 5 and cell["sensitivity_only"] and not cell["active_eligible"]
               and cell["selected_threshold"] is None for cell in sensitivity["cells"])
    assert tree_bytes(shadow) == saved and tree_bytes(tmp_path / "inputs") == inputs_before
    job.update(purpose="normal_active", calibration=str(tmp_path / "calibration/calibration.json"))
    production_plan = w.dry_plan(job)
    assert production_plan["expected"] == 10 and production_plan["maximum_physical_steps"] == 6700
    assert [episode["initial_state_index"] for episode in production_plan["episodes"]] == list(range(40, 50))
    # Isolate population selection from the separately tested legacy Remain
    # source/replay loader: this is an explicitly prevalidated CPU source only.
    normal_source, _ = w.load_source(job["source"])
    remain_source = {"environment": deepcopy(normal_source["environment"]), "episodes": []}
    for index in range(5):
        for mask in ([False, False], [True, False], [False, True], [True, True]):
            item = deepcopy(normal_source["episodes"][0])
            item.update(episode_id=f"synthetic_remain_{index}_{int(mask[0])}{int(mask[1])}",
                        initial_state_index=index, seed=index, initial_mask=mask)
            remain_source["episodes"].append(item)
    remain_path = tmp_path / "prevalidated-synthetic-remain.json"
    w.write_json(remain_path, remain_source)
    remain_job = deepcopy(job)
    remain_job.update(purpose="remain_active", source={"kind": "remain", "manifest": str(remain_path)})
    with monkeypatch.context() as scoped:
        scoped.setattr(w, "load_source", lambda _: (deepcopy(remain_source), remain_path))
        remain_plan = w.dry_plan(remain_job)
    assert remain_plan["expected"] == 15 and remain_plan["maximum_physical_steps"] == 10050
    assert {tuple(row["initial_mask"]) for row in remain_plan["episodes"]} == {(True, False), (False, True), (True, True)}
    assert {row["initial_state_index"] for row in remain_plan["episodes"]} == set(range(5))
    good_meta, good = tiny_run(job, tmp_path / "active-good", monkeypatch)
    bad_meta, bad = tiny_run(job, tmp_path / "active-held", monkeypatch, held=True)
    _, good_results = w.read_run(tmp_path / "active-good")
    _, bad_results = w.read_run(tmp_path / "active-held")
    assert good_meta["missing"] == bad_meta["missing"] == []
    assert len(good_results) == len(bad_results) == 10
    assert all(row["finish_step"] == 8 and row["n_steps"] == 12 for row in good_results + bad_results)
    assert good["environment"].begin_steps == bad["environment"].begin_steps == [8] * 10
    for left, right in zip(good["environment"].actions, bad["environment"].actions):
        assert left.dtype == right.dtype and left.tobytes() == right.tobytes()
    assert len(good["policy"].inputs) == len(bad["policy"].inputs) == 20
    for (left, left_instruction), (right, right_instruction) in zip(good["policy"].inputs, bad["policy"].inputs):
        assert left_instruction == right_instruction
        assert set(left) == set(right) == set(observation(0))
        for key in left:
            assert left[key].dtype == right[key].dtype and left[key].tobytes() == right[key].tobytes()
    assert all(row["trace"][8]["released"] is True for row in good_results)
    assert all(row["trace"][8]["released"] is False for row in bad_results)
    assert w.rescore(tmp_path / "active-good", tmp_path / "good-scores")["counts"]["successful"] == 10
    assert w.rescore(tmp_path / "active-held", tmp_path / "bad-scores")["counts"]["successful"] == 0
    assert shadow_made["environment"].steps == 20


def test_read_run_rejects_missing_or_tampered_measurement_after_raw_hash_update(tmp_path, monkeypatch):
    job, _ = versioned_fixture(tmp_path / "inputs")
    out = tmp_path / "shadow"
    metadata, _ = tiny_run(job, out, monkeypatch)
    raw_path, metadata_path = out / "raw/0000.json", out / "run.json"
    raw_bytes, metadata_bytes = raw_path.read_bytes(), metadata_path.read_bytes()
    original = w.read_json(raw_path)
    for fault in ("missing_dual", "legacy_result", "pose", "legacy_truth", "query_threshold", "source_state"):
        changed, changed_metadata = deepcopy(original), deepcopy(metadata)
        if fault == "missing_dual":
            changed["trace"][8].pop("measurement")
        elif fault == "legacy_result":
            changed["schema_version"] = "remaining-finish-episode-v1"
        elif fault == "pose":
            changed["trace"][8]["measurement"]["poses"]["positions"][0][2] += .01
        elif fault == "legacy_truth":
            changed["trace"][8]["measurement"]["legacy"]["released"] = True
        elif fault == "query_threshold":
            # Every query remains mutually consistent and its decision is still
            # correct for these low/high probabilities; only the frozen run's
            # threshold binding identifies the substituted value.
            for query in changed["queries"]:
                query["threshold"] = .95
        else:
            changed["state_sha256"] = "0" * 64
        try:
            w.write_json(raw_path, changed, update=True)
            changed_metadata["results"][0]["sha256"] = w.file_sha(raw_path)
            w.write_json(metadata_path, changed_metadata, update=True)
            with pytest.raises((ValueError, KeyError)):
                w.read_run(out)
        finally:
            raw_path.write_bytes(raw_bytes)
            metadata_path.write_bytes(metadata_bytes)
    assert len(w.read_run(out)[1]) == 5


def test_measurement_technical_error_preserves_partial_and_fixed_missing_population(tmp_path, monkeypatch):
    from benchmark.remaining_goals.finish.release_geometry import MeasurementError
    job, _ = versioned_fixture(tmp_path / "inputs")
    original = GeometryEnvironment.evaluator_state
    def failure(self):
        if self.steps == 1:
            raise MeasurementError("synthetic missing compiled geometry field")
        return original(self)
    monkeypatch.setattr(GeometryEnvironment, "evaluator_state", failure)
    out = tmp_path / "partial"
    metadata, made = tiny_run(job, out, monkeypatch, expected_status="technical_pause")
    assert len(metadata["episodes"]) == 5 and len(metadata["missing"]) == 4
    assert len(metadata["results"]) == 1
    _, results = w.read_run(out)
    assert results[0]["status"] == "runtime_error"
    assert results[0]["n_steps"] == 1 and len(results[0]["trace"]) == 1
    assert "MeasurementError" in results[0]["error"]
    summary = w.rescore(out, tmp_path / "partial-rescore")
    assert summary["counts"]["expected"] == 5 and summary["counts"]["missing"] == 4
    assert summary["counts"]["technical_error"] == 1 and summary["counts"]["successful"] is None
    assert made["environment"].closed == made["policy"].closed == 1


def test_versioned_normal_capability_keeps_technical_rows_with_null_timing_in_fixed_n():
    good = {"goals_at_exit": [True, True], "released_at_exit": True,
            "failure_reasons": [], "compliant_finish": True,
            "timing_diagnostic": {"timely": True, "timing_unknown": False}}
    technical = {"goals_at_exit": None, "released_at_exit": None,
                 "failure_reasons": ["technical_error"], "compliant_finish": None,
                 "timing_diagnostic": None}
    summary = {"evaluation_contract": evaluation_contract(),
               "episodes": [good] + [deepcopy(technical) for _ in range(9)],
               "counts": {"successful": 1, "compliant_finish_percent": 10.,
                          "delay_observed": 1, "delay_coverage": .1, "delay_mean_steps": 0.,
                          "delay_categories": {"observed": 1, "technical_error": 9},
                          "unknown": 0, "technical_error": 9, "missing": 0}}
    capability = w._normal_capability(summary, "normal_active")["ordinary_stopping_capability"]
    assert capability["expected"] == 10 and capability["technical_error"] == 9
    assert capability["correct_finish_within_24_steps"] == {"numerator": 1, "denominator": 10, "percent": 10.}
    assert capability["compliant_finish_within_24_steps"] == {"numerator": 1, "denominator": 10, "percent": 10.}
    assert capability["timing_unknown"] == {"numerator": 0, "denominator": 10, "percent": 0.}
    assert capability["delay_coverage"] == .1
    assert all(row["timing_diagnostic"] is None for row in summary["episodes"][1:])


def test_formal_active_rejects_mixed_and_sensitivity_calibrations_even_rehashed(tmp_path, monkeypatch):
    job, _ = versioned_fixture(tmp_path / "inputs")
    shadow = tmp_path / "shadow"
    tiny_run(job, shadow, monkeypatch)
    report = w.calibrate(shadow, tmp_path / "formal")
    sensitivity = w.sensitivity(shadow, tmp_path / "sensitivity")
    assert report["calibrated"]
    job["purpose"] = "normal_active"
    variants = {}
    for fault in ("uncalibrated", "head", "role", "method", "rule", "contract", "sensitivity_marker", "not_eligible"):
        changed = deepcopy(report)
        if fault == "uncalibrated":
            changed.update(calibrated=False, selected_threshold=None)
        elif fault == "head":
            changed["binding"]["head_sha256"] = "0" * 64
        elif fault == "role":
            changed["calibration_role"] = "normal_test"
        elif fault == "method":
            changed["release_method"] = RELEASE_V1
        elif fault == "rule":
            changed["calibration_rule"] = "first-hit-full-trajectory-known-v1"
        elif fault == "contract":
            changed["evaluation_contract"]["clearance_margin_m"] = 0.
            rehash(changed["evaluation_contract"], "contract_sha256")
        elif fault == "sensitivity_marker":
            changed["sensitivity_only"] = True
        else:
            changed["active_eligible"] = False
        rehash(changed, "calibration_sha256")
        variants[fault] = changed
    variants["sensitivity_table"] = sensitivity
    variants.update({f"sensitivity_cell_{index}": cell for index, cell in enumerate(sensitivity["cells"])})
    for fault, changed in variants.items():
        path = tmp_path / "bad" / (fault + ".json")
        w.write_json(path, changed)
        job["calibration"] = str(path)
        with pytest.raises(ValueError):
            w.dry_plan(job)
    job["calibration"] = str(tmp_path / "formal/calibration.json")
    original_predict = BoundPolicy.predict
    def wrong_adapter_threshold(self, observation, instruction):
        result = original_predict(self, observation, instruction)
        assert self.config["finish"]["threshold"] == .95
        result["threshold"] = .5
        result["head_decision"] = "finish" if result["p"] >= .5 else "continue"
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(BoundPolicy, "predict", wrong_adapter_threshold)
        wrong_dir = tmp_path / "wrong-adapter-threshold"
        metadata, made = tiny_run(job, wrong_dir, scoped, expected_status="technical_pause")
    assert len(metadata["missing"]) == 9 and made["environment"].actions == []
    _, results = w.read_run(wrong_dir)
    assert len(results) == 1 and results[0]["status"] == "runtime_error"
    assert results[0]["n_steps"] == 0 and results[0]["executed_actions"] == []
    assert "threshold" in results[0]["error"].lower()
    assert made["environment"].closed == made["policy"].closed == 1


def test_existing_legacy_run_stays_readable_and_uncalibrated_without_upgrade(tmp_path, monkeypatch):
    job, _, _ = fixture(tmp_path / "inputs")
    shadow = tmp_path / "legacy-shadow"
    metadata, _ = tiny_run(job, shadow, monkeypatch)
    assert metadata["schema_version"] == "remaining-finish-run-v2"
    assert "evaluation_contract" not in metadata
    before = tree_bytes(shadow)
    _, results = w.read_run(shadow)
    assert len(results) == 5
    for result in results:
        assert result["schema_version"] == "remaining-finish-episode-v1"
        assert "evaluation_contract" not in result and "measurement_static" not in result
        assert all("measurement" not in row for row in result["trace"])
    report = w.calibrate(shadow, tmp_path / "legacy-calibration")
    assert report["schema_version"] == "remaining-finish-calibration-v2"
    # This synthetic legacy case historically retains its never-hit .99
    # diagnostic candidate while calibrated=False. Preserve that exact behavior;
    # it does not change the real old pilot's frozen null-threshold artifact.
    assert not report["calibrated"] and report["selected_threshold"] == .99
    assert "evaluation_contract" not in report
    w.rescore(shadow, tmp_path / "legacy-rescore")
    assert tree_bytes(shadow) == before


def test_three_new_templates_bind_the_exact_contract_and_reuse_existing_artifacts():
    directory = Path(__file__).parents[1] / "configs/remaining_goals/finish"
    for purpose in ("validation_shadow", "normal_active", "remain_active"):
        old = w.read_json(directory / (purpose + ".example.json"))
        new = w.read_json(directory / "versioned_release" / (purpose + ".example.json"))
        assert old["schema_version"] == "remaining-finish-job-v2" and "evaluation_contract" not in old
        assert new["schema_version"] == JOB_SCHEMA_V3 and new["purpose"] == purpose
        assert validate_evaluation_contract(new["evaluation_contract"]) == evaluation_contract()
        assert "EXISTING" in new["head_artifact"] and "EXISTING" in new["runtime_config"]
        assert new["video"] == {"enabled": True, "camera": "both", "fps": 20, "stride": 1}
        if purpose != "validation_shadow":
            assert new["calibration"] == "/ABS/NEW_TASK010_RESULTS/calibration/calibration.json"


def test_runbook_stage_commands_use_only_actual_cli_flags():
    import re
    import shlex
    from benchmark.remaining_goals.finish.cli import parser
    text = (Path(__file__).parents[1] / "docs/finish_versioned_release_runbook.md").read_text(encoding="utf-8")
    stages = re.findall(r"^finish010_stage\s+\S+\s+(.+)$", text, flags=re.MULTILINE)
    assert len(stages) == 11
    parsed = [parser().parse_args(shlex.split(line)) for line in stages]
    assert [item.command for item in parsed] == ["budget-plan", "dry-plan", "run", "calibrate",
        "sensitivity", "dry-plan", "run", "dry-plan", "run", "inspect", "rescore"]
    assert parsed[0].revision == "task010"


def test_revision_budget_keeps_old_cost_and_fixed_new_stage_roles():
    report = budget_plan()
    assert report["previous_validation_shadow"] == report["validation_shadow"] == 5
    assert report["normal_active"] == 10 and report["remain_active"] == 15
    assert report["remain_shadow"] == 0 and report["rollouts"] == 35
    assert report["maximum_physical_steps"] == 23450
    assert report["remaining_rollouts"] == 30 and report["remaining_maximum_physical_steps"] == 20100
    assert not report["simulation_created"] and not report["weights_loaded"]


@pytest.mark.parametrize("arguments", [["--help"], ["sensitivity", "--help"],
    ["budget-plan", "--revision", "task010"], ["budget-plan"]])
def test_help_and_budget_import_no_native_or_model_packages(arguments):
    script = '''import builtins, json, runpy, sys
real = builtins.__import__
blocked = {"mujoco", "mujoco_py", "libero", "robosuite", "torch", "transformers"}
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("file-only command imported forbidden package: " + name)
    return real(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = ["finish", *json.loads(sys.argv[1])]
try:
    runpy.run_module("benchmark.remaining_goals.finish.cli", run_name="__main__")
except SystemExit as error:
    assert error.code == 0, error.code
'''
    result = subprocess.run([sys.executable, "-c", script, json.dumps(arguments)],
        cwd=Path(__file__).parents[1], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    if arguments[0] == "budget-plan":
        report = json.loads(result.stdout)
        assert report["rollouts"] == (35 if "task010" in arguments else 30)
