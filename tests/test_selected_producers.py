"""Fake native seams test the selected producer budgets and state composition."""
import hashlib
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


TASK = "frypan_stove9"


def fake_builder(monkeypatch, module, tmp_path):
    from benchmark.remaining_goals.build import _write, HOLD
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.validation import validate_candidate, RGB_QUANTIZATION_AUDIT
    from tests.test_headless_source_acceptance import SyntheticAudit, observation
    calls = {"steps": 0, "audits": [], "profiles": []}
    env = SimpleNamespace(state=np.array([0., .4, 0., 0.]), sim=SimpleNamespace(model=object()))
    env.seed = lambda seed: calls.update(seed=seed)
    env.close = lambda: calls.update(closed=True)
    env.env = SimpleNamespace(parsed_problem={"goal_state": [["on", "akita_black_bowl_1", "plate_1"], ["turnon", "flat_stove_1"]]})
    from benchmark.remaining_goals.task_catalog import TASKS
    profile = TASKS[TASK]
    env.env.parsed_problem["goal_state"] = [p for g in profile["goals"] for p in g["predicates"]]
    bddl = tmp_path / "task.bddl"
    bddl.write_text("official fake fixture")

    def restore(env, state):
        env.state = np.asarray(state).copy()

    def step(env, action):
        assert list(action) == [0, 0, 0, 0, 0, 0, -1]
        calls["steps"] += 1
        env.state[0] += .05
        env.state[3] += .00001

    def per_goal(env, base, selected_profile, limit):
        calls["profiles"].append(selected_profile)
        assert len(selected_profile["goals"]) == 1
        state = base.copy()
        state[2] = 1.
        return [[{"state": state, "allowed_indices": [2], "diagnostics": {"fixture": True}}]]

    def audit(env, state, episode, output, relative, **kwargs):
        calls["audits"].append(kwargs)
        class ThresholdAudit(SyntheticAudit):
            def validation_snapshot(self):
                value = super().validation_snapshot()
                value["goals"] = [bool(v > .5) for v in self.state[2:]]
                return value
        evidence = validate_candidate(ThresholdAudit(state), episode, steps=kwargs["validation_steps"],
                                      hold_action=HOLD, **RGB_QUANTIZATION_AUDIT)
        episode["initial_observation"] = save_observation_artifact(output, str(relative / "initial_observation.npz"),
                                                                  observation(state))
        _write(output / relative / "audit.json", evidence)
        return {"technical_acceptance": evidence["technical_acceptance"], "audit_path": str(relative / "audit.json")}

    fake = SimpleNamespace(
        _write=_write, HOLD=HOLD, create_scene=lambda *a, **kw: (env, SimpleNamespace(name=profile["name"], language=re.split(r"SCENE\d+_", profile["name"])[1].replace("_", " ")), bddl),
        environment_identity=lambda _: {"name": "libero", "fingerprint": "fake"},
        _official_initial_states=lambda suite, index: [np.array([0., .4, 0., 0.])] * 10,
        reset_scene=lambda env: None, model_xml_hash=lambda env: "b" * 64,
        restore_raw_state=restore, _step=step, _state=lambda env: env.state.copy(),
        _goals=lambda env, goals: [env.state[2] > .5, False], _per_goal=per_goal,
        combine_goal_candidates=lambda base, model, goals, mask, **kw: goals[0],
        state_diff_whitelist=lambda base, state, model, indices: {"valid": all(base[i] == state[i] for i in range(len(base)) if i not in indices)},
        _audit_state=audit,
        ms=SimpleNamespace(StateLayout=SimpleNamespace(from_model=lambda model: None), get_robot_qpos=lambda state, layout, n: state[1:2]),
    )
    suite = SimpleNamespace(n_tasks=1, get_task=lambda i: SimpleNamespace(name=profile["name"]))
    monkeypatch.setattr(module, "_backend", lambda: fake)
    monkeypatch.setattr(module, "_suite", lambda profile: suite)
    monkeypatch.setattr(module, "_official_asset", lambda *args: {"asset": "fake.init", "sha256": "f" * 64})
    return fake, calls


def test_selected_builder_only_searches_A_and_keeps_outside_whitelist(monkeypatch, tmp_path):
    module = importlib.import_module("benchmark.remaining_goals.selected_build")
    _, calls = fake_builder(monkeypatch, module, tmp_path)
    result = module.build(tmp_path / "out", task=TASK, index=9)
    manifest = json.loads((tmp_path / "out/manifest.candidates.json").read_text())
    assert result["complete"] is True
    assert calls["seed"] == 9 and calls["steps"] == 160
    assert [a["validation_steps"] for a in calls["audits"]] == [150]
    assert [g["id"] for g in calls["profiles"][0]["goals"]] == ["stove_on"]
    assert len(manifest["episodes"]) == 1 and manifest["episodes"][0]["initial_mask"] == [True, False]
    episode = manifest["episodes"][0]
    state = np.load(tmp_path / "out" / episode["state_path"], allow_pickle=False)
    assert state[0] == pytest.approx(4.) and state[3] == pytest.approx(.0008)
    assert episode["construction"]["method"] == "selected_A_only_settle_component_transplant_v1"
    assert "components_exactly_matched" not in episode["construction"]


