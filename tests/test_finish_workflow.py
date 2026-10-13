"""Synthetic CPU/file workflow tests. No simulator, VLA, or encoded-video claim."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from benchmark.remaining_goals.finish import workflow as w
from benchmark.remaining_goals.finish import evidence as ev
from benchmark.remaining_goals.finish.data import canonical_hash, DEFAULT_SPLIT
from benchmark.remaining_goals.finish.schema import PROTOCOL
from benchmark.remaining_goals.observation_artifact import save_observation_artifact
from tests.test_finish_runner import Env, Policy, episode, observation


class FakeEnv(Env):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.closed = 0

    def reset(self, ep):
        self.steps = 0
        return super().reset(ep)

    def close(self):
        self.closed += 1


class FakePolicy(Policy):
    provenance = {"synthetic": True}

    def __init__(self, **kw):
        super().__init__(**kw)
        self.closed = 0

    def close(self):
        self.closed += 1


class TinyRecorder:
    """Writes distinguishable placeholder bytes, deliberately not a real MP4."""
    instances = []

    def __init__(self, output, config, **kw):
        self.output, self.frames, self.closed = Path(output), [], 0
        self.instances.append(self)

    def capture(self, obs, *, step):
        self.frames.append(step)

    def close(self):
        self.closed += 1
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"SYNTHETIC-NOT-MP4:" + bytes(self.frames))
        return {"status": "saved", "path": self.output.name, "frame_steps": self.frames, "synthetic": True}


def plan(n=2, mode="active"):
    episodes = []
    for i in range(n):
        item = episode()
        item.update(episode_id=f"synthetic_{i}", initial_state_index=40+i)
        episodes.append(item)
    value = {"schema_version": "remaining-finish-plan-v1", "protocol_version": PROTOCOL,
             "mode": mode, "purpose": "normal_active" if mode == "active" else "validation_shadow",
             "split": deepcopy(DEFAULT_SPLIT), "head_split_identity": {"split": deepcopy(DEFAULT_SPLIT)},
             "head_sha256": "b"*64, "manifest_hash": "c"*64,
             "configuration": {"horizon": 9, "retention_steps": 4, "max_chunk_steps": 8},
             "episodes": episodes, "policy_config": {}, "environment_config": {},
             "video": {"enabled": True, "camera": "both", "fps": 20, "stride": 1}}
    value["plan_sha256"] = canonical_hash(value)
    return value


def run_fake(tmp_path, monkeypatch, *, env=None, policy=None, recorder=TinyRecorder, mode="active", n=2):
    frozen = plan(n, mode)
    monkeypatch.setattr(w, "dry_plan", lambda cfg: deepcopy(frozen))
    env, policy = env or FakeEnv(), policy or FakePolicy(finish_at=0)
    out = tmp_path / "run"
    metadata = w.run({}, out, policy_factory=lambda cfg: policy, env_factory=lambda cfg: env,
                     recorder_factory=recorder)
    return out, metadata, env, policy


def tree_bytes(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_real_file_flow_failed_policy_outcome_continues_and_readonly_rescore(tmp_path, monkeypatch):
    out, metadata, env, policy = run_fake(tmp_path, monkeypatch)
    assert metadata["status"] == "completed" and metadata["missing"] == []
    assert env.resets == policy.resets == 2 and env.closed == policy.closed == 1
    before = tree_bytes(out)
    loaded, results = w.read_run(out)
    assert len(results) == 2 and all(r["finish_step"] == 0 for r in results)
    assert all(r["evidence_validation"]["verified"] for r in results)
    summary = w.rescore(out, tmp_path / "derived")
    assert summary["counts"]["expected"] == 2 and summary["counts"]["successful"] == 0
    capability = summary["ordinary_stopping_capability"]
    assert capability["premature_finish"] == {"numerator": 2, "denominator": 2, "percent": 100.}
    assert capability["completion_at_exit"]["numerator"] == 0
    assert capability["delay_coverage"] == 0
    assert "Normal00 active capability" in (tmp_path/"derived/report.md").read_text(encoding="utf-8")
    assert tree_bytes(out) == before
    with pytest.raises(ValueError, match="outside"):
        w.rescore(out, out/"derived")
    with pytest.raises(FileExistsError):
        w.rescore(out, tmp_path/"derived")
    with pytest.raises(FileExistsError):
        w.run({}, out, policy_factory=lambda c: pytest.fail("must not load"))


@pytest.mark.parametrize("kind", ["predict", "reset", "initial", "interrupt"])
def test_technical_pause_keeps_partial_fixed_expected_and_closes(tmp_path, monkeypatch, kind):
    env, policy = FakeEnv(), FakePolicy(fail_query=2)
    if kind == "reset":
        env.reset = lambda ep: (_ for _ in ()).throw(RuntimeError("reset failed"))
    elif kind == "initial":
        env.wrong_initial = True
    elif kind == "interrupt":
        policy.predict = lambda *args: (_ for _ in ()).throw(KeyboardInterrupt("synthetic interrupt"))
    out, metadata, env, policy = run_fake(tmp_path, monkeypatch, env=env, policy=policy)
    assert metadata["status"] == "technical_pause" and len(metadata["episodes"]) == 2
    assert metadata["missing"] == ["synthetic_1"] and len(metadata["results"]) == 1
    assert env.closed == policy.closed == 1
    _, results = w.read_run(out)
    assert results[0]["status"] == "runtime_error"
    if kind == "predict":
        assert results[0]["n_steps"] == 8 and len(results[0]["executed_actions"]) == 8
    if kind == "interrupt":
        assert metadata["interrupted"] is True and results[0]["interrupted"] is True
    summary = w.rescore(out, tmp_path/"derived")
    assert summary["counts"]["expected"] == 2 and summary["counts"]["missing"] == 1


@pytest.mark.parametrize("phase", ["policy_setup", "environment_setup", "video_setup", "evidence_setup"])
def test_setup_failure_records_attempt_and_closes_acquired_resources(tmp_path, monkeypatch, phase):
    monkeypatch.setattr(w, "dry_plan", lambda cfg: plan())
    env, policy = FakeEnv(), FakePolicy()
    def fail(*args, **kw):
        raise RuntimeError("synthetic setup failure")
    if phase == "evidence_setup":
        monkeypatch.setattr(ev, "FinishEvidence", fail)
    before = len(TinyRecorder.instances)
    out = tmp_path/"run"
    metadata = w.run({}, out, policy_factory=fail if phase == "policy_setup" else lambda c: policy,
                     env_factory=fail if phase == "environment_setup" else lambda c: env,
                     recorder_factory=fail if phase == "video_setup" else TinyRecorder)
    assert metadata["status"] == "technical_pause" and metadata["error_phase"] == phase
    assert metadata["missing"] == ["synthetic_0", "synthetic_1"] and metadata["results"] == []
    assert policy.closed == (phase != "policy_setup")
    assert env.closed == (phase in {"video_setup", "evidence_setup"})
    assert w.read_run(out)[1] == []
    if phase == "evidence_setup":
        assert TinyRecorder.instances[before].closed == 1
        assert metadata["attempts"][0]["video"]["status"] == "saved"
        assert metadata["attempts"][0]["video"]["path"] == "videos/0000.mp4"


def test_evidence_setup_plus_invalid_close_report_keeps_primary_error(tmp_path, monkeypatch):
    class BrokenClose(TinyRecorder):
        def close(self):
            self.closed += 1
            return {"not_json": np.ones(1)}
    monkeypatch.setattr(ev, "FinishEvidence", lambda *args: (_ for _ in ()).throw(OSError("evidence setup failed")))
    out, metadata, env, policy = run_fake(tmp_path, monkeypatch, recorder=BrokenClose)
    assert "evidence setup failed" in metadata["error"]
    assert metadata["attempts"][0]["video"]["status"] == "video_error"
    assert env.closed == policy.closed == 1


@pytest.mark.parametrize("fault", ["video_capture", "video_close", "evidence_query", "evidence_finish"])
def test_partial_video_and_evidence_failures_remain_readable(tmp_path, monkeypatch, fault):
    class Recorder(TinyRecorder):
        def capture(self, obs, *, step):
            super().capture(obs, step=step)
            if fault == "video_capture" and step == 1:
                raise OSError("capture error")
        def close(self):
            result = super().close()
            return {"status": "video_error", "error": "synthetic encoder"} if fault == "video_close" else result
    if fault.startswith("evidence_"):
        method = "capture_query" if fault == "evidence_query" else "finish"
        def fail(*args, **kw):
            raise OSError("synthetic evidence write failure")
        monkeypatch.setattr(ev.FinishEvidence, method, fail)
    out, metadata, env, policy = run_fake(tmp_path, monkeypatch, recorder=Recorder, policy=FakePolicy())
    assert metadata["status"] == "technical_pause" and metadata["missing"] == ["synthetic_1"]
    _, results = w.read_run(out)
    assert results[0]["status"] == "runtime_error"
    assert env.closed == policy.closed == 1
    assert (out/"raw/0000.json").is_file() and (out/"evidence/0000/execution.json").is_file()


@pytest.mark.parametrize("fault", ["missing_video", "post_validation"])
def test_post_run_verification_failure_never_discards_raw(tmp_path, monkeypatch, fault):
    class Missing(TinyRecorder):
        def close(self):
            self.closed += 1
            return {"status": "saved", "path": self.output.name}
    if fault == "post_validation":
        monkeypatch.setattr(ev, "validate_finish_evidence", lambda *args: (_ for _ in ()).throw(ValueError("evidence differs")))
    out, metadata, _, _ = run_fake(tmp_path, monkeypatch, recorder=Missing if fault == "missing_video" else TinyRecorder)
    assert metadata["status"] == "technical_pause" and metadata["missing"] == ["synthetic_1"]
    raw = w.read_json(out/"raw/0000.json")
    assert raw["n_steps"] == 4 and raw["queries"] and raw["executed_actions"]
    assert metadata["results"][0]["validation"]["status"] == "error"
    assert w.read_json(out/"summary.json")["unverified_raw_results"] == ["synthetic_0"]
    with pytest.raises(ValueError, match="unverified"):
        w.read_run(out)


@pytest.mark.parametrize("target", ["raw", "video", "input", "legacy_run", "legacy_result"])
def test_read_rejects_tampering_and_legacy_records(tmp_path, monkeypatch, target):
    out, metadata, _, _ = run_fake(tmp_path, monkeypatch)
    if target == "raw":
        (out/"raw/0000.json").write_bytes(b"{}")
    elif target == "video":
        (out/"videos/0000.mp4").write_bytes(b"other bytes")
    elif target == "input":
        (out/"evidence/0000/query_0001.npz").write_bytes(b"other bytes")
    elif target == "legacy_run":
        metadata["schema_version"] = "remaining-goals-run-v1"
        w.write_json(out/"run.json", metadata, update=True)
    else:
        raw = w.read_json(out/"raw/0000.json")
        raw.pop("schema_version")
        w.write_json(out/"raw/0000.json", raw, update=True)
        metadata["results"][0]["sha256"] = w.file_sha(out/"raw/0000.json")
        w.write_json(out/"run.json", metadata, update=True)
    with pytest.raises((ValueError, OSError)):
        w.read_run(out)


def fake_prepare(task, index, out, **kw):
    """Physical data are synthetic; only serialization/source binding is exercised."""
    out.mkdir(parents=True)
    state = np.array([1., -0., index], np.float64)
    (out/"states").mkdir()
    np.save(out/"states/base.npy", state, allow_pickle=False)
    initial = save_observation_artifact(out, "initial.npz", observation(0))
    identity = {"dtype": state.dtype.str, "shape": list(state.shape), "sha256": hashlib.sha256(state.tobytes()).hexdigest()}
    audit = {"technical_acceptance": True, "requested_steps": 150, "completed_steps": 150, "error": None,
             "trace": [{"step": i, "goals": [False, False], "state": state.tolist(),
                        "observation_check": {"returned_sha256": initial["observation_sha256"]}} for i in range(151)]}
    w.write_json(out/"audit.json", audit)
    environment = {"name": "libero", "fingerprint": "synthetic-file-only"}
    ep = episode()
    ep.update(episode_id=f"basket_s{index:03d}_00", task_id="basket", initial_state_index=index, seed=index,
              horizon=520, retention_steps=150, state_path="states/base.npy", state_sha256=w.file_sha(out/"states/base.npy"),
              initial_observation=initial, construction={"technical_audit": "audit.json"},
              model_xml_sha256="d"*64, bddl_sha256="e"*64)
    report = {"schema_version": "remaining-goals-capability-statebank-v1", "purpose": "normal00-capability-regression",
              "complete_paired_benchmark": False, "status": "prepared", "error": None, "episode": ep,
              "environment_config": {"environment": environment, "control_freq": 20, "image_size": 256},
              "preparation": {"attempted": 1, "requested_index": index, "replacement_indices": [],
                              "settle_steps_requested": 80, "settle_steps_completed": 80,
                              "audit_steps_requested": 150, "audit_steps_completed": 150, "policy_steps": 0,
                              "horizon": 520, "retention_steps": 150, "settled_goal_values": [False, False],
                              "audit": {"technical_acceptance": True}},
              "provenance": {"environment": environment, "task_key": "basket", "initial_state_index": index,
                             "environment_seed": index, "model_xml_sha256": ep["model_xml_sha256"], "bddl_sha256": ep["bddl_sha256"],
                             "official_instruction": ep["instruction"], "saved_state_sha256": ep["state_sha256"],
                             "settled_base_state": identity, "selected_official_state": identity, "restored_official_state": identity,
                             "official_initial_state_file": {"sha256": "f"*64, "count": 50},
                             "technical_audit_sha256": w.file_sha(out/"audit.json")}}
    w.write_json(out/"preparation.json", report)
    return report


def actual_plan_files(tmp_path):
    bank = tmp_path/"bank"
    w.prepare_normal_bank([35], bank, prepare=fake_prepare)
    split = {"train": [5], "validation": [35], "normal_test": [40], "remain_test": list(range(5))}
    confirmation = {"confirmed": True, "reviewer": "synthetic-test", "reason": "CPU file fixture only"}
    head = tmp_path/"head"
    head.mkdir()
    (head/"head.npz").write_bytes(b"synthetic file-only head; never loaded")
    manifest = {"schema_version": "remaining-finish-head-v1", "weights": {"path": "head.npz", "sha256": w.file_sha(head/"head.npz")},
                "identities": {"split_identity": {"split": split, "sha256": canonical_hash(split), "alternative_confirmation": confirmation}}}
    manifest["artifact_sha256"] = canonical_hash(manifest)
    w.write_json(head/"head.json", manifest)
    runtime = tmp_path/"runtime.json"
    w.write_json(runtime, {"model_id": "openvla_oft", "suite": "libero_10", "execution": {"max_chunk_steps": 8, "random_seed": 7}})
    config = {"schema_version": "remaining-finish-job-v1", "purpose": "validation_shadow", "split": split,
              "alternative_confirmation": confirmation, "runtime_config": str(runtime), "head_artifact": str(head),
              "source": {"kind": "normal_bank", "manifest": str(bank/"normal_bank.json")}}
    return config, bank


def test_file_only_dry_plan_exact_sources_budgets_and_no_source_changes(tmp_path):
    config, bank = actual_plan_files(tmp_path)
    before = tree_bytes(bank)
    value = w.dry_plan(config)
    assert value["expected"] == 1 and value["maximum_physical_steps"] == 670
    assert value["configuration"] == {"horizon": 520, "retention_steps": 150, "max_chunk_steps": 8}
    assert value["head_split_identity"]["alternative_confirmation"]["confirmed"] is True
    assert not value["simulation_created"] and not value["weights_loaded"]
    assert tree_bytes(bank) == before
    runtime = w.read_json(config["runtime_config"])
    runtime["execution"]["random_seed"] = 0
    w.write_json(config["runtime_config"], runtime, update=True)
    with pytest.raises(ValueError, match="seed7"):
        w.dry_plan(config)


@pytest.mark.parametrize("change", ["episode", "audit", "index", "state_after_audit", "settle"])
def test_bank_cannot_substitute_preparation_even_after_rehash(tmp_path, change):
    config, bank = actual_plan_files(tmp_path)
    manifest = w.read_json(bank/"normal_bank.json")
    ref = manifest["preparations"][0]
    report_path = bank/ref["path"]
    report = w.read_json(report_path)
    if change == "episode":
        manifest["episodes"][0]["instruction"] = "substituted instruction"
    elif change == "index":
        ref["source_index"] = 36
    elif change == "audit":
        report["provenance"]["technical_audit_sha256"] = "0"*64
    elif change == "settle":
        report["preparation"]["settle_steps_completed"] = 79
    else:
        audit_path = report_path.parent/"audit.json"
        audit = w.read_json(audit_path)
        audit["trace"][0]["state"][0] = 100.
        w.write_json(audit_path, audit, update=True)
        report["provenance"]["technical_audit_sha256"] = w.file_sha(audit_path)
    w.write_json(report_path, report, update=True)
    ref["sha256"] = w.file_sha(report_path)
    manifest.pop("content_hash")
    manifest["content_hash"] = canonical_hash(manifest)
    w.write_json(bank/"normal_bank.json", manifest, update=True)
    with pytest.raises(ValueError):
        w.load_source(config["source"])


def test_calibration_passes_frozen_alternative_split_identity_without_source_writes(tmp_path, monkeypatch):
    out, _, _, _ = run_fake(tmp_path, monkeypatch, mode="shadow", n=1)
    from benchmark.remaining_goals.finish import calibration
    captured = {}
    def calibrator(episodes, results, **kw):
        captured.update(kw)
        return {"schema_version": "remaining-finish-calibration-v1", "calibrated": False}
    monkeypatch.setattr(calibration, "calibrate_threshold", calibrator)
    before = tree_bytes(out)
    w.calibrate(out, tmp_path/"cal")
    assert captured["split_identity"] == plan(1, "shadow")["head_split_identity"]
    assert tree_bytes(out) == before
    with pytest.raises(ValueError, match="outside"):
        w.calibrate(out, out/"cal")


def test_normal_capability_separates_correct_timing_from_hold_compliance_fixed_n():
    row = {"goals_at_exit": [True, True], "released_at_exit": True, "delay_status": "observed",
           "finish_delay_steps": 24, "failure_reasons": [], "compliant_finish": True}
    rows = [deepcopy(row), {**deepcopy(row), "compliant_finish": False, "failure_reasons": ["unstable_after_exit"]},
            {"failure_reasons": [], "compliant_finish": None, "delay_status": "missing"},
            {"failure_reasons": [], "compliant_finish": None, "delay_status": "technical_error"},
            {**deepcopy(row), "released_at_exit": None, "compliant_finish": None, "delay_status": "unknown_release",
             "finish_delay_steps": None}]
    summary = {"episodes": rows, "counts": {"successful": 1, "compliant_finish_percent": 20., "delay_observed": 2,
                "delay_coverage": .4, "delay_mean_steps": 24., "delay_categories": {"observed": 2},
                "unknown": 1, "technical_error": 1, "missing": 1}}
    cap = w._normal_capability(summary, "normal_active")["ordinary_stopping_capability"]
    assert cap["completion_at_exit"] == cap["correct_finish_within_24_steps"] == {"numerator": 2, "denominator": 5, "percent": 40.}
    assert cap["compliant_finish_within_24_steps"] == {"numerator": 1, "denominator": 5, "percent": 20.}
    assert cap["delay_coverage"] == .4 and cap["missing"] == cap["technical_error"] == cap["unknown"] == 1
    assert "not a software acceptance gate" in cap["notice"]


@pytest.mark.parametrize("arguments", [["--help"], ["budget-plan"], ["budget-plan", "--include-remain-shadow"]])
def test_cli_help_budget_do_not_import_model_or_simulator(arguments):
    script = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','libero','robosuite','mujoco','transformers'}:
            raise AssertionError('forbidden heavy import: ' + fullname)
sys.meta_path.insert(0, Block())
from benchmark.remaining_goals.finish.cli import main
raise SystemExit(main(sys.argv[1:]))
'''
    result = subprocess.run([sys.executable, "-c", script, *arguments], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    if arguments[0] == "budget-plan":
        parsed = json.loads(result.stdout)
        assert parsed["simulation_created"] is False and parsed["weights_loaded"] is False
