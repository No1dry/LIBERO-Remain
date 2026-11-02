"""CPU-only contracts for the nine-task source protocol."""
from copy import deepcopy
import importlib

import pytest
from tests.test_remaining_construction import scene
from tests.test_remaining_libero_env import fake_libero


def catalog():
    return importlib.import_module("benchmark.remaining_goals.nine_catalog")


def episode(key):
    c = catalog()
    p = c.get_task(key)
    return {"task_id": key, "suite": p["suite"], "task_name": p["name"],
            "libero_task_id": p["official_task_id"], **c.episode_fields(key)}


def test_nine_catalog_has_exact_order_and_preserves_legacy():
    c = catalog()
    from benchmark.remaining_goals.task_catalog import TASKS
    assert [c.get_task(k)["official_task_id"] for k in c.NINE_TASKS] == [0, 1, 2, 3, 4, 6, 7, 8, 9]
    assert c.NEW_TASKS == ("bowl_drawer_close", "two_pots", "mug_microwave_close")
    assert len(c.REUSE_TASKS) == 6
    assert len(TASKS["two_pots"]["goals"]) == 3
    for key in c.NINE_TASKS:
        assert len(c.get_task(key)["goals"]) == 2
        assert c.get_task(key)["suite"] == "libero_10"
    with pytest.raises(ValueError):
        c.get_task("frypan_stove9")


@pytest.mark.parametrize("key", ["bowl_drawer_close", "mug_microwave_close"])
def test_door_A_is_In_even_when_official_B_written_first(key):
    c = catalog()
    p = c.get_task(key)
    official = list(reversed(p["official_goal_predicates"]))
    fields = c.episode_fields(key, official)
    s = fields["task_semantics"]
    assert fields["goal_specs"][0]["predicates"][0][0] == "in"
    assert fields["goal_specs"][1]["predicates"][0][0] == "close"
    truth = {tuple(p): p[0] in ("in", "open") for p in official + s["required_open_predicates"]}
    facts = c.read_goal_facts(lambda p: truth[tuple(p)], False, s)
    assert facts["goals"] == [True, False]
    assert facts["required_open_values"] == [True]
    assert c.initial_constraints_match(facts)
    truth[tuple(s["required_open_predicates"][0])] = False
    facts = c.read_goal_facts(lambda p: truth[tuple(p)], False, s)
    assert not c.initial_constraints_match(facts)  # !Close alone does not prove Open.


def test_two_pots_active00_retains_full_native_invariant():
    c = catalog()
    s = c.episode_fields("two_pots")["task_semantics"]
    facts = c.read_goal_facts(lambda p: p[0] == "turnon", False, s)
    assert facts["goals"] == [False, False]
    assert facts["invariant_values"] == [True]
    assert facts["official_goal_values"] == [False, False, True]
    assert c.initial_constraints_match(facts)
    with pytest.raises(ValueError, match="success"):
        c.read_goal_facts(lambda p: True, False, s)
    altered = deepcopy(facts)
    altered["goals"] = [True, False]
    with pytest.raises(ValueError):
        c.validate_goal_facts(altered, s)


@pytest.mark.parametrize("mutation", ["drop_invariant", "swap_active", "suite", "name", "id"])
def test_semantics_rejects_forged_mapping_and_official_identity(mutation):
    c = catalog()
    e = episode("two_pots")
    if mutation == "drop_invariant": e["task_semantics"]["invariant_indices"] = []
    if mutation == "swap_active": e["task_semantics"]["active_goal_indices"].reverse()
    if mutation == "suite": e["suite"] = "libero_90"
    if mutation == "name": e["task_name"] = "wrong"
    if mutation == "id": e["libero_task_id"] = 5
    with pytest.raises(ValueError):
        c.validate_episode_semantics(e)


def test_audit_rejects_lost_invariant_with_active_mask_unchanged():
    c = catalog()
    from tests.test_remaining_validation import CandidateEnv, snapshot
    from benchmark.remaining_goals.validation import validate_candidate
    e = {**episode("two_pots"), "initial_mask": [True, False]}
    s = e["task_semantics"]
    rows = [snapshot(i) for i in range(3)]
    for i, row in enumerate(rows):
        row.update(c.read_goal_facts(lambda p: p[1] == "moka_pot_1" or (p[0] == "turnon" and i != 1), False, s))
    audit = validate_candidate(CandidateEnv(rows), e, steps=2, hold_action=[0] * 7)
    assert not audit["technical_acceptance"]
    assert audit["checks"]["initial_constraints_match"] is False
    assert audit["trace"][1]["invariant_values"] == [False]


