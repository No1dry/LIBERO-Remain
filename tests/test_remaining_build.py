"""Driver integration with fake physics; no claim of real LIBERO acceptance."""

import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import build as driver
from benchmark.remaining_goals.construction import joint_candidates
from benchmark.remaining_goals.validation import compare_observations
from benchmark.remaining_goals.observation_artifact import load_observation_artifact


@pytest.fixture
def runtime(tmp_path, monkeypatch, request):
    task_key = getattr(request, "param", "basket")
    if task_key == "three_goal_fixture":
        # Exercise generic K=3 mechanics independently of two_pots, whose
        # official initially-on stove requires an invariant-aware protocol.
        synthetic = dict(driver.TASKS["two_pots"], requires_invariant_protocol=False,
                         name="synthetic_three_independent_goals")
        monkeypatch.setitem(driver.TASKS, task_key, synthetic)
    profile = driver.TASKS[task_key]
    count = len(profile["goals"])
    nq = 9 + count
    goal_slice = slice(10, 10 + count)
    model = SimpleNamespace(
        nq=nq, nv=nq, na=0, njnt=nq, nbody=1,
        joint_names=[*[f"robot0_joint{i}" for i in range(9)], *[f"goal_{chr(97+i)}" for i in range(count)]],
        body_names=["world"], jnt_type=np.full(nq, 3), jnt_qposadr=np.arange(nq),
        jnt_dofadr=np.arange(nq), jnt_limited=np.ones(nq),
        jnt_range=np.tile([0., 4.], (nq, 1)),
    )
    initial = np.r_[0., np.linspace(.01, .09, 9), np.zeros(count), np.zeros(nq)]
    initial[10 + nq:10 + nq + count] = np.arange(count) * .001 + .003
    records = SimpleNamespace(validation=[], per_goal_calls=0, xml_calls=[], env_closed=False,
                              task_key=task_key, scene_calls=[],
                              reject=lambda bits, steps, state: False)

    class Sim:
        def __init__(self):
            self.model = model
            self.state = initial.copy()

        def get_state(self):
            return SimpleNamespace(flatten=lambda: self.state.copy())

    class Env:
        def __init__(self):
            self.sim = Sim()
            self.env = SimpleNamespace(parsed_problem={
                "goal_state": [goal["predicates"][0] for goal in profile["goals"]],
                "objects": {"fake": ["a", "b"]},
            })
            self.xml_variant = "created"

        def seed(self, value):
            self.seed_value = value

        def reset(self):
            self.sim.state = initial.copy()
            self.xml_variant = "reset_model"

        def close(self):
            records.env_closed = True

    env = Env()
    task = SimpleNamespace(name=profile["name"], language="official task instruction")
    suite = SimpleNamespace(n_tasks=1, get_task=lambda index: task)
    package = ModuleType("libero")
    package.libero = ModuleType("libero.libero")
    package.libero.benchmark = SimpleNamespace(get_benchmark_dict=lambda: {profile["suite"]: lambda: suite})
    monkeypatch.setitem(sys.modules, "libero", package)
    monkeypatch.setitem(sys.modules, "libero.libero", package.libero)
    bddl = tmp_path / "task.bddl"
    bddl.write_text("fake task identity for integration tests", encoding="utf-8")
    def create_scene(*args, **kwargs):
        records.scene_calls.append(args)
        return env, task, bddl

    monkeypatch.setattr(driver, "create_scene", create_scene)
    monkeypatch.setattr(driver, "_official_initial_states", lambda *args: [initial.copy()])
    monkeypatch.setattr(driver, "environment_identity", lambda freq: {"name": "fake", "fingerprint": "test"})
    monkeypatch.setattr(driver, "_image", lambda *args: None)

    def xml_hash(active_env):
        records.xml_calls.append(active_env.xml_variant)
        return hashlib.sha256(active_env.xml_variant.encode()).hexdigest()

    def restore(active_env, state):
        active_env.sim.state = state.copy()
        active_env.xml_variant = "completed_visuals" if any(state[goal_slice] > .5) else "base_visuals"
        return {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8)}

    def step(active_env, action):
        active_env.sim.state[0] += .05
        active_env.sim.state[1] += .0007  # Robot drift must not leak into edited starts.
        for index in range(10, 10 + count):
            if active_env.sim.state[index] > .5:
                active_env.sim.state[index] += .001
                active_env.sim.state[index + nq] = .002 * active_env.sim.state[index]
        return {"agentview_image": np.zeros((2, 2, 3), dtype=np.uint8)}

    def per_goal(active_env, base, profile, max_candidates):
        records.per_goal_calls += 1
        # Real candidate construction/composition, with two alternative A states
        # and one B state. No geometry or policy is involved in this driver test.
        a = joint_candidates(base, model, "goal_a", sample_count=3)
        b = joint_candidates(base, model, "goal_b", sample_count=3)
        by_value_a = {item["diagnostics"]["chosen_value"]: item for item in a}
        by_value_b = {item["diagnostics"]["chosen_value"]: item for item in b}
        result = [[by_value_a[1.], by_value_a[2.]], [by_value_b[3.]]]
        if count == 3:
            c = joint_candidates(base, model, "goal_c", sample_count=3)
            result.append([next(item for item in c if item["diagnostics"]["chosen_value"] == 3.)])
        return result

    def validate(wrapper, episode, *, steps, **kwargs):
        observation = wrapper.restore_candidate(episode)
        state = wrapper.env.sim.state.copy()
        bits = "".join("1" if bit else "0" for bit in episode["initial_mask"])
        records.validation.append({"bits": bits, "steps": steps, "state": state,
                                   "episode": episode})
        mask_matches = list(state[goal_slice] > .5) == episode["initial_mask"]
        passed = bool(mask_matches and not records.reject(bits, steps, state))
        # An audit may advance physics; exports must use the original restored
        # candidate, never the final validation state.
        if steps:
            wrapper.env.sim.state += 100.
        return {"technical_acceptance": passed, "checks": {"mock_acceptance": passed},
                "error": None, "trace": [{"state": state.tolist(),
                    "observation_check": compare_observations(observation, observation)}], "completed_steps": steps}

    monkeypatch.setattr(driver, "model_xml_hash", xml_hash)
    monkeypatch.setattr(driver, "restore_raw_state", restore)
    monkeypatch.setattr(driver, "reset_scene", lambda active_env: active_env.reset())
    monkeypatch.setattr(driver, "_step", step)
    monkeypatch.setattr(driver, "_goals", lambda active, goals: [bool(x) for x in active.sim.state[goal_slice] > .5])
    monkeypatch.setattr(driver, "_per_goal", per_goal)
    monkeypatch.setattr(driver, "validate_candidate", validate)
    return records, tmp_path / "pack", model, env


