"""CPU/file-only integration for the bounded evaluator diagnostic.

The injected environment and recorder below are synthetic. They do not certify
native replay, geometry, release, or a new policy outcome.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pytest

from benchmark.remaining_goals.finish import release_audit as audit
from benchmark.remaining_goals.pilot_evidence import observation_sha256


TARGETS = ("alphabet_soup_1", "tomato_sauce_1")


def observation(step):
    return {"agentview_image": np.full((2, 3, 3), step % 256, np.uint8),
            "robot0_eye_in_hand_image": np.full((3, 2, 3), (step + 17) % 256, np.uint8),
            "proprio": np.array([step, -0., .25, -.5, 1., 0., .01, -.01], np.float64)}


def physical_truth(step):
    complete = step >= 263
    uncertain = 263 <= step <= 291
    facts = {}
    for index, name in enumerate(TARGETS):
        unknown = uncertain and index == 1
        facts[name] = {"role": "target", "in_basket": complete,
            "released": None if unknown else True,
            "release_evidence": {"method": "synthetic-release-evidence",
                "clearance_margin_m": .002, "dual_pad_grasp": False, "any_gripper_contact": False,
                "hand_sphere_clearance_m": -.02343 if unknown else .03,
                "pinch_capsule_clearance_m": .01468,
                "reason": "near_hand_or_inside_pinch_envelope" if unknown else
                    "no_contact_and_clear_of_hand_and_pinch_envelope"}}
    return {"goals": [complete, complete], "released": None if uncertain else True,
            "objects": facts,
            "release_evidence": {"method": "synthetic-release-evidence",
                "targets": {key: deepcopy(value["release_evidence"]) for key, value in facts.items()}}}


def action_rows(count=292):
    # Include signed zero and non-round decimal values: numerical equality alone
    # would miss changes to the original decoded float64 action bytes.
    actions = np.zeros((count, 7), dtype=np.float64)
    actions[:, 0] = np.linspace(-.5, .5, count)
    actions[:, 1] = -0.
    actions[:, 2] = np.nextafter(.25, 1.)
    actions[:, 3] = np.nextafter(0., 1.)
    actions[:, 4] = -.125
    actions[:, 5] = .3333333333333333
    actions[:, 6] = np.where(np.arange(count) % 2, 1., -1.)
    actions.setflags(write=False)
    return actions


def make_context(tmp_path):
    source, bank = tmp_path / "source", tmp_path / "bank"
    source.mkdir()
    bank.mkdir()
    (source / "raw.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    (bank / "normal_bank.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    actions = action_rows()
    events = [{"step": step, "action": actions[step - 1].tolist(), "action_kind": "policy",
               "hold_cause": None, "query_sequence": (step - 1) // 8 + 1,
               "chunk_index": (step - 1) % 8} for step in range(1, 293)]
    queries = {step: {"sequence": step // 8 + 1, "observation_step": step,
                     "observation_sha256": observation_sha256(observation(step)), "status": "valid"}
               for step in range(0, 289, 8)}
    trace = [{**physical_truth(0), "step": 0, "action": None, "action_kind": "initial",
              "hold_cause": None, "query_sequence": None, "chunk_index": None}]
    trace.extend({**physical_truth(event["step"]), **deepcopy(event)} for event in events)
    episode = {"episode_id": "basket_s035_00", "initial_state_index": 35, "initial_mask": [False, False],
               "seed": 35, "state_sha256": "a" * 64, "model_xml_sha256": "b" * 64,
               "bddl_sha256": "c" * 64, "instruction": "put both original objects in the basket"}
    plan = {"schema_version": "remaining-release-observability-plan-v1", "plan_sha256": "d" * 64,
            "source_run": str(source), "source_bank": str(bank / "normal_bank.json"),
            "protected_roots": [str(source), str(bank)], "max_action_steps": 292,
            "episode_id": episode["episode_id"], "synthetic": True}
    return {"plan": plan, "metadata": {"run_id": "synthetic-readonly-replay"}, "episode": episode,
            "source_result": {"executed_actions": events, "queries": list(queries.values()), "trace": trace},
            "environment_config": {"synthetic": True}, "actions": actions, "query_by_step": queries,
            "trace": trace, "initial_observation": observation(0),
            "initial_observation_sha256": observation_sha256(observation(0)),
            "state": np.array([0., 35., -.0], dtype=np.float64)}


def tree_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


class FakeMonitor:
    def __init__(self, calls):
        self.calls, self.backend = calls, object()
        self.phase = None

    def __enter__(self):
        self.calls.append(("monitor_enter",))
        return self

    def __exit__(self, *args):
        self.calls.append(("monitor_exit",))

    def set_phase(self, phase):
        self.phase = phase
        self.calls.append(("phase", phase))

    def summary(self):
        return {"test_only": True, "native_certified": False, "calls": []}


class FakeEnvironment:
    def __init__(self, calls, *, fail=None, mismatch=None):
        self.calls, self.fail, self.mismatch = calls, fail, mismatch
        self.steps = self.resets = self.closes = self.evaluations = 0
        self.actions = []

    def reset(self, episode):
        self.resets += 1
        self.calls.append(("reset", episode["episode_id"]))
        if self.fail == "reset":
            raise RuntimeError("synthetic reset failure")
        return self._observation()

    def _observation(self):
        result = observation(self.steps)
        if self.mismatch == ("observation", self.steps):
            result["proprio"][0] += .5
        return result

    def evaluator_state(self):
        self.evaluations += 1
        self.calls.append(("truth", self.steps))
        if self.fail == ("evaluator", self.steps):
            raise RuntimeError("synthetic evaluator failure")
        result = physical_truth(self.steps)
        if self.mismatch is not None and self.mismatch[1] == self.steps:
            kind = self.mismatch[0]
            if kind == "goals":
                result["goals"][0] = not result["goals"][0]
            elif kind == "released":
                result["objects"][TARGETS[1]]["released"] = False
            elif kind in {"dual_pad_grasp", "any_gripper_contact"}:
                result["objects"][TARGETS[1]]["release_evidence"][kind] = True
            elif kind == "clearance":
                facts = result["objects"][TARGETS[1]]["release_evidence"]
                facts["hand_sphere_clearance_m"] = np.nextafter(facts["hand_sphere_clearance_m"], 1.).item()
        return result

    def step(self, action):
        next_step = self.steps + 1
        self.calls.append(("step", next_step))
        if self.fail == ("step", next_step):
            raise RuntimeError("synthetic step failure")
        if self.fail == ("interrupt", next_step):
            raise KeyboardInterrupt("synthetic user interruption")
        assert action.dtype == np.float64 and action.shape == (7,)
        self.actions.append(action.copy())
        self.steps = next_step
        if self.fail == ("mutate_action", next_step):
            action[1] = 0.  # Signed-zero mutation must be detected after return.
        if self.fail == ("last_action", next_step):
            self._last_action = action.astype(np.float32)
        return self._observation()

    def begin_hold(self):
        pytest.fail("bounded prefix must never begin hold")

    def hold_action(self):
        pytest.fail("bounded prefix must never compute hold")

    def close(self):
        self.closes += 1
        self.calls.append(("env_close",))
        if self.fail == "close":
            raise RuntimeError("synthetic environment close failure")


class FakeRecorder:
    def __init__(self, env, out, *, backend=None, calls, fail=None):
        self.env, self.out, self.backend, self.calls, self.fail = env, Path(out), backend, calls, fail
        self.snapshots, self.closes = [], 0

    def static(self):
        self.calls.append(("static",))
        if self.fail == "static":
            raise RuntimeError("synthetic static recorder failure")
        value = {"test_only": True, "native_certified": False,
                 "compiled_model_xml_sha256": "f" * 64 if self.fail == "static_xml" else
                     getattr(self.env, "compiled_model_xml_sha256", "b" * 64)}
        (self.out / "static.json").write_text(json.dumps(value), encoding="utf-8")
        return value

    def capture(self, step, *, action_kind, query_index=None, action=None, truth=None):
        self.calls.append(("capture", step))
        if self.fail == ("capture", step):
            raise RuntimeError("synthetic read-only recorder fingerprint mismatch")
        if self.fail == ("interrupt", step):
            raise KeyboardInterrupt("synthetic recorder interruption")
        self.snapshots.append({"step": step, "action_kind": action_kind, "query_index": query_index,
                               "action": None if action is None else action.copy(), "truth": deepcopy(truth)})
        # Deliberately tiny typed fake file, not a native INTEGRATION certificate.
        target = self.out / "native" / f"{step:04d}.npz"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            np.savez_compressed(stream, synthetic_state=np.array([step], dtype=np.float64))
        return {"path": target.relative_to(self.out).as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "test_only": True}

    def close(self):
        self.closes += 1
        self.calls.append(("recorder_close",))
        if self.fail == "close":
            raise RuntimeError("synthetic recorder close failure")


def run_fake(tmp_path, monkeypatch, *, fail=None, mismatch=None, recorder_fail=None, change_context=None):
    context = make_context(tmp_path)
    if change_context is not None:
        change_context(context)
    calls, recorders = [], []
    env = FakeEnvironment(calls, fail=fail, mismatch=mismatch)
    monkeypatch.setattr(audit, "load_plan", lambda path: context)
    original_observation = audit._observation
    def inspected_observation(raw):
        calls.append(("observation", int(raw["proprio"][0])))
        return original_observation(raw)
    monkeypatch.setattr(audit, "_observation", inspected_observation)
    def recorder_factory(env, out, *, backend):
        recorder = FakeRecorder(env, out, backend=backend, calls=calls, fail=recorder_fail)
        recorders.append(recorder)
        return recorder
    out = tmp_path / "diagnostic"
    before = {name: tree_bytes(Path(context["plan"][name]).parent if name == "source_bank" else Path(context["plan"][name]))
              for name in ("source_run", "source_bank")}
    report = audit.run(tmp_path / "plan/synthetic-plan.json", out, env_factory=lambda config: env,
                       recorder_factory=recorder_factory, monitor_factory=lambda: FakeMonitor(calls))
    for name in before:
        root = Path(context["plan"][name]).parent if name == "source_bank" else Path(context["plan"][name])
        assert tree_bytes(root) == before[name]
    return report, out, context, env, recorders, calls


def test_exact_prefix_preserves_float64_actions_and_query_boundaries(tmp_path, monkeypatch):
    python_rng, numpy_rng = random.getstate(), np.random.get_state()
    report, out, context, env, recorders, calls = run_fake(tmp_path, monkeypatch)
    assert report["status"] == "diagnostic_completed", report
    assert report["requested_action_steps"] == report["completed_action_steps"] == env.steps == 292
    assert report["snapshot_count"] == 293 and env.evaluations == 293
    assert env.resets == env.closes == recorders[0].closes == 1
    assert report["first_mismatch"] is None and not report["cleanup_errors"]
    assert report["forbidden_calls"] == {"vla_forward": 0, "head_inference": 0, "processor": 0}
    assert all(actual.dtype == np.float64 and actual.tobytes() == expected.tobytes()
               for actual, expected in zip(env.actions, context["actions"]))
    snapshots = recorders[0].snapshots
    assert [row["step"] for row in snapshots] == list(range(293))
    assert [(row["step"], row["query_index"]) for row in snapshots if row["query_index"] is not None] == [
        (step, step // 8 + 1) for step in range(0, 289, 8)]
    assert snapshots[-1]["query_index"] is None
    final = json.loads((out / "frames/0292.json").read_text(encoding="utf-8"))
    assert final["step"] == 292 and final["query_reference"] is None
    assert final["source_action"]["query_sequence"] == 37
    assert final["source_action"]["chunk_index"] == 3
    assert len(report["query_comparisons"]) == 37
    assert json.loads((out / "source_plan.json").read_text(encoding="utf-8")) == context["plan"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    files = {row["path"]: row for row in manifest["files"]}
    assert set(files) == set(tree_bytes(out)) - {"manifest.json"}
    for name, row in files.items():
        raw = (out / name).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    # Preserve the old runner's different reset vs post-step evaluation order.
    assert calls.index(("observation", 0)) < calls.index(("truth", 0)) < calls.index(("capture", 0))
    for step in range(1, 293):
        assert calls.index(("step", step)) < calls.index(("truth", step)) < calls.index(("observation", step))
        assert calls.index(("observation", step)) < calls.index(("capture", step))
    assert random.getstate() == python_rng
    actual_numpy_rng = np.random.get_state()
    assert actual_numpy_rng[0] == numpy_rng[0] and actual_numpy_rng[2:] == numpy_rng[2:]
    np.testing.assert_array_equal(actual_numpy_rng[1], numpy_rng[1])


@pytest.mark.parametrize("mismatch,step", [("observation", 0), ("observation", 8),
    ("goals", 7), ("released", 7), ("dual_pad_grasp", 7), ("any_gripper_contact", 7), ("clearance", 7)])
def test_first_mismatch_saves_current_sidecar_and_stops(tmp_path, monkeypatch, mismatch, step):
    report, out, _, env, recorders, _ = run_fake(tmp_path, monkeypatch, mismatch=(mismatch, step))
    assert report["status"] == "replay_mismatch", report
    assert report["first_mismatch"]["step"] == step
    assert report["first_mismatch"]["kind"] == ("observation" if mismatch == "observation" else "truth")
    assert env.steps == report["completed_action_steps"] == step
    assert report["snapshot_count"] == step + 1
    assert (out / "frames" / f"{step:04d}.json").is_file()
    assert env.closes == recorders[0].closes == 1


@pytest.mark.parametrize("field,value", [("action_kind", "hold"), ("query_sequence", 2),
                                        ("chunk_index", 0), ("hold_cause", "timeout")])
def test_source_action_phase_mismatch_stops_before_executing_bad_action(tmp_path, monkeypatch, field, value):
    def alter(context):
        context["source_result"]["executed_actions"][6][field] = value
    report, out, _, env, recorders, _ = run_fake(tmp_path, monkeypatch, change_context=alter)
    assert report["status"] == "replay_mismatch", report
    assert report["first_mismatch"]["kind"] == "action" and report["first_mismatch"]["step"] == 7
    assert report["completed_action_steps"] == env.steps == 6
    assert report["snapshot_count"] == 7
    assert not (out / "actions/0007.json").exists()
    assert env.closes == recorders[0].closes == 1


def test_cached_action_byte_mismatch_stops_before_executing(tmp_path, monkeypatch):
    def alter(context):
        changed = context["actions"].copy()
        changed[6, 1] = 0.
        changed.setflags(write=False)
        context["actions"] = changed
    report, _, _, env, _, _ = run_fake(tmp_path, monkeypatch, change_context=alter)
    assert report["status"] == "replay_mismatch"
    assert report["first_mismatch"]["step"] == 7
    assert report["first_mismatch"]["field"] == "action.bytes"
    assert env.steps == 6


@pytest.mark.parametrize("fault", ["mutate_action", "last_action"])
def test_environment_action_mutation_retains_completed_frame_and_stops(tmp_path, monkeypatch, fault):
    report, out, _, env, recorders, _ = run_fake(tmp_path, monkeypatch, fail=(fault, 4))
    assert report["status"] == "replay_mismatch", report
    assert report["first_mismatch"]["kind"] == "action" and report["first_mismatch"]["step"] == 4
    assert report["completed_action_steps"] == env.steps == 4
    assert report["snapshot_count"] == 5 and (out / "frames/0004.json").is_file()
    assert env.closes == recorders[0].closes == 1


@pytest.mark.parametrize("failure", ["reset", ("step", 4), ("evaluator", 4), ("interrupt", 4)])
def test_environment_failure_preserves_prefix_and_always_closes(tmp_path, monkeypatch, failure):
    report, out, _, env, recorders, _ = run_fake(tmp_path, monkeypatch, fail=failure)
    assert report["status"] == ("interrupted" if failure == ("interrupt", 4) else "technical_error"), report
    assert env.closes == 1
    assert all(recorder.closes == 1 for recorder in recorders)
    assert report["completed_action_steps"] == env.steps
    assert report["error"] is not None
    assert not (out / "frames/0005.json").exists()


@pytest.mark.parametrize("failure", ["static", "static_xml", ("capture", 0), ("capture", 4), ("interrupt", 4)])
def test_recorder_failure_is_technical_not_physical_unknown(tmp_path, monkeypatch, failure):
    report, _, _, env, recorders, _ = run_fake(tmp_path, monkeypatch, recorder_fail=failure)
    assert report["status"] == ("interrupted" if failure == ("interrupt", 4) else "technical_error"), report
    assert report["first_mismatch"] is None
    assert report["error"] is not None
    assert env.closes == recorders[0].closes == 1
    assert env.steps <= (4 if isinstance(failure, tuple) else 0)


@pytest.mark.parametrize("owner", ["env", "recorder"])
def test_cleanup_failure_does_not_claim_diagnostic_completed(tmp_path, monkeypatch, owner):
    report, _, _, env, recorders, _ = run_fake(tmp_path, monkeypatch,
        fail="close" if owner == "env" else None, recorder_fail="close" if owner == "recorder" else None)
    assert report["status"] == "technical_error", report
    assert report["completed_action_steps"] == 292 and report["snapshot_count"] == 293
    assert report["cleanup_errors"]
    assert env.closes == recorders[0].closes == 1


@pytest.mark.parametrize("error_type,status,exit_code", [
    (OSError, "technical_error", 2), (KeyboardInterrupt, "interrupted", 130)])
def test_manifest_failure_persists_failure_after_closing_resources(
        tmp_path, monkeypatch, capsys, error_type, status, exit_code):
    def short_prefix(context):
        context["plan"]["max_action_steps"] = 1
        context["actions"] = context["actions"][:1]
    def fail_manifest(output):
        raise error_type("synthetic final manifest failure")
    monkeypatch.setattr(audit, "_manifest", fail_manifest)
    report, out, _, env, recorders, calls = run_fake(
        tmp_path, monkeypatch, change_context=short_prefix)
    assert report["status"] == status and report["phase"] == "manifest", report
    assert report["interrupted"] is (error_type is KeyboardInterrupt)
    assert report["manifest"] is None
    assert "synthetic final manifest failure" in report["error"]
    assert report["completed_action_steps"] == 1 and report["snapshot_count"] == 2
    assert env.closes == recorders[0].closes == 1
    assert ("monitor_exit",) in calls
    assert not (out / "manifest.json").exists()
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == report
    # Exercise the CLI's actual result-to-exit-code mapping without a second run.
    monkeypatch.setattr(audit, "run", lambda *args, **kwargs: report)
    assert audit.main(["run", "--plan", "synthetic-plan.json", "--out", str(out)]) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize("failure", ["cleanup_phase", "exit", "summary"])
def test_monitor_cleanup_interruption_preserves_other_closes_and_exit130(
        tmp_path, monkeypatch, capsys, failure):
    def short_prefix(context):
        context["plan"]["max_action_steps"] = 1
        context["actions"] = context["actions"][:1]
    original_phase = FakeMonitor.set_phase
    original_exit = FakeMonitor.__exit__
    def set_phase(self, phase):
        original_phase(self, phase)
        if phase == "cleanup" and failure == "cleanup_phase":
            raise KeyboardInterrupt("synthetic monitor cleanup phase interruption")
    def exit_monitor(self, *args):
        original_exit(self, *args)
        if failure == "exit":
            raise KeyboardInterrupt("synthetic monitor exit interruption")
    def summary(self):
        self.calls.append(("monitor_summary",))
        if failure == "summary":
            raise KeyboardInterrupt("synthetic monitor summary interruption")
        return {"test_only": True, "native_certified": False, "calls": []}
    monkeypatch.setattr(FakeMonitor, "set_phase", set_phase)
    monkeypatch.setattr(FakeMonitor, "__exit__", exit_monitor)
    monkeypatch.setattr(FakeMonitor, "summary", summary)
    report, out, _, env, recorders, calls = run_fake(
        tmp_path, monkeypatch, change_context=short_prefix)
    assert report["status"] == "interrupted" and report["interrupted"] is True, report
    assert report["completed_action_steps"] == 1 and report["snapshot_count"] == 2
    assert len(report["cleanup_errors"]) == 1
    assert "KeyboardInterrupt" in report["error"]
    assert env.closes == recorders[0].closes == 1
    assert ("monitor_exit",) in calls and ("monitor_summary",) in calls
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == report
    assert (out / "manifest.json").is_file()
    monkeypatch.setattr(audit, "run", lambda *args, **kwargs: report)
    assert audit.main(["run", "--plan", "synthetic-plan.json", "--out", str(out)]) == 130
    assert json.loads(capsys.readouterr().out)["status"] == "interrupted"


def test_invalid_or_changed_plan_never_constructs_environment(tmp_path, monkeypatch):
    def changed(path):
        raise ValueError("source file hash changed since frozen plan")
    monkeypatch.setattr(audit, "load_plan", changed)
    def forbidden(*args, **kwargs):
        pytest.fail("source validation must happen before native construction")
    with pytest.raises(ValueError, match="hash changed"):
        audit.run(tmp_path / "plan.json", tmp_path / "run", env_factory=forbidden,
                  recorder_factory=forbidden, monitor_factory=forbidden)


def test_actual_file_plan_cli_and_runner_share_frozen_context_without_native(tmp_path, monkeypatch, capsys):
    from benchmark.remaining_goals.finish import release_audit_plan as planner
    from tests.test_release_audit_plan import make_source
    from tests.test_finish_workflow import FakeEnv as SourceEnvironment
    source = make_source(tmp_path / "inputs", monkeypatch)
    before = tree_bytes(source.parent)
    output = tmp_path / "plan"
    assert audit.main(["plan", "--source-run", str(source), "--episode-id", "basket_s035_00",
                       "--max-action-steps", "8", "--out", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "plan_ready"
    context = planner.load_plan(output / "plan.json")
    calls, recorders = [], []
    env = SourceEnvironment()
    env.compiled_model_xml_sha256 = context["episode"]["model_xml_sha256"]
    def factory(env, out, *, backend):
        item = FakeRecorder(env, out, backend=backend, calls=calls)
        recorders.append(item)
        return item
    report = audit.run(output / "plan.json", tmp_path / "run", env_factory=lambda _: env,
                       recorder_factory=factory, monitor_factory=lambda: FakeMonitor(calls))
    assert report["status"] == "diagnostic_completed", report
    assert report["completed_action_steps"] == 8 and report["snapshot_count"] == 9
    assert [row["observation_step"] for row in report["query_comparisons"]] == [0, 8]
    assert env.closed == recorders[0].closes == 1
    assert tree_bytes(source.parent) == before
    assert json.loads((tmp_path / "run/source_plan.json").read_text()) == context["plan"]


@pytest.mark.parametrize("target", ["raw", "settled_state", "query_input"])
def test_actual_plan_source_mutation_is_rejected_before_native_factory(tmp_path, monkeypatch, target):
    from benchmark.remaining_goals.finish import release_audit_plan as planner
    from tests.test_release_audit_plan import make_source
    source = make_source(tmp_path / "inputs", monkeypatch)
    plan_dir = tmp_path / "plan"
    frozen = planner.create_plan(source, "basket_s035_00", 292, plan_dir)
    paths = {"raw": source / "raw/0000.json", "query_input": source / "evidence/0000/query_0001.npz",
             "settled_state": Path(frozen["source_bank"]).parent / planner.STATE_PATH}
    changed = paths[target]
    changed.write_bytes(changed.read_bytes() + b"synthetic-after-plan-mutation")
    before = tree_bytes(source.parent)
    def forbidden(*args, **kwargs):
        pytest.fail("source mutation cannot launch a native component")
    out = tmp_path / "never_started"
    with pytest.raises(ValueError, match="source file bytes changed"):
        audit.run(plan_dir / "plan.json", out, env_factory=forbidden,
                  recorder_factory=forbidden, monitor_factory=forbidden)
    assert not out.exists() and tree_bytes(source.parent) == before


def test_existing_output_is_not_modified_or_resumed(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    monkeypatch.setattr(audit, "load_plan", lambda path: context)
    out = tmp_path / "exists"
    out.mkdir()
    (out / "retained.json").write_text('{"original":true}', encoding="utf-8")
    before = tree_bytes(out)
    def forbidden(*args, **kwargs):
        pytest.fail("existing output cannot start a new native run")
    with pytest.raises(FileExistsError):
        audit.run(tmp_path / "plan/plan.json", out, env_factory=forbidden,
                  recorder_factory=forbidden, monitor_factory=forbidden)
    assert tree_bytes(out) == before


@pytest.mark.parametrize("owner", ["source", "bank", "plan"])
def test_new_output_cannot_be_nested_in_protected_source_trees(tmp_path, monkeypatch, owner):
    context = make_context(tmp_path)
    monkeypatch.setattr(audit, "load_plan", lambda path: context)
    out = tmp_path / owner / "new_diagnostic"
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        audit.run(tmp_path / "plan/plan.json", out,
                  env_factory=lambda _: pytest.fail("protected output must fail before environment"))
    assert not out.exists() and tree_bytes(tmp_path) == before


@pytest.mark.parametrize("phase", ["monitor", "environment", "recorder"])
def test_setup_error_closes_only_resources_that_were_constructed(tmp_path, monkeypatch, phase):
    context = make_context(tmp_path)
    monkeypatch.setattr(audit, "load_plan", lambda path: context)
    calls = []
    env, monitor = FakeEnvironment(calls), FakeMonitor(calls)
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic setup failure")
    report = audit.run(tmp_path / "plan/plan.json", tmp_path / "run",
        env_factory=fail if phase == "environment" else lambda _: env,
        recorder_factory=fail,
        monitor_factory=fail if phase == "monitor" else lambda: monitor)
    assert report["status"] == "technical_error" and "setup failure" in report["error"]
    assert env.closes == (1 if phase == "recorder" else 0)
    assert (("monitor_exit",) in calls) == (phase != "monitor")


@pytest.mark.parametrize("arguments", [[], ["plan"], ["run"]])
def test_cli_help_never_imports_native_or_model_packages(arguments):
    script = '''import builtins, json, runpy, sys
real = builtins.__import__
blocked = {"mujoco", "mujoco_py", "libero", "robosuite", "torch", "transformers"}
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("help imported forbidden package: " + name)
    return real(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = ["release_audit", *json.loads(sys.argv[1]), "--help"]
try:
    runpy.run_module("benchmark.remaining_goals.finish.release_audit", run_name="__main__")
except SystemExit as error:
    assert error.code == 0, error.code
print("HELP_WITHOUT_NATIVE_OR_MODEL_IMPORTS")
'''
    result = subprocess.run([sys.executable, "-c", script, json.dumps(arguments)],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "HELP_WITHOUT_NATIVE_OR_MODEL_IMPORTS" in result.stdout
    if arguments == ["plan"]:
        assert all(flag in result.stdout for flag in ("--source-run", "--episode-id", "--max-action-steps", "--out"))
    elif arguments == ["run"]:
        assert "--plan" in result.stdout and "--out" in result.stdout