def test_adapter_crosschecks_full_goals_without_equating_active_to_native():
    from benchmark.remaining_goals.libero_env import LiberoGoalEnv
    from types import SimpleNamespace
    c = catalog()
    env = object.__new__(LiberoGoalEnv)
    env._ready = True
    env.task_semantics = c.episode_fields("two_pots")["task_semantics"]
    env.inner = SimpleNamespace(_eval_predicate=lambda p: p[0] == "on")
    env.env = SimpleNamespace(check_success=lambda: False)
    env.predicates = [g["predicates"] for g in c.get_task("two_pots")["goals"]]
    assert env.goal_values() == [True, True]
    assert env.goal_facts()["invariant_values"] == [False]


def test_selected_A_keeps_full_two_object_reservations(monkeypatch):
    from types import SimpleNamespace
    from benchmark.remaining_goals import build
    p = catalog().get_task("two_pots")
    p["goals"] = p["goals"][:1]
    seen = []
    monkeypatch.setattr(build, "restore_raw_state", lambda *args: None)
    monkeypatch.setattr(build, "placement_candidates", lambda *args, **kwargs: seen.append(kwargs) or [])
    build._per_goal(SimpleNamespace(sim=SimpleNamespace(model=None, data=None)), None, p, 24)
    assert seen[0]["reservation_objects"] == ["moka_pot_1", "moka_pot_2"]


def test_candidate_audit_accepts_fixture_close_and_tracks_actual_region(scene):
    from types import SimpleNamespace
    from benchmark.remaining_goals.build import CandidateAuditEnv
    model, data, base = scene
    model.site_names[0] = "microwave_1_heating_region"
    model.body_name2id = lambda name: model.body_names.index(name)
    inner = SimpleNamespace(parsed_problem={"objects": {"item": ["a", "b"]}},
        objects_dict={}, fixtures_dict={"microwave_1": SimpleNamespace(root_body="basket")},
        object_sites_dict={"microwave_1_heating_region": SimpleNamespace(parent_name="microwave_1")})
    env = SimpleNamespace(env=inner, sim=SimpleNamespace(model=model, data=data))
    c = catalog()
    audit = CandidateAuditEnv(env, base, c.get_task("mug_microwave_close")["goals"],
                              task_semantics=c.episode_fields("mug_microwave_close")["task_semantics"])
    assert ("microwave_1_heating_region", 0) in audit.articulation_sites
    assert audit.articulation_geoms  # The fixture name is not incorrectly treated as a site.


def test_placement_follows_open_container_region_without_world_coordinate_seed(scene):
    import numpy as np
    from benchmark.remaining_goals.construction import placement_candidates
    model, data, base = scene
    before = placement_candidates(base, model, data, "a", "basket_contain_region")[0]
    offset = np.array([.3, -.14, .0])
    data.site_xpos[0] += offset
    data.geom_xpos[:3] += offset
    after = placement_candidates(base, model, data, "a", "basket_contain_region")[0]
    np.testing.assert_allclose(np.asarray(after["placements"][0]["position"]) - before["placements"][0]["position"], offset)


@pytest.mark.parametrize("key", ["bowl_drawer_close", "two_pots", "mug_microwave_close"])
def test_nine_measurement_roles_and_full_facts_roundtrip(monkeypatch, key):
    from tests import test_headless_environment as fixtures
    from benchmark.remaining_goals.headless import environment, roles
    c = catalog()
    p = c.get_task(key)
    # Reuse the synthetic native-shaped fixture; no simulator import.
    monkeypatch.setitem(fixtures.TASKS, key, {**p, "goals": p["goals"] + [{"predicates": p["invariant_predicates"]}]})
    monkeypatch.setattr(environment, "_callback_status", lambda: "absent")
    native = fixtures.FakeNative(key)
    s = c.episode_fields(key)["task_semantics"]
    observer = environment.HeadlessMeasurements(native, key, task_semantics=s)
    truth = c.read_goal_facts(lambda p: p[0] in ("in", "open", "turnon") or p[1] == "moka_pot_1", False, s)
    facts = observer.evaluator_state(truth["goals"], goal_facts=truth)
    static = observer.measurement_static()
    environment.validate_evaluator_evidence(facts, static)
    assert facts["official_success"] is False
    assert static["task_semantics"] == s
    assert set(facts["event_candidates"]["wrong_grasp"]) == {"distractor_1"}
    assert "flat_stove_1" not in static["role_profile"]["wrong_placement_objects"]
    broken = deepcopy(facts)
    broken["official_success"] = True
    with pytest.raises(ValueError):
        environment.validate_evaluator_evidence(broken, static)