def run_build(runtime):
    records, output, _, _ = runtime
    report = driver.build(output, tasks=records.task_key, scenes=1, settle_steps=2,
                          validation_steps=3, max_candidates=4)
    manifest = json.loads((output / "manifest.candidates.json").read_text(encoding="utf-8"))
    return records, output, report, manifest


def test_search_selects_one_complete_group_without_mixing_earlier_survivors(runtime):
    records = runtime[0]
    records.reject = lambda bits, steps, state: bits == "11" and state[10] < 1.5
    _, output, report, manifest = run_build(runtime)
    group = report["groups"][0]
    assert group["complete"] and group["selected_joint_candidate"] == 1
    assert len(group["joint_attempts"]) == 2
    assert [trial["accepted"] for trial in group["joint_attempts"]] == [False, True]
    assert len(manifest["episodes"]) == 4
    starts = {"".join("1" if bit else "0" for bit in episode["initial_mask"]):
              np.load(output / episode["state_path"], allow_pickle=False)
              for episode in manifest["episodes"]}
    assert starts["10"][10] == starts["11"][10] == pytest.approx(2.002)
    assert starts["01"][11] == starts["11"][11] == pytest.approx(3.002)
    for a, b, indices in [("10", "11", [10, 21]), ("01", "11", [11, 22]),
                           ("00", "01", [10, 21]), ("00", "10", [11, 22])]:
        np.testing.assert_array_equal(starts[a][indices], starts[b][indices])
    for state in starts.values():
        np.testing.assert_array_equal(state[:10], starts["00"][:10])
        assert state.max() < 4.  # The validation-end mutation was not saved.
    assert all(episode["construction"]["joint_candidate"] == 1 for episode in manifest["episodes"])
    assert all(episode["construction"]["legal"] is False for episode in manifest["episodes"])
    assert records.env_closed


def test_reset_xml_identity_is_frozen_before_candidate_visual_changes(runtime):
    records, _, _, manifest = run_build(runtime)
    expected = hashlib.sha256(b"reset_model").hexdigest()
    assert records.xml_calls == ["reset_model"]
    assert {episode["model_xml_sha256"] for episode in manifest["episodes"]} == {expected}