def test_normal00_has_settle80_initial_only_and_bound_provenance(monkeypatch, tmp_path):
    module = importlib.import_module("benchmark.remaining_goals.selected_build")
    _, calls = fake_builder(monkeypatch, module, tmp_path)
    result = module.build(tmp_path / "out", task=TASK, index=4, protocol="normal00-control")
    manifest = json.loads((tmp_path / "out/manifest.candidates.json").read_text())
    episode = manifest["episodes"][0]
    group = result["groups"][0]
    assert calls["steps"] == 80 and calls["profiles"] == []
    assert [a["validation_steps"] for a in calls["audits"]] == [0]
    assert result["kind"] == "normal00_initialization_v1"
    assert result["settle_steps"] == 80 and result["initialization_kind"] == "settled_base"
    assert episode["initial_mask"] == [False, False]
    assert group["state_sha256"] == episode["state_sha256"]
    assert group["initial_observation_sha256"] == episode["initial_observation"]["sha256"]
    assert group["base_state_array_sha256"] == hashlib.sha256(np.load(tmp_path / "out" / episode["state_path"]).astype("<f8").tobytes()).hexdigest()


@pytest.mark.parametrize("task,index,protocol", [("basket", 0, "selected-mask10"), (TASK, 10, "selected-mask10"), (TASK, 0, "invalid")])
def test_builder_rejects_wrong_scope_before_backend(monkeypatch, tmp_path, task, index, protocol):
    module = importlib.import_module("benchmark.remaining_goals.selected_build")
    monkeypatch.setattr(module, "_backend", lambda: pytest.fail("native backend imported"))
    with pytest.raises(ValueError):
        module.build(tmp_path / "out", task=task, index=index, protocol=protocol)