@pytest.mark.parametrize("protocol", ["nine-normal00", "nine-mask10"])
def test_nine_builder_roundtrips_source(monkeypatch, tmp_path, protocol):
    import hashlib
    import json
    import numpy as np
    from types import SimpleNamespace
    from tests import test_selected_producers as fixtures
    from tests.test_headless_source_acceptance import SyntheticAudit, observation
    from benchmark.remaining_goals import selected_build as builder
    from benchmark.remaining_goals.validation import validate_candidate, RGB_QUANTIZATION_AUDIT, compare_observations
    from benchmark.remaining_goals.observation_artifact import save_observation_artifact
    from benchmark.remaining_goals.headless.scoped_sources import resolve_source
    c = catalog()
    monkeypatch.setattr(fixtures, "TASK", "two_pots")
    fake, calls = fixtures.fake_builder(monkeypatch, builder, tmp_path)
    env, task, _ = fake.create_scene()
    env.env._eval_predicate = lambda p: p[0] == "turnon" or (p[1] == "moka_pot_1" and env.state[2] > .5)
    env.check_success = lambda: False
    monkeypatch.setattr(builder, "_suite", lambda p: SimpleNamespace(n_tasks=9, get_task=lambda i: SimpleNamespace(name=task.name if i == 8 else "unused")))
    def audit(env, state, e, output, relative, **kwargs):
        calls["audits"].append(kwargs)
        class Audit(SyntheticAudit):
            def validation_snapshot(self):
                row = super().validation_snapshot()
                row.update(c.read_goal_facts(lambda p: p[0] == "turnon" or (p[1] == "moka_pot_1" and self.state[2] > .5), False, e["task_semantics"]))
                return row
        result = validate_candidate(Audit(state), e, steps=kwargs["validation_steps"], hold_action=fake.HOLD, **RGB_QUANTIZATION_AUDIT)
        e["initial_observation"] = save_observation_artifact(output, str(relative / "initial_observation.npz"), observation(state))
        fake._write(output / relative / "audit.json", result)
        return {"technical_acceptance": result["technical_acceptance"]}
    fake._audit_state = audit
    out = tmp_path / "normal"
    result = builder.build(out, task="two_pots", index=2, protocol=protocol)
    assert result["complete"], result
    normal = protocol == "nine-normal00"
    assert calls["steps"] == (80 if normal else 160)
    assert [a["validation_steps"] for a in calls["audits"]] == ([0] if normal else [150])
    if not normal:
        assert calls["profiles"][0]["reservation_objects"]["flat_stove_1_cook_region"] == ["moka_pot_1", "moka_pot_2"]
    mp, ip = out / "manifest.candidates.json", out / "construction_report.json"
    manifest = json.loads(mp.read_text())
    origin = {"manifest": str(mp), "manifest_sha256": hashlib.sha256(mp.read_bytes()).hexdigest(), "content_hash": manifest["content_hash"],
              "initialization": str(ip), "initialization_sha256": hashlib.sha256(ip.read_bytes()).hexdigest()}
    if not normal:
        from benchmark.remaining_goals import selected_replay, replay_candidates
        s = manifest["episodes"][0]["task_semantics"]
        class Adapter:
            def __init__(self, config): pass
            def close(self): pass
        class Wrapper(SyntheticAudit):
            def __init__(self, adapter, state, observation_hash, *, frames_dir, manifest_dir):
                super().__init__(state)
                self.reset_checks = {"saved_state_exact": True, "initial_mask_exact": True,
                    "construction_observation_matches": True, "initial_non_rgb_exact": True}
                self.reset_observation_comparison = compare_observations(observation(state), observation(state), atol=0,
                    require_non_rgb_exact=True, refresh_state_unchanged=True, **RGB_QUANTIZATION_AUDIT)
                self.reset_initial_observation = save_observation_artifact(frames_dir, "initial_observation.npz", observation(state))
                self.post_restore_xml_sha256 = "d" * 64
            def validation_snapshot(self):
                row = super().validation_snapshot()
                row.update(c.read_goal_facts(lambda p: p[0] == "turnon" or p[1] == "moka_pot_1", False, s))
                return row
        monkeypatch.setattr(replay_candidates, "LiberoGoalEnv", Adapter)
        monkeypatch.setattr(replay_candidates, "ReplayAuditEnv", Wrapper)
        rp = tmp_path / "replay"
        replay_result = selected_replay.replay(mp, rp, task="two_pots", index=2, protocol=protocol)
        assert replay_result["technical_acceptance"]
        origin.pop("initialization")
        origin.pop("initialization_sha256")
        origin.update(candidate_replay=str(rp / "replay_report.json"), replay_sha256=hashlib.sha256((rp / "replay_report.json").read_bytes()).hexdigest())
    plan = resolve_source(protocol, "two_pots", 2, origin)
    assert plan["status"] == "ready"
    assert plan["source_acceptance"]["schema_version"] == ("remaining-headless-nine-normal00-source-acceptance-v1" if normal else "remaining-headless-nine-selected10-source-acceptance-v1")
    assert plan["environment_config"]["protocol"] == protocol
    assert plan["episodes"][0]["task_semantics"]["invariant_indices"] == [2]
    from benchmark.remaining_goals.headless.scoped_sources import archive_source
    archive_source(tmp_path / "archive", plan)