def test_initial_artifact_uses_selected_returned_frame_without_an_extra_render(runtime, monkeypatch):
    original = driver.restore_raw_state
    render_calls = []

    def changing_render(env, state):
        obs = original(env, state)
        render_calls.append(len(render_calls) + 1)
        obs["agentview_image"][:] = render_calls[-1]
        return obs

    monkeypatch.setattr(driver, "restore_raw_state", changing_render)
    _, output, _, manifest = run_build(runtime)
    for episode in manifest["episodes"]:
        audit_path = output / episode["construction"]["technical_audit"]
        audit = json.loads(audit_path.read_text())
        static = json.loads(audit_path.with_name("static_audit.json").read_text())
        captured = load_observation_artifact(output, episode["initial_observation"])
        digest = compare_observations(captured, captured)["returned_sha256"]
        assert digest == audit["trace"][0]["observation_check"]["returned_sha256"]
        assert digest != static["trace"][0]["observation_check"]["returned_sha256"]
    # Every capture belongs to an existing restore/audit; no renderer call is
    # introduced by exporting the artifact after an audit has completed.
    assert len(render_calls) == 10  # official base + joint settle + 2 audits per mask


def test_actual_selected_component_values_and_hashes_match_saved_states(runtime):
    _, output, report, manifest = run_build(runtime)
    group = report["groups"][0]
    states = [np.load(output / episode["state_path"], allow_pickle=False) for episode in manifest["episodes"]]
    for component in group["selected_components"]:
        values = states[-1][component["indices"]]
        np.testing.assert_array_equal(values, component["values"])
        assert hashlib.sha256(values.astype("<f8").tobytes()).hexdigest() == component["values_sha256"]
    assert group["components_exactly_matched"]
    assert len(list((output / "states").glob("*.npy"))) == 4
    for episode in manifest["episodes"]:
        audit = json.loads((output / episode["construction"]["technical_audit"]).read_text())
        reference = episode["initial_observation"]
        assert reference == audit["initial_observation"]
        loaded = load_observation_artifact(output, reference,
            expected_digest=audit["trace"][0]["observation_check"]["returned_sha256"])
        assert loaded["agentview_image"].dtype == np.uint8
        assert not loaded["agentview_image"].any()
    assert "observation_artifact.py" in report["builder_sources_sha256"]


@pytest.mark.parametrize("fail_steps,expected_steps", [(0, [0]), (3, [0, 3])])
def test_shared_zero_failure_stops_entire_group_once(runtime, fail_steps, expected_steps):
    records = runtime[0]
    records.reject = lambda bits, steps, state: bits == "00" and steps == fail_steps
    _, output, report, manifest = run_build(runtime)
    assert records.per_goal_calls == 0
    assert [call["steps"] for call in records.validation] == expected_steps
    assert all(call["bits"] == "00" for call in records.validation)
    assert report["complete_groups"] == 0
    assert "shared 00 base failed" in report["groups"][0]["error"]
    assert manifest["episodes"] == []
    assert not (output / "states").exists()


def test_static_rejection_skips_dynamic_and_rejected_groups_export_no_survivors(runtime):
    records = runtime[0]
    records.reject = lambda bits, steps, state: bits == "11"
    _, output, report, manifest = run_build(runtime)
    assert len(report["groups"][0]["joint_attempts"]) == 2
    assert len([call for call in records.validation if call["bits"] == "11"]) == 2
    assert all(call["steps"] == 0 for call in records.validation if call["bits"] == "11")
    assert [(call["bits"], call["steps"]) for call in records.validation].count(("00", 3)) == 1
    assert manifest["episodes"] == []
    assert not (output / "states").exists()
    paths = list(output.glob("validation/*_11/*/audit.json"))
    assert len(paths) == 2
    assert all(json.loads(path.read_text(encoding="utf-8"))["stage"] == "static_rejection" for path in paths)


def test_mixed_whitelists_within_one_goal_fail_closed(runtime):
    _, _, model, env = runtime
    base = env.sim.state.copy()
    a = joint_candidates(base, model, "goal_a")
    b = joint_candidates(base, model, "goal_b")
    combined = driver.combine_goal_candidates(base, model, [a, b], [True, True])[0]
    with pytest.raises(ValueError, match="same exact whitelist"):
        driver._matched_states(base, combined["state"], model, [[a[0], b[0]], b], combined)


