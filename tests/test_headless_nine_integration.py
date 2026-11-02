"""Real file/adapter contracts with synthetic physics and CPU policy doubles.

No native simulator, research model, GPU or video encoder is invoked. Source
production, audits, acceptance, archival, planning, runtime ledgers and offline
geometry/evidence checks use their production implementations.
"""
from copy import deepcopy
import hashlib
import json
import re
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import selected_build, selected_replay, replay_candidates
from benchmark.remaining_goals.build import HOLD, _write
from benchmark.remaining_goals.nine_catalog import NEW_TASKS, FACT_FIELDS, get_task, read_goal_facts
from benchmark.remaining_goals.observation_artifact import save_observation_artifact, load_observation_artifact
from benchmark.remaining_goals.validation import validate_candidate, compare_observations, RGB_QUANTIZATION_AUDIT
from benchmark.remaining_goals.headless import environment, nine_planning, nine_workflow, workflow
from benchmark.remaining_goals.headless.scoped_sources import resolve_source, archive_source
from tests.test_headless_nine_planning import configuration033
from tests.test_headless_workflow import execution
from tests.test_headless_source_acceptance import tree_hash
from tests.test_headless_runner import observation
from tests.test_remaining_oft_transfer import configs
from tests import test_headless_environment as native_fixtures


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_observation(state):
    return observation(int(state[2]) + 2 * int(state[3]))


def _source_facts(state, semantics):
    profile = get_task(semantics["task_key"])
    active = {tuple(g["predicates"][0]): bool(state[i + 2] > .5) for i, g in enumerate(profile["goals"])}
    def evaluate(predicate):
        if predicate[0] in ("open", "turnon"):
            return True
        return active[tuple(predicate)]
    return read_goal_facts(evaluate, bool(all(state[2:] > .5)), semantics)


class SourceAudit:
    def __init__(self, state, semantics):
        self.start, self.semantics = state.copy(), semantics

    def restore_candidate(self, episode):
        self.state = self.start.copy()
        return _source_observation(self.state)

    def step(self, action):
        assert list(action) == HOLD.tolist()
        self.state[0] += .05
        return _source_observation(self.state)

    def validation_snapshot(self):
        return {"state": self.state.copy(), "state_before_refresh": self.state.copy(), "qvel": [0.],
                "robot_qpos": [self.state[1]], "object_positions": {"target_a": [self.state[2], 0., 0.],
                "target_b": [self.state[3], 0., 0.]}, "penetrations": [],
                "fresh_observation": _source_observation(self.state), **_source_facts(self.state, self.semantics)}