@pytest.mark.parametrize("protocol", ["nine-normal00", "nine-mask10"])
def test_preparation_nine_default_only_new30_and_rejects_reuse(monkeypatch, tmp_path, protocol):
    import json
    from benchmark.remaining_goals.headless import selected_preparation as p
    from benchmark.remaining_goals.headless.nine_planning import expected_episodes
    expected = expected_episodes(protocol)
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"schema_version": p.SCHEMA, "protocol": protocol, "expected": expected, "entries": []}))
    monkeypatch.setattr(p, "_native", lambda *a, **k: pytest.fail("inspection imported native"))
    report = p.prepare(inventory, tmp_path / "inspect")
    assert len(report["expected"]) == 90 and len(report["sources"]) == 30
    assert {r["task_id"] for r in report["sources"]} == set(catalog().NEW_TASKS)
    with pytest.raises(ValueError):
        p.prepare(inventory, tmp_path / "reuse", tasks=["basket"])
    assert not (tmp_path / "reuse").exists()


def test_nine_invalidated_ready_continuation_never_invokes_native(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    from benchmark.remaining_goals.headless import selected_preparation as p
    from benchmark.remaining_goals.headless.nine_planning import expected_episodes
    current = {"ready": True}
    def resolve(*args):
        if not current["ready"]: raise FileNotFoundError("original audit removed")
        return {"episodes": [{"episode_id": "two_pots_s000_10"}], "source_acceptance": {}}
    monkeypatch.setattr(p, "_sources", lambda: SimpleNamespace(resolve_source=resolve,
        inspect_candidate=lambda *args, **kw: (_ for _ in ()).throw(FileNotFoundError("candidate absent"))))
    monkeypatch.setattr(p, "_native", lambda *args: pytest.fail("invalidated ready invoked native"))
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"schema_version": p.SCHEMA, "protocol": "nine-mask10", "expected": expected_episodes("nine-mask10"),
        "entries": [{"task_id": "two_pots", "initial_state_index": 0, "origin": {"manifest": "old.json"}}]}))
    out = tmp_path / "prepare"
    p.prepare(inventory, out, mode="prepare-missing", tasks=["two_pots"], indices=[0])
    current["ready"] = False
    report = p.prepare(inventory, out, mode="prepare-missing", tasks=["two_pots"], indices=[0], continuation=True, allow_failed_retry=True)
    row = report["sources"][0]
    assert row["ready_origin_invalidated"] is True and row["operations"] == []