@pytest.mark.parametrize("runtime", ["three_goal_fixture"], indirect=True)
def test_three_goals_export_all_eight_matched_masks_from_one_winning_candidate(runtime):
    records = runtime[0]
    records.reject = lambda bits, steps, state: bits == "111" and state[10] < 1.5
    _, output, report, manifest = run_build(runtime)
    group = report["groups"][0]
    masks = driver.mask_order(3)
    assert group["selected_joint_candidate"] == 1 and group["goal_count"] == 3
    assert ["".join(str(int(bit)) for bit in e["initial_mask"]) for e in manifest["episodes"]] == list(masks)
    assert len(manifest["episodes"]) == 8
    states = {bits: np.load(output / episode["state_path"]) for bits, episode in zip(masks, manifest["episodes"])}
    for goal_index, component in enumerate(group["selected_components"]):
        indices = component["indices"]
        for bits, state in states.items():
            expected = states["111"] if bits[goal_index] == "1" else states["000"]
            np.testing.assert_array_equal(state[indices], expected[indices])
    assert [(x["bits"], x["steps"]) for x in records.validation].count(("000", 3)) == 1
    assert all(e["construction"]["legal"] is False for e in manifest["episodes"])


@pytest.mark.parametrize("runtime", ["three_goal_fixture"], indirect=True)
def test_three_goal_missing_partner_never_exports_a_partial_group(runtime):
    runtime[0].reject = lambda bits, steps, state: bits == "111"
    _, output, report, manifest = run_build(runtime)
    assert len(report["groups"][0]["joint_attempts"]) == 2
    assert not report["groups"][0]["complete"]
    assert manifest["episodes"] == [] and not (output / "states").exists()


@pytest.mark.parametrize("runtime", ["frypan_stove3"], indirect=True)
def test_task_uses_its_own_official_suite_for_scene_and_manifest(runtime):
    records, _, report, manifest = run_build(runtime)
    assert records.scene_calls == [("libero_90", driver.TASKS["frypan_stove3"]["name"])]
    assert report["groups"][0]["suite"] == "libero_90"
    assert {episode["suite"] for episode in manifest["episodes"]} == {"libero_90"}


def test_task_runtime_failure_is_recorded_and_next_task_still_runs(runtime, monkeypatch):
    records, output, _, _ = runtime
    monkeypatch.setitem(driver.TASKS, "missing_task", dict(driver.TASKS["basket"], name="not_installed"))
    report = driver.build(output, tasks="missing_task,basket", settle_steps=2, validation_steps=3)
    assert report["complete_groups"] == 1 and len(report["groups"]) == 2
    assert report["groups"][0]["failure_stage"] == "task_runtime_error"
    assert report["groups"][1]["complete"]
    assert report["task_errors"][0]["task_id"] == "missing_task"
    assert records.env_closed


def test_default_construction_is_annotated_as_validation_development_data(runtime):
    _, _, report, manifest = run_build(runtime)
    assert report["split"] == "val" and report["start_index"] == 0
    assert {episode["split"] for episode in manifest["episodes"]} == {"val"}
    assert "not established" in report["split_scope"]


def test_source_offset_is_used_for_initial_index_seed_ids_and_split(runtime, monkeypatch):
    records, output, _, env = runtime
    initial = env.sim.state.copy()
    monkeypatch.setattr(driver, "_official_initial_states", lambda *args: [initial.copy() for _ in range(4)])
    report = driver.build(output, tasks="basket", scenes=1, start_index=2, split="train",
                          settle_steps=2, validation_steps=3)
    manifest = json.loads((output / "manifest.candidates.json").read_text(encoding="utf-8"))
    assert report["start_index"] == report["groups"][0]["initial_state_index"] == env.seed_value == 2
    assert len(manifest["episodes"]) == 4
    for episode in manifest["episodes"]:
        assert episode["initial_state_index"] == episode["seed"] == 2
        assert episode["split"] == "train"
        assert episode["source_id"] == "basket_official_2"
        assert episode["episode_id"].startswith("basket_s002_")


@pytest.mark.parametrize("kwargs", [{"split": "pilot"}, {"start_index": -1}, {"start_index": True}])
def test_invalid_source_annotation_fails_before_output_is_created(runtime, kwargs):
    with pytest.raises(ValueError):
        driver.build(runtime[1], tasks="basket", **kwargs)
    assert not runtime[1].exists()


def test_small_joint_search_budget_reaches_another_first_goal_value(runtime, monkeypatch):
    records, _, model, _ = runtime

    def candidates(active_env, base, profile, max_candidates):
        return [joint_candidates(base, model, "goal_a", sample_count=9),
                joint_candidates(base, model, "goal_b", sample_count=24)]

    monkeypatch.setattr(driver, "_per_goal", candidates)
    # Every pairing with the first goal's central seed fails, regardless of
    # the second goal. A lexicographic product exhausts budget=4 on that seed.
    records.reject = lambda bits, steps, state: bits[0] == "1" and abs(state[10] - 2.002) < 1e-8
    _, _, report, manifest = run_build(runtime)
    assert report["groups"][0]["selected_joint_candidate"] == 1
    assert len(manifest["episodes"]) == 4