def make_nine_source(directory, monkeypatch, task, protocol):
    """Run the actual selected producer and file readers with a physics seam."""
    directory.mkdir(parents=True)
    profile = get_task(task)
    bddl = directory / "official.bddl"
    bddl.write_text("synthetic official task fixture: " + profile["name"])
    env = SimpleNamespace(state=np.array([0., .4, 0., 0.]), sim=SimpleNamespace(model=object()))
    env.seed = lambda value: None
    env.close = lambda: None
    env.env = SimpleNamespace(parsed_problem={"goal_state": list(reversed(profile["official_goal_predicates"]))})
    def evaluate(predicate):
        if predicate[0] in ("open", "turnon"): return True
        index = next(i for i, g in enumerate(profile["goals"]) if g["predicates"][0] == predicate)
        return bool(env.state[index + 2] > .5)
    env.env._eval_predicate = evaluate
    env.check_success = lambda: all(evaluate(p) for p in profile["official_goal_predicates"])
    calls = {"settle_steps": 0, "audit_steps": []}
    def restore(env, state): env.state = state.copy()
    def step(env, action):
        calls["settle_steps"] += 1
        env.state[0] += .05
    def per_goal(env, base, active, limit):
        assert len(active["goals"]) == 1
        if task == "two_pots":
            assert active["reservation_objects"]["flat_stove_1_cook_region"] == ["moka_pot_1", "moka_pot_2"]
        state = base.copy(); state[2] = 1.
        return [[{"state": state, "allowed_indices": [2], "diagnostics": {"synthetic_candidate": True}}]]
    def audit(env, state, episode, output, relative, **options):
        calls["audit_steps"].append(options["validation_steps"])
        result = validate_candidate(SourceAudit(state, episode["task_semantics"]), episode,
            steps=options["validation_steps"], hold_action=HOLD, **RGB_QUANTIZATION_AUDIT)
        episode["initial_observation"] = save_observation_artifact(output, str(relative / "initial_observation.npz"), _source_observation(state))
        _write(output / relative / "audit.json", result)
        return {"technical_acceptance": result["technical_acceptance"]}
    official = SimpleNamespace(name=profile["name"], language=re.split(r"SCENE\d+_", profile["name"])[1].replace("_", " "))
    backend = SimpleNamespace(_write=_write, HOLD=HOLD, create_scene=lambda *a, **k: (env, official, bddl),
        environment_identity=lambda freq: {"name": "libero", "fingerprint": "cpu-synthetic-nine"},
        _official_initial_states=lambda *a: [np.array([0., .4, 0., 0.])] * 10,
        reset_scene=lambda env: None, model_xml_hash=lambda env: "b" * 64,
        restore_raw_state=restore, _step=step, _state=lambda env: env.state.copy(),
        _goals=lambda env, goals: [evaluate(g["predicates"][0]) for g in goals], _per_goal=per_goal,
        combine_goal_candidates=lambda base, model, goals, mask, **kw: goals[0],
        state_diff_whitelist=lambda base, state, model, indices: {"valid": all(base[i] == state[i] for i in range(len(base)) if i not in indices)},
        _audit_state=audit, ms=SimpleNamespace(StateLayout=SimpleNamespace(from_model=lambda m: None),
            get_robot_qpos=lambda state, layout, n: state[1:2]))
    monkeypatch.setattr(selected_build, "_backend", lambda: backend)
    monkeypatch.setattr(selected_build, "_suite", lambda p: SimpleNamespace(n_tasks=10,
        get_task=lambda i: official if i == p["official_task_id"] else SimpleNamespace(name="other")))
    monkeypatch.setattr(selected_build, "_official_asset", lambda *a: {"asset": "synthetic.init", "sha256": "f" * 64})
    out = directory / "build"
    result = selected_build.build(out, task=task, index=0, protocol=protocol)
    assert result["complete"], result
    normal = protocol == "nine-normal00"
    assert calls == {"settle_steps": 80 if normal else 160, "audit_steps": [0 if normal else 150]}
    manifest_path = out / "manifest.candidates.json"
    manifest = json.loads(manifest_path.read_text())
    origin = {"manifest": str(manifest_path), "manifest_sha256": _sha(manifest_path), "content_hash": manifest["content_hash"]}
    if normal:
        report = out / "construction_report.json"
        origin.update(initialization=str(report), initialization_sha256=_sha(report))
    else:
        semantics = manifest["episodes"][0]["task_semantics"]
        class Adapter:
            def __init__(self, config): pass
            def close(self): pass
        class Replay(SourceAudit):
            def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir):
                super().__init__(state, semantics)
                self.reset_checks = {"saved_state_exact": True, "initial_mask_exact": True,
                    "construction_observation_matches": True, "initial_non_rgb_exact": True}
                self.reset_observation_comparison = compare_observations(_source_observation(state), _source_observation(state),
                    atol=0, require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
                self.reset_initial_observation = save_observation_artifact(frames_dir, "initial_observation.npz", _source_observation(state))
                self.post_restore_xml_sha256 = "c" * 64
        monkeypatch.setattr(replay_candidates, "LiberoGoalEnv", Adapter)
        monkeypatch.setattr(replay_candidates, "ReplayAuditEnv", Replay)
        replay_dir = directory / "replay"
        result = selected_replay.replay(manifest_path, replay_dir, task=task, index=0, protocol=protocol)
        assert result["technical_acceptance"] and result["steps"] == 150 and result["repeats"] == 2
        report = replay_dir / "replay_report.json"
        origin.update(candidate_replay=str(report), replay_sha256=_sha(report))
    plan = resolve_source(protocol, task, 0, origin)
    archive_source(directory / "archive_check", plan)
    return origin


class NineGeometryEnv:
    def __init__(self, config):
        self.config, self.steps, self.actions, self.closed = config, 0, [], 0

    def reset(self, source):
        self.source, self.steps = deepcopy(source), 0
        self.native = native_fixtures.FakeNative(source["task_id"])
        self.measurements = environment.HeadlessMeasurements(self.native, source["task_id"],
            source_reset_model_xml_sha256=source["model_xml_sha256"], task_semantics=source["task_semantics"])
        if self.config["protocol"] == "nine-normal00":
            # Real geometry observer reports target held. Native00 still ends
            # at official success; no synthetic release certificate is injected.
            self.native.grasped.update(name + "_geom" for name in self.measurements.roles["movable_targets"])
        return load_observation_artifact(self.config["manifest_dir"], source["initial_observation"])

    def measurement_static(self):
        return self.measurements.measurement_static()

    def evaluator_state(self):
        profile = get_task(self.source["task_id"])
        active = [self.source["initial_mask"][0] or self.steps >= 1, self.steps >= 2]
        for value, goal in zip(active, profile["goals"]):
            self.native.relations[tuple(goal["predicates"][0])] = value
        for predicate in profile["invariant_predicates"]:
            self.native.relations[tuple(predicate)] = True
        for predicate in profile["required_open_predicates"]:
            self.native.relations[tuple(predicate)] = self.steps < 2
        facts = read_goal_facts(self.native.env._eval_predicate, all(active), self.source["task_semantics"])
        return self.measurements.evaluator_state(active, goal_facts=facts)

    def step(self, action):
        self.actions.append(action.copy())
        self.steps += 1
        self.native.steps += 1
        self.native.sim.data.site_xpos[0] = [self.steps / 100, 0, 0]
        return observation(self.steps)

    def close(self):
        self.closed += 1


@pytest.mark.parametrize("protocol", ["nine-normal00", "nine-mask10"])
def test_new_three_source_archive_plan_rollout_evidence_and_inspection(tmp_path, monkeypatch, protocol):
    from benchmark.remaining_goals import cli
    monkeypatch.setattr(cli, "_source_hash", lambda: "d" * 64)
    monkeypatch.setattr(environment, "_callback_status", lambda: "absent")
    config = configuration033(tmp_path / "config", monkeypatch, protocol)
    fake_model = tmp_path / "cpu_model_fixture"
    fake_model.mkdir()
    runtime, _ = configs(fake_model)
    workflow.write_json(config.parent / "runtime.json", runtime, update=True)
    source_inventory = nine_planning.sources_template(protocol)
    for task in NEW_TASKS:
        origin = make_nine_source(tmp_path / "sources" / task, monkeypatch, task, protocol)
        next(row for row in source_inventory["entries"] if row["task_id"] == task and row["initial_state_index"] == 0)["origin"] = origin
        profile = get_task(task)
        monkeypatch.setitem(native_fixtures.TASKS, task, {**profile,
            "goals": profile["goals"] + [{"predicates": profile["invariant_predicates"]}]})
    workflow.write_json(config.parent / "sources.json", source_inventory, update=True)
    original = tree_hash(tmp_path / "sources")
    plan = nine_planning.validate_plan(nine_planning.dry_plan(config))
    assert plan["ready_episodes"] == 3 and len(plan["selected_episode_ids"]) == 30
    assert sum(row["status"] == "reuse_only" for row in plan["sources"]) == 60
    made, _ = execution(monkeypatch)
    envs = []
    def make_environment(options):
        assert options["protocol"] == protocol
        value = NineGeometryEnv(options); envs.append(value)
        return value
    monkeypatch.setattr(workflow, "make_environment", make_environment)
    out = tmp_path / "run"
    batch = nine_workflow.run_batch(config, out, allow_missing=True)
    bits = "00" if protocol == "nine-normal00" else "10"
    for task in NEW_TASKS:
        name = f"{task}_s000_{bits}"
        assert batch["episodes"][name]["status"] == "completed", batch["episodes"][name]
        raw = json.loads((out / "episodes" / name / "raw" / (name + ".json")).read_text())
        assert raw["n_steps"] == (2 if bits == "00" else 6)
        assert raw["exit_reason"] == ("official_success" if bits == "00" else "goal_confirmed")
        assert raw["trace"][-1]["released"] is (False if bits == "00" else True)
        assert raw["official_goals_achieved"] is True
        assert raw["execution_evidence"]["status"] == "recorded"
        assert raw["video"]["status"] == "saved"
        assert raw["video"]["frame_steps"] == list(range(raw["n_steps"] + 1))
        assert all(not set(FACT_FIELDS) & set(value) for value, _ in made[0].inputs)
    assert len(envs) == 3 and len(made) == 1 and made[0].calls == made[0].resets == 3
    assert all(e.closed == 1 for e in envs)
    report = nine_workflow.inspect_batch(out)
    assert report["artifact_issues"] == [], report["artifact_issues"]
    condition = report["conditions"][bits]
    assert condition["expected"] == 90 and condition["observed"] == 3
    assert condition["official_task_SR"] == {"numerator": 3, "denominator": 3, "percent": 100.0}
    assert condition["classification_counts"]["success"] == 3
    assert condition["classification_counts"]["missing"] == 87
    assert tree_hash(tmp_path / "sources") == original
    saved_episodes = tree_hash(out / "episodes")
    nine_workflow.run_batch(config, out, allow_missing=True, continue_run=True)
    assert made[0].calls == 3 and len(envs) == 3
    assert tree_hash(out / "episodes") == saved_episodes
    assert nine_workflow.inspect_batch(out)["artifact_issues"] == []