def test_replay_uses_original_manifest_selected_episode_and_exact_2x150(monkeypatch, tmp_path):
    module = importlib.import_module("benchmark.remaining_goals.selected_replay")
    from benchmark.remaining_goals.build import _write, HOLD
    from benchmark.remaining_goals.validation import RGB_QUANTIZATION_AUDIT, RGB_QUANTIZATION_LIMITATION, RGB_QUANTIZATION_RULE
    from benchmark.remaining_goals.headless import selected_preparation as preparation
    manifest_path = tmp_path / "original.json"
    manifest_path.write_text('{"original":"all masks including failures"}')
    episode = {"episode_id": "exact_old_id", "initial_mask": [True, False], "model_xml_sha256": "b" * 64,
               "construction": {"legal": False}}
    manifest = {"environment": {"name": "libero", "fingerprint": "fake"}, "content_hash": "c" * 64}
    candidate = {"episode": episode, "manifest": manifest, "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                 "source_content_hash": manifest["content_hash"]}
    state_path = tmp_path / "saved.npy"
    np.save(state_path, np.array([0., .4, 1., 0.]))
    episode["state_sha256"] = hashlib.sha256(state_path.read_bytes()).hexdigest()
    episode["initial_observation"] = {"observation_sha256": "e" * 64}
    calls = []
    class Adapter:
        def __init__(self, config):
            assert config["manifest_dir"] == str(tmp_path)
        def close(self):
            calls.append("close")
    class Wrapper:
        def __init__(self, *args, **kwargs):
            self.reset_checks = {"saved_state_exact": True}
            self.reset_observation_comparison = {}
            self.reset_initial_observation = {}
            self.post_restore_xml_sha256 = "d" * 64
    def validate(wrapper, actual, **kwargs):
        assert actual is episode
        calls.append(kwargs)
        return {"technical_acceptance": True, "checks": {}, "error": None}
    fake = SimpleNamespace(_write=_write, HOLD=HOLD, LiberoGoalEnv=Adapter, ReplayAuditEnv=Wrapper,
                           verify_state_file=lambda e, root: state_path, validate_candidate=validate,
                           RGB_QUANTIZATION_AUDIT=RGB_QUANTIZATION_AUDIT,
                           RGB_QUANTIZATION_LIMITATION=RGB_QUANTIZATION_LIMITATION, RGB_QUANTIZATION_RULE=RGB_QUANTIZATION_RULE)
    monkeypatch.setattr(module, "_backend", lambda: fake)
    monkeypatch.setattr(module, "_candidate", lambda *args: candidate)
    # Production preflight owns typed observation validation; give its exact
    # already-verified construction observation hash at this seam.
    candidate["construction"] = {"initial_observation_sha256": "e" * 64}
    result = module.replay(manifest_path, tmp_path / "out", task=TASK, index=6)
    assert len(result["episodes"]) == 2
    assert [row["repetition"] for row in result["episodes"]] == [0, 1]
    assert [call["steps"] for call in calls[:-1]] == [150, 150]
    assert result["source_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert manifest_path.read_text() == '{"original":"all masks including failures"}'


def test_control_ledger_counts_caught_step_exception_as_unknown(tmp_path):
    module = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
    owner = SimpleNamespace()
    def step(fail=False):
        if fail:
            raise ValueError("physics may already have advanced")
    owner.step = step
    def run():
        owner.step()
        try:
            owner.step(True)
        except ValueError:
            pass
        owner.step()
    _, result = module._run_counted(run, owner, "step", tmp_path / "ledger.json", {"operation": "replay"})
    assert result["attempted"] == 3 and result["completed"] == 2 and result["exception_calls"] == 1
    assert result["actual_control_steps"] is None and result["count_status"] == "partial_unknown"
    assert owner.step is step and result["hook_restored"]


def test_new_normal_producer_roundtrips_real_file_acceptance(monkeypatch, tmp_path):
    module = importlib.import_module("benchmark.remaining_goals.selected_build")
    from benchmark.remaining_goals.headless.scoped_sources import resolve_source
    fake_builder(monkeypatch, module, tmp_path)
    output = tmp_path / "normal"
    module.build(output, task=TASK, index=4, protocol="normal00-control")
    mp, ip = output / "manifest.candidates.json", output / "construction_report.json"
    manifest = json.loads(mp.read_text())
    origin = {"manifest": str(mp), "manifest_sha256": hashlib.sha256(mp.read_bytes()).hexdigest(), "content_hash": manifest["content_hash"],
              "initialization": str(ip), "initialization_sha256": hashlib.sha256(ip.read_bytes()).hexdigest()}
    plan = resolve_source("normal00-control", TASK, 4, origin)
    assert plan["status"] == "ready"
    assert plan["source_acceptance"]["episodes"][0]["construction"]["steps"] == 0


def test_new_selected_producer_and_formal_replay_roundtrip_file_acceptance(monkeypatch, tmp_path):
    builder = importlib.import_module("benchmark.remaining_goals.selected_build")
    replay = importlib.import_module("benchmark.remaining_goals.selected_replay")
    from benchmark.remaining_goals import replay_candidates as backend
    from benchmark.remaining_goals.headless.scoped_sources import resolve_source, inspect_candidate
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.validation import compare_observations, RGB_QUANTIZATION_AUDIT
    from tests.test_headless_source_acceptance import SyntheticAudit, observation
    fake_builder(monkeypatch, builder, tmp_path)
    output = tmp_path / "selected"
    builder.build(output, task=TASK, index=2)
    mp = output / "manifest.candidates.json"
    candidate = inspect_candidate(TASK, 2, mp)
    assert candidate["construction"]["steps"] == 150
    class Adapter:
        def __init__(self, config): pass
        def close(self): pass
    class Wrapper(SyntheticAudit):
        def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir):
            super().__init__(state)
            self.frames_dir = frames_dir
            self.reset_checks = {"saved_state_exact": True, "initial_mask_exact": True,
                                 "construction_observation_matches": True, "initial_non_rgb_exact": True}
            self.reset_observation_comparison = compare_observations(observation(state), observation(state), atol=0,
                require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
            self.reset_initial_observation = save_observation_artifact(frames_dir, "initial_observation.npz", observation(state))
            self.post_restore_xml_sha256 = "d" * 64
        def validation_snapshot(self):
            value = super().validation_snapshot()
            value["goals"] = [bool(v > .5) for v in self.state[2:]]
            return value
    monkeypatch.setattr(backend, "LiberoGoalEnv", Adapter)
    monkeypatch.setattr(backend, "ReplayAuditEnv", Wrapper)
    rp = tmp_path / "replay"
    report = replay.replay(mp, rp, task=TASK, index=2)
    assert report["technical_acceptance"] is True
    origin = {"manifest": str(mp), "manifest_sha256": hashlib.sha256(mp.read_bytes()).hexdigest(),
              "content_hash": candidate["source_content_hash"], "candidate_replay": str(rp / "replay_report.json"),
              "replay_sha256": hashlib.sha256((rp / "replay_report.json").read_bytes()).hexdigest()}
    plan = resolve_source("selected-mask10", TASK, 2, origin)
    assert plan["status"] == "ready"
    assert len(plan["source_acceptance"]["episodes"][0]["replays"]) == 2
