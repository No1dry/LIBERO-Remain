"""Synthetic evidence tamper and execution parity tests; no real experiments."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from benchmark.remaining_goals.finish import evidence as evidence_module
from benchmark.remaining_goals.finish.evidence import FinishEvidence, load_query_input, validate_finish_evidence
from benchmark.remaining_goals.finish.runner import run_finish_episode
from benchmark.remaining_goals.finish.schema import PROTOCOL, digest, input_sha256, validate_finish_result
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from tests.test_finish_runner import Env, Policy, episode, observation, inputs


def identity(ep, *, mode="active", horizon=9):
    return {"run_id": "synthetic_finish_run", "run_config_sha256": "d" * 64, "manifest_hash": "e" * 64,
            "episode_id": ep["episode_id"], "state_sha256": ep["state_sha256"], "protocol_version": PROTOCOL,
            "mode": mode, "head_sha256": "b" * 64, "horizon": horizon, "retention_steps": 2, "max_chunk_steps": 8}


def execute(tmp_path, *, mode="active", policy=None, env=None, writer_type=FinishEvidence):
    run = tmp_path / "run"
    ep = episode()
    who = identity(ep, mode=mode)
    writer = writer_type(run / "evidence" / "000000", who)
    env, policy = env or Env(), policy or Policy()
    result = run_finish_episode(env, policy, ep, mode=mode, horizon=9, retention_steps=2, evidence=writer)
    return run, ep, who, writer, env, policy, result


def index(run, result):
    path = run / result["finish_evidence"]["path"]
    return path, json.loads(path.read_text(encoding="utf-8"))


def rewrite(path, data, result):
    path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    result["finish_evidence"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_actual_reset_and_each_same_forward_input_are_lossless(tmp_path):
    run, ep, who, _, env, policy, result = execute(tmp_path, mode="shadow")
    assert result["status"] == "completed"
    assert validate_finish_evidence(run, result, ep, who)["verified"]
    initial = load_observation_artifact(run, result["finish_evidence"]["initial_observation"])
    for key, actual in observation(0).items():
        assert initial[key].dtype == actual.dtype and initial[key].tobytes() == actual.tobytes()
    for row in result["queries"]:
        captured = load_query_input(run, row["input_evidence"])
        expected = inputs(row["observation_step"])
        assert input_sha256(captured) == input_sha256(expected) == row["input_sha256"]
        for name, reference in row["input_evidence"]["crops"].items():
            assert (run / reference["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert row["input_evidence"]["tensor_dtypes"]["proprio"] == "numpy.float64"
    assert env.resets == policy.resets == 1 and policy.calls == 3 and env.steps == 11


def test_evidence_does_not_change_calls_trace_actions_or_inputs(tmp_path):
    run, ep, who, _, env, policy, recorded = execute(tmp_path, policy=Policy(finish_at=8))
    other_env, other_policy = Env(), Policy(finish_at=8)
    plain = run_finish_episode(other_env, other_policy, ep, horizon=9, retention_steps=2)
    assert "finish_evidence" not in plain
    assert plain["trace"] == recorded["trace"] and plain["executed_actions"] == recorded["executed_actions"]
    assert (env.steps, env.evaluations, env.holds, policy.calls) == (other_env.steps, other_env.evaluations, other_env.holds, other_policy.calls)
    for (a, text), (b, text2) in zip(policy.inputs, other_policy.inputs):
        assert text == text2 == ep["instruction"]
        for key in a:
            assert a[key].tobytes() == b[key].tobytes()
    assert validate_finish_evidence(run, recorded, ep, who)["verified"]


@pytest.mark.parametrize("env,policy", [(Env(fail_evaluator=1), Policy()), (Env(), Policy(fail_query=2)),
                                      (Env(fail_hold=True), Policy(finish_at=0)), (Env(fail_step=2), Policy())])
def test_real_partial_errors_remain_auditable(env, policy, tmp_path):
    run, ep, who, _, _, _, result = execute(tmp_path, env=env, policy=policy)
    assert result["status"] == "runtime_error" and result["finish_evidence"]["status"] == "recorded"
    assert validate_finish_evidence(run, result, ep, who)["verified"]


def test_initial_archive_save_failure_is_not_a_fake_policy_attempt(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(evidence_module, "save_observation_artifact", fail)
    run, ep, who, _, env, policy, result = execute(tmp_path)
    assert result["error_phase"] == "evidence_initial" and result["status"] == "runtime_error"
    assert env.resets == 1 and env.steps == policy.calls == 0 and result["trace"] == []
    assert validate_finish_evidence(run, result, ep, who)["verified"]


def test_failed_final_write_preserves_partial_but_never_excuses_changed_bytes(tmp_path):
    class BrokenFinish(FinishEvidence):
        def finish(self, result):
            raise OSError("synthetic final write failed")
    run, ep, who, _, _, _, result = execute(tmp_path, writer_type=BrokenFinish)
    assert result["error_phase"] == "evidence_finalize" and result["finish_evidence"]["status"] == "evidence_error"
    assert validate_finish_evidence(run, result, ep, who)["verified"] is False
    path = run / result["finish_evidence"]["initial_observation"]["path"]
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        validate_finish_evidence(run, result, ep, who)


@pytest.mark.parametrize("field,value", [("mode", "shadow"), ("run_id", "other"), ("head_sha256", "f" * 64)])
def test_wrong_expected_run_or_mode_or_head_rejected(tmp_path, field, value):
    run, ep, who, _, _, _, result = execute(tmp_path)
    with pytest.raises(ValueError, match="identity"):
        validate_finish_evidence(run, result, ep, {**who, field: value})


@pytest.mark.parametrize("mutate", [
    lambda d: d["result"]["queries"][0].update(observation_step=1),
    lambda d: d["configuration"].update(horizon=20),
    lambda d: d["identity"].update(mode="shadow"),
    lambda d: d["query_inputs"]["1"]["tensor_dtypes"].update(proprio="numpy.float32"),
    lambda d: d["query_inputs"]["1"]["crops"]["wrist"].update(pixels_sha256="a" * 64),
])
def test_rehashing_index_does_not_hide_query_or_artifact_tampering(tmp_path, mutate):
    run, ep, who, _, _, _, result = execute(tmp_path)
    path, data = index(run, result)
    mutate(data)
    rewrite(path, data, result)
    with pytest.raises(ValueError):
        validate_finish_evidence(run, result, ep, who)


@pytest.mark.parametrize("which", ["npz", "crop"])
def test_corrupt_real_input_bytes_rejected(tmp_path, which):
    run, ep, who, _, _, _, result = execute(tmp_path)
    reference = result["queries"][0]["input_evidence"]
    item = reference["arrays"] if which == "npz" else reference["crops"]["agentview"]
    path = run / item["path"]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        validate_finish_evidence(run, result, ep, who)


def test_initial_source_artifact_cannot_replace_actual_reset(tmp_path):
    run, ep, who, _, _, _, result = execute(tmp_path)
    changed = deepcopy(ep)
    changed["initial_observation"] = {"path": "old_construction.npz", "sha256": "f" * 64}
    with pytest.raises(ValueError, match="source"):
        validate_finish_evidence(run, result, changed, who)


def test_rehashed_result_cannot_relabel_timeout_as_finish(tmp_path):
    run, ep, who, _, _, _, result = execute(tmp_path)
    path, data = index(run, result)
    result.update(exit_reason="finish", finish_step=9, timeout_step=None)
    for key in ("exit_reason", "finish_step", "timeout_step"):
        data["result"][key] = result[key]
    rewrite(path, data, result)
    with pytest.raises(ValueError, match="exit reason"):
        validate_finish_evidence(run, result, ep, who)


def test_path_escape_rejected_even_if_content_hash_known(tmp_path):
    run, ep, who, _, _, _, result = execute(tmp_path)
    result["finish_evidence"]["path"] = "../execution.json"
    with pytest.raises(ValueError, match="contained"):
        validate_finish_evidence(run, result, ep, who)


def test_existing_output_is_not_overwritten_or_claimed(tmp_path):
    root = tmp_path / "run" / "evidence" / "000000"
    root.mkdir(parents=True)
    file = root / "execution.json"
    file.write_text("old history", encoding="utf-8")
    run, ep, who, _, env, policy, result = execute(tmp_path)
    assert file.read_text(encoding="utf-8") == "old history"
    assert env.resets == policy.calls == 0 and result["status"] == "runtime_error"
    assert "path" not in result["finish_evidence"]
    assert validate_finish_evidence(run, result, ep, who)["verified"] is False


def test_bf16_input_archive_preserves_original_bits(tmp_path):
    def bf16(value):
        value["input_evidence"]["tensors"]["pixel_values"] = np.full((1, 6, 2, 2), 0xBF80, np.uint16)
        value["input_evidence"]["tensor_dtypes"]["pixel_values"] = "torch.bfloat16"
        return value
    run, ep, who, _, _, _, result = execute(tmp_path, policy=Policy(finish_at=0, invalid=bf16))
    captured = load_query_input(run, result["queries"][0]["input_evidence"])
    assert captured["tensor_dtypes"]["pixel_values"] == "torch.bfloat16"
    assert np.all(captured["tensors"]["pixel_values"] == 0xBF80)
    assert validate_finish_evidence(run, result, ep, who)["verified"]


def test_partial_crop_save_failure_keeps_npz_and_first_crop_auditable(tmp_path, monkeypatch):
    original = evidence_module._png
    calls = 0
    def failure(pixels):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second camera write failure")
        return original(pixels)
    monkeypatch.setattr(evidence_module, "_png", failure)
    run, ep, who, _, env, policy, result = execute(tmp_path)
    assert result["error_phase"] == "evidence_query" and result["status"] == "runtime_error"
    assert env.steps == 0 and policy.calls == 1 and result["queries"][0]["accepted_chunk_length"] == 0
    assert validate_finish_evidence(run, result, ep, who)["verified"]
    _, data = index(run, result)
    path = run / data["query_inputs"]["1"]["crops"]["agentview"]["path"]
    path.write_bytes(path.read_bytes() + b"tampered partial crop")
    with pytest.raises(ValueError):
        validate_finish_evidence(run, result, ep, who)


@pytest.mark.parametrize("where", ["query", "hold"])
def test_user_interrupt_returns_finalized_partial_for_orchestrator(tmp_path, where):
    class InterruptedPolicy(Policy):
        def predict(self, obs, instruction):
            if where == "query":
                raise KeyboardInterrupt("synthetic user interruption")
            return super().predict(obs, instruction)
    env = Env()
    if where == "hold":
        def interrupt():
            raise SystemExit(130)
        env.hold_action = interrupt
    run, ep, who, _, _, _, result = execute(tmp_path, policy=InterruptedPolicy(finish_at=0), env=env)
    assert result["status"] == "runtime_error" and result["interrupted"] is True
    assert result["n_steps"] == 0 and result["policy_queries"] == 1
    assert validate_finish_evidence(run, result, ep, who)["verified"]
