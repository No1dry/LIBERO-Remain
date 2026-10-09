"""Synthetic CPU evidence tests; no simulator, model weights or GPU required."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from benchmark.remaining_goals import pilot_evidence as evidence_module
from benchmark.remaining_goals.observation_artifact import load_observation_artifact, save_observation_artifact
from benchmark.remaining_goals.pilot_evidence import EpisodeEvidence, observation_sha256, validate_execution_evidence
from benchmark.remaining_goals.runner import run_episode


def episode(mask=None, horizon=4, retention=2):
    return {"episode_id": "synthetic_partial", "task_id": "toy", "suite": "synthetic",
            "task_name": "synthetic two goals", "instruction": "complete both original goals",
            "seed": 7, "initial_mask": [True, False] if mask is None else mask,
            "goal_specs": [{"id": "first", "language": "complete first", "predicates": [["on", "a", "b"]]},
                           {"id": "second", "language": "complete second", "predicates": [["on", "c", "d"]]}],
            "horizon": horizon, "retention_steps": retention, "state_sha256": "a" * 64}


def identity(ep):
    return {"run_id": "synthetic-run", "manifest_hash": "b" * 64, "run_config_sha256": "c" * 64,
            "episode_id": ep["episode_id"], "state_sha256": ep["state_sha256"],
            "selection_sha256": "d" * 64, "instruction_mode": "original",
            "effective_instruction_sha256": hashlib.sha256(ep["instruction"].encode()).hexdigest()}


def obs(step):
    return {"agentview_image": np.full((5, 6, 3), step + 7, dtype=np.uint8),
            "robot0_eye_in_hand_image": np.full((4, 7, 3), 40 + step, dtype=np.uint8),
            "proprio": np.array([-0., 1e-9, float(step)], dtype=np.float32)}


class Env:
    def __init__(self, *, fail_reset=False, fail_step=None, fail_goals=None, wrong_initial=False):
        self.fail_reset, self.fail_step, self.fail_goals = fail_reset, fail_step, fail_goals
        self.wrong_initial = wrong_initial
        self.steps = self.resets = self.goal_calls = self.holds = 0
        self.actions = []

    def reset(self, spec):
        self.resets += 1
        if self.fail_reset:
            raise RuntimeError("synthetic reset failure")
        self.mask = spec["initial_mask"]
        return obs(0)

    def goal_values(self):
        self.goal_calls += 1
        if self.fail_goals == self.steps:
            raise RuntimeError("synthetic goal read failure")
        if self.wrong_initial and self.steps == 0:
            return [False, False]
        return self.mask

    def step(self, action):
        if self.steps + 1 == self.fail_step:
            raise RuntimeError("synthetic step failure")
        self.steps += 1
        self.actions.append(action.copy())
        return obs(self.steps)

    def hold_action(self):
        self.holds += 1
        return np.array([0., 0., 0., 0., 0., 0., -1.])


class Policy:
    def __init__(self, sizes=(2, 1, 5), fail_query=None, stop_query=None, invalid=None):
        self.sizes = sizes
        self.fail_query, self.stop_query, self.invalid = fail_query, stop_query, invalid
        self.queries = self.resets = 0
        self.inputs = []

    def reset(self):
        self.resets += 1

    def predict(self, observation, instruction):
        self.queries += 1
        self.inputs.append((deepcopy(observation), instruction))
        if self.queries == self.fail_query:
            raise RuntimeError("synthetic inference failure")
        if self.queries == self.stop_query:
            return None
        if self.invalid is not None:
            return self.invalid
        size = self.sizes[min(self.queries - 1, len(self.sizes) - 1)]
        return np.arange(size * 7, dtype=float).reshape(size, 7) / 100 + self.queries / 10


def execute(tmp_path, *, ep=None, env=None, policy=None, chunk=4, evidence_class=EpisodeEvidence):
    ep = ep or episode()
    env, policy = env or Env(), policy or Policy()
    run = tmp_path / "run"
    writer = evidence_class(run / "evidence" / "000000", identity(ep))
    result = run_episode(env, policy, ep, max_chunk_steps=chunk, evidence=writer)
    return run, ep, env, policy, writer, result


def read_index(run, result):
    path = run / result["execution_evidence"]["path"]
    return path, json.loads(path.read_text(encoding="utf-8"))


def rewrite_index(path, data, result):
    path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    result["execution_evidence"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_actual_initial_typed_capture_and_variable_chunk_mapping(tmp_path):
    ep = episode()
    construction = save_observation_artifact(tmp_path, "construction.npz", obs(99))
    ep["initial_observation"] = construction
    run, ep, env, policy, _, result = execute(tmp_path, ep=ep)
    assert result["status"] == "completed"
    checked = validate_execution_evidence(run, result, ep, identity(ep))
    assert checked["verified"] and checked["queries"] == 3 and checked["executed_steps"] == 6
    initial = load_observation_artifact(run, result["execution_evidence"]["initial_observation"])
    assert initial["agentview_image"][0, 0, 0] == 7  # not the construction reference's 106
    assert initial["proprio"].dtype == np.float32 and np.signbit(initial["proprio"][0])
    _, data = read_index(run, result)
    assert [q["observation_step"] for q in data["queries"]] == [0, 2, 3]
    assert [q["returned_chunk_length"] for q in data["queries"]] == [2, 1, 5]
    assert [q["accepted_chunk_length"] for q in data["queries"]] == [2, 1, 4]
    assert [q["execution_interval"] for q in data["queries"]] == [[1, 2], [3, 3], [4, 6]]
    assert data["queries"][-1]["unexecuted_accepted_actions"] == 1
    assert [q["observation_sha256"] for q in data["queries"]] == [observation_sha256(obs(s)) for s in [0, 2, 3]]
    assert env.resets == policy.resets == 1 and env.steps == 6 and policy.queries == 3
    assert {text for _, text in policy.inputs} == {ep["instruction"]}
    assert all(set(value) == {"agentview_image", "robot0_eye_in_hand_image", "proprio"} for value, _ in policy.inputs)


def test_evidence_does_not_change_default_schema_trace_inputs_or_metrics(tmp_path):
    from benchmark.remaining_goals.metrics import compute_metrics
    ep = episode()
    baseline_env, baseline_policy = Env(), Policy()
    baseline = run_episode(baseline_env, baseline_policy, ep, max_chunk_steps=4)
    _, _, env, policy, _, recorded = execute(tmp_path, ep=ep)
    assert "execution_evidence" not in baseline
    assert {k: v for k, v in baseline.items() if k != "elapsed_seconds"} == {
        k: v for k, v in recorded.items() if k not in {"elapsed_seconds", "execution_evidence"}}
    assert compute_metrics(ep, baseline["trace"]) == compute_metrics(ep, recorded["trace"])
    assert (env.resets, env.steps, env.goal_calls, policy.resets, policy.queries) == (
        baseline_env.resets, baseline_env.steps, baseline_env.goal_calls, baseline_policy.resets, baseline_policy.queries)
    for (left, instruction), (right, other) in zip(baseline_policy.inputs, policy.inputs):
        assert instruction == other
        assert observation_sha256(left) == observation_sha256(right)


@pytest.mark.parametrize("stop_query", [1, 2])
def test_stop_query_maps_holds_without_fabricating_policy_actions(tmp_path, stop_query):
    run, ep, env, _, _, result = execute(tmp_path, policy=Policy(stop_query=stop_query))
    validate_execution_evidence(run, result, ep, identity(ep))
    _, data = read_index(run, result)
    stop = data["queries"][-1]
    assert stop["response"] == "stop" and stop["returned_chunk_length"] == stop["accepted_chunk_length"] == 0
    assert stop["executed_policy_actions"] == 0
    assert stop["executed_hold_actions"] == env.holds == (6 if stop_query == 1 else 4)
    assert stop["observation_step"] == result["stop_step"] == (0 if stop_query == 1 else 2)


def test_terminal_mask_budget_stays_retention_only(tmp_path):
    run, ep, env, _, _, result = execute(tmp_path, ep=episode([True, True], 520, 3), policy=Policy((8,)))
    assert result["scheduled_steps"] == result["n_steps"] == env.steps == 3
    validate_execution_evidence(run, result, ep, identity(ep))
    _, data = read_index(run, result)
    assert data["queries"][0]["accepted_chunk_length"] == 4
    assert data["queries"][0]["unexecuted_accepted_actions"] == 1


@pytest.mark.parametrize("env,policy,phase,steps,queries", [
    (Env(fail_reset=True), Policy(), "env_reset", 0, 0),
    (Env(), Policy(fail_query=2), "policy_predict", 2, 2),
    (Env(fail_step=3), Policy(), "env_step", 2, 2),
    (Env(fail_goals=3), Policy(), "goal_values", 3, 2),
    (Env(), Policy(invalid=np.ones(6)), "validate_action", 0, 1),
    (Env(), Policy(invalid=np.full((2, 7), np.nan)), "validate_action", 0, 1),
])
def test_runtime_errors_keep_only_the_real_executed_prefix(tmp_path, env, policy, phase, steps, queries):
    run, ep, env, policy, _, result = execute(tmp_path, env=env, policy=policy)
    assert result["status"] == "runtime_error" and result["error_phase"] == phase
    assert result["n_steps"] == steps and result["policy_queries"] == queries
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"]
    _, data = read_index(run, result)
    assert len(data["queries"]) == queries and len(data["executed_actions"]) == steps
    if phase == "policy_predict":
        assert data["queries"][-1]["response"] == "error"
    if phase == "goal_values":
        assert len(result["trace"]) == steps  # final action happened before predicate read failed


def test_invalid_initial_mask_saves_actual_reset_but_never_queries(tmp_path):
    run, ep, _, policy, _, result = execute(tmp_path, env=Env(wrong_initial=True))
    assert result["status"] == "invalid_initial_state" and policy.queries == policy.resets == 0
    assert result["execution_evidence"]["initial_observation"]
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"]


def test_single_action_vector_records_one_action_not_seven(tmp_path):
    run, ep, _, _, _, result = execute(tmp_path, policy=Policy(invalid=np.zeros(7)))
    _, data = read_index(run, result)
    assert len(data["queries"]) == 6
    assert all(q["returned_shape"] == [7] and q["returned_chunk_length"] == 1 for q in data["queries"])
    validate_execution_evidence(run, result, ep, identity(ep))


def test_evidence_receives_isolated_copies(tmp_path):
    class MutatingEvidence(EpisodeEvidence):
        def capture_initial(self, value):
            super().capture_initial(value)
            value.clear()
        def prepare_query(self, value, **kwargs):
            super().prepare_query(value, **kwargs)
            value["proprio"][:] = 999
        def accept_actions(self, value, **kwargs):
            super().accept_actions(value, **kwargs)
            value[:] = 999
        def action_executed(self, step, action, **kwargs):
            super().action_executed(step, action, **kwargs)
            action[:] = 999
    run, ep, _, policy, _, result = execute(tmp_path, evidence_class=MutatingEvidence)
    assert result["status"] == "completed"
    assert policy.inputs[0][0]["proprio"].tolist() == obs(0)["proprio"].tolist()
    assert max(result["trace"][1]["action"]) < 1
    validate_execution_evidence(run, result, ep, identity(ep))


def test_step0_save_failure_is_technical_error_before_policy(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic full disk")
    monkeypatch.setattr(evidence_module, "save_observation_artifact", fail)
    run, ep, env, policy, _, result = execute(tmp_path)
    assert result["status"] == "runtime_error" and result["error_phase"] == "evidence_initial_observation"
    assert env.resets == 1 and env.steps == policy.queries == policy.resets == 0
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"]


def test_evidence_prepare_failure_does_not_fabricate_a_query(tmp_path):
    class Failure(EpisodeEvidence):
        def prepare_query(self, *args, **kwargs):
            super().prepare_query(*args, **kwargs)
            raise OSError("synthetic query evidence failure")
    run, ep, _, policy, _, result = execute(tmp_path, evidence_class=Failure)
    assert result["status"] == "runtime_error" and result["error_phase"] == "evidence_query_input"
    assert result["policy_queries"] == policy.queries == 0
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"]


def test_finalize_write_failure_keeps_strict_partial_references(tmp_path):
    class Failure(EpisodeEvidence):
        def _write(self):
            if self.data["recording_status"] == "finished":
                raise OSError("synthetic final write failure")
            super()._write()
    run, ep, _, _, _, result = execute(tmp_path, evidence_class=Failure)
    assert result["status"] == "runtime_error" and result["error_phase"] == "evidence_finalize"
    assert result["prior_execution_status"]["status"] == "completed"
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"] is False
    path, _ = read_index(run, result)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file hash"):
        validate_execution_evidence(run, result, ep, identity(ep))


def test_existing_evidence_is_not_overwritten_or_claimed(tmp_path):
    run = tmp_path / "run"
    prior = run / "evidence" / "000000"
    prior.mkdir(parents=True)
    marker = prior / "execution.json"
    marker.write_text("historical evidence")
    _, ep, env, _, _, result = execute(tmp_path)
    assert result["status"] == "runtime_error" and env.resets == 0
    assert "path" not in result["execution_evidence"]
    assert marker.read_text() == "historical evidence"
    assert validate_execution_evidence(run, result, ep, identity(ep))["verified"] is False


@pytest.mark.parametrize("field,value", [("selection_sha256", "e" * 64), ("episode_id", "other"),
                                        ("instruction_mode", "oracle-remaining-initial")])
def test_wrong_run_selection_or_episode_identity_rejected(tmp_path, field, value):
    run, ep, _, _, _, result = execute(tmp_path)
    expected = identity(ep)
    expected[field] = value
    with pytest.raises(ValueError, match="identity"):
        validate_execution_evidence(run, result, ep, expected)


@pytest.mark.parametrize("mutation", ["observation_step", "first_hash", "accepted_length", "returned_length", "interval", "action"])
def test_rehashed_query_tampering_still_rejected(tmp_path, mutation):
    run, ep, _, _, _, result = execute(tmp_path)
    path, data = read_index(run, result)
    if mutation == "observation_step":
        data["queries"][1]["observation_step"] += 1
    elif mutation == "first_hash":
        data["queries"][0]["observation_sha256"] = "f" * 64
    elif mutation == "accepted_length":
        data["queries"][-1]["accepted_chunk_length"] -= 1
    elif mutation == "returned_length":
        data["queries"][0]["returned_chunk_length"] = 3
    elif mutation == "interval":
        data["queries"][-1]["execution_interval"][1] += 1
    else:
        data["executed_actions"][0]["action"][0] += 1
    rewrite_index(path, data, result)
    with pytest.raises(ValueError):
        validate_execution_evidence(run, result, ep, identity(ep))


def test_trace_and_source_episode_tampering_rejected(tmp_path):
    run, ep, _, _, _, result = execute(tmp_path)
    changed = deepcopy(result)
    changed["trace"][1]["action"][0] += .1
    with pytest.raises(ValueError, match="trace binding"):
        validate_execution_evidence(run, changed, ep, identity(ep))
    altered_episode = deepcopy(ep)
    altered_episode["instruction"] = "oracle text disguised as original"
    with pytest.raises(ValueError, match="source episode"):
        validate_execution_evidence(run, result, altered_episode, identity(ep))


@pytest.mark.parametrize("failure_label", [False, True])
def test_corrupt_actual_npz_is_never_excused_by_error_status(tmp_path, failure_label):
    run, ep, _, _, _, result = execute(tmp_path)
    reference = result["execution_evidence"]
    artifact = run / reference["initial_observation"]["path"]
    artifact.write_bytes(artifact.read_bytes() + b"corrupt")
    if failure_label:
        result.update(status="runtime_error", error_phase="evidence_finalize")
        reference["status"] = "evidence_error"
    with pytest.raises(ValueError, match="file hash"):
        validate_execution_evidence(run, result, ep, identity(ep))


def test_evidence_reference_cannot_escape_run(tmp_path):
    run, ep, _, _, _, result = execute(tmp_path)
    result["execution_evidence"]["path"] = "../foreign/execution.json"
    with pytest.raises(ValueError, match="contained"):
        validate_execution_evidence(run, result, ep, identity(ep))


def test_typed_observation_hash_distinguishes_dtype_and_signed_zero():
    value = obs(0)
    changed = deepcopy(value)
    changed["proprio"] = changed["proprio"].astype(np.float64)
    assert observation_sha256(value) != observation_sha256(changed)
    changed = deepcopy(value)
    changed["proprio"][0] = 0.
    assert observation_sha256(value) != observation_sha256(changed)


def test_truth_field_rejected_before_capture_or_prediction(tmp_path):
    class TruthEnv(Env):
        def reset(self, spec):
            value = super().reset(spec)
            value["goal_truth"] = np.array([True, False])
            return value
    _, _, _, policy, _, result = execute(tmp_path, env=TruthEnv())
    assert result["status"] == "runtime_error" and policy.queries == 0
    assert "initial_observation" not in result["execution_evidence"]


def test_chunk_budget_is_bound_to_run_identity(tmp_path):
    ep = episode()
    bound = {**identity(ep), "max_chunk_steps": 4}
    run = tmp_path / "run"
    writer = EpisodeEvidence(run / "evidence" / "000000", bound)
    result = run_episode(Env(), Policy(), ep, max_chunk_steps=4, evidence=writer)
    validate_execution_evidence(run, result, ep, bound)
    path, data = read_index(run, result)
    data["configuration"]["max_chunk_steps"] = 5
    rewrite_index(path, data, result)
    with pytest.raises(ValueError, match="bound run configuration"):
        validate_execution_evidence(run, result, ep, bound)


def test_stop_is_recorded_even_if_its_evidence_write_fails_once(tmp_path):
    class Failure(EpisodeEvidence):
        raised = False
        def _write(self):
            if self.data["queries"] and self.data["queries"][-1]["response"] == "stop" and not self.raised:
                self.raised = True
                raise OSError("synthetic STOP recording failure")
            super()._write()
    run, ep, env, _, _, result = execute(tmp_path, policy=Policy(stop_query=1), evidence_class=Failure)
    assert result["status"] == "runtime_error" and result["error_phase"] == "evidence_query_return"
    assert result["stop_step"] == 0 and env.steps == 0
    validate_execution_evidence(run, result, ep, identity(ep))