def test_native_success_unknown_is_not_coerced_to_false():
    c = catalog()
    with pytest.raises(ValueError):
        c.read_goal_facts(lambda p: False, None, c.episode_fields("two_pots")["task_semantics"])


def test_door_source_requires_open_through_entire_validation_window():
    c = catalog()
    from tests.test_remaining_validation import CandidateEnv, snapshot
    from benchmark.remaining_goals.validation import validate_candidate
    e = {**episode("mug_microwave_close"), "initial_mask": [True, False]}
    rows = [snapshot(i) for i in range(3)]
    for i, row in enumerate(rows):
        row.update(c.read_goal_facts(lambda p: p[0] == "in" or (p[0] == "open" and i != 1), False, e["task_semantics"]))
    result = validate_candidate(CandidateEnv(rows), e, steps=2, hold_action=[0] * 7)
    assert not result["technical_acceptance"]
    assert result["trace"][1]["goals"] == [True, False]
    assert result["trace"][1]["required_open_values"] == [False]


def test_container_with_articulated_object_inventory_is_never_read_as_free(scene):
    from types import SimpleNamespace
    from benchmark.remaining_goals.build import CandidateAuditEnv
    model, data, base = scene
    model.site_names[0] = "microwave_1_heating_region"
    model.body_name2id = lambda name: model.body_names.index(name)
    fixture = SimpleNamespace(root_body="basket")
    inner = SimpleNamespace(parsed_problem={"objects": {"item": ["a", "microwave_1"]}},
        objects_dict={"microwave_1": fixture}, fixtures_dict={},
        object_sites_dict={"microwave_1_heating_region": SimpleNamespace(parent_name="microwave_1")})
    env = SimpleNamespace(env=inner, sim=SimpleNamespace(model=model, data=data))
    c = catalog()
    audit = CandidateAuditEnv(env, base, c.get_task("mug_microwave_close")["goals"],
                              task_semantics=c.episode_fields("mug_microwave_close")["task_semantics"])
    assert audit.objects == ["a"]
    assert audit.articulation_geoms


@pytest.mark.parametrize("key", ["bowl_drawer_close", "two_pots", "mug_microwave_close"])
def test_formal_adapter_restores_nine_task_and_reads_complete_native_truth(fake_libero, monkeypatch, key):
    import sys
    import numpy as np
    from tests import test_remaining_libero_env as fixtures
    from benchmark.remaining_goals.libero_env import LiberoGoalEnv
    c = catalog()
    profile = c.get_task(key)
    official = list(reversed(profile["official_goal_predicates"]))
    monkeypatch.setattr(fixtures, "OFFICIAL_GOALS", official)
    original_eval = fixtures.FakeTask._eval_predicate
    def evaluate(self, predicate):
        if predicate[0] == "open":
            closed = next(i for i, p in enumerate(official, 1) if p[0] == "close")
            return bool(self.sim.state[closed] < .1)
        return original_eval(self, predicate)
    monkeypatch.setattr(fixtures.FakeTask, "_eval_predicate", evaluate)
    f = fake_libero
    f.task.name = profile["name"]
    sys.modules["libero.libero"].benchmark.get_benchmark_dict = lambda: {"libero_10": lambda: f.suite}
    state = f.state.copy()
    for i, predicate in enumerate(official, 1):
        state[i] = float(predicate[0] in ("in", "turnon") or predicate[1] == "moka_pot_1")
    np.save(f.state_file, state)
    e = {**f.episode, **episode(key), **c.episode_fields(key, official), "state_sha256": fixtures.sha256(f.state_file.read_bytes())}
    env = LiberoGoalEnv(f.config)
    observation = env.reset(e)
    np.testing.assert_array_equal(env.env.sim.state, state)
    facts = env.goal_facts()
    assert facts["goals"] == [True, False] and c.initial_constraints_match(facts)
    assert facts["official_success"] is False
    assert not set(c.FACT_FIELDS) & set(observation)
    e["task_semantics"]["active_goal_indices"].reverse()
    with pytest.raises(ValueError):
        env.reset(e)
    with pytest.raises(RuntimeError):
        env.goal_facts()
