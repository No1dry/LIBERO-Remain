"""CPU-only explicit normal00 execution, scoring and evidence contracts."""
from copy import deepcopy
from types import ModuleType
import sys

import pytest

from benchmark.remaining_goals.headless import runner, schema
from benchmark.remaining_goals.headless.evidence import HeadlessEvidence, validate_evidence
from benchmark.remaining_goals.headless.metrics import score_episode, summarize, render_report
from tests.test_headless_runner import Env, Policy, Video, episode


@pytest.fixture(autouse=True)
def synthetic_measurements(monkeypatch):
    module = ModuleType("benchmark.remaining_goals.headless.environment")
    def static(value, episode=None, *, protocol="mask10"):
        if value.get("synthetic") is not True or value["model_xml_sha256"] != episode["model_xml_sha256"]:
            raise ValueError("synthetic source differs")
        return deepcopy(value)
    module.validate_measurement_static = static
    module.validate_evaluator_evidence = lambda facts, frozen: deepcopy(facts)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def normal_episode(**changes):
    return episode(**{"episode_id": "basket_s000_00", "initial_mask": [False, False], **changes})


class NormalEnv(Env):
    def __init__(self, goals=None, **kwargs):
        super().__init__(**kwargs)
        self.goals = goals or (lambda step: [step >= 1, step >= 2])

    def evaluator_state(self):
        facts = super().evaluator_state()
        facts["goals"] = self.goals(self.steps)
        return facts


def execute(env=None, *, ep=None, identity=None, evidence=None, horizon=16, policy=None):
    env, policy, ep, video = env or NormalEnv(), policy or Policy(), ep or normal_episode(), Video()
    result = runner.run_episode(env, policy, ep, protocol="normal00-control", horizon=horizon,
                                recorder=video, evidence=evidence, identity=identity)
    schema.validate_normal00_result(result, ep, identity)
    return env, policy, video, result


@pytest.mark.parametrize("goals", [lambda step: [step >= 1, step >= 2], lambda step: [step >= 2, step >= 1],
                                    lambda step: [step >= 1 and step != 3, step >= 2]])
def test_normal00_both_goal_orders_and_temporary_new_goal_loss_are_legal(goals):
    env, policy, video, result = execute(NormalEnv(goals))
    expected = 8 if result["trace"][3]["goals"][0] is False else 6
    assert result["status"] == "completed" and result["n_steps"] == expected
    assert result["goal_confirmed_step"] == expected and result["goal_completion_step"] == expected - 4
    assert result["goal_regression"] is None and result["preservation_applicable"] is False
    assert all(row["goal_regression"] is None and row["preservation_applicable"] is False for row in result["trace"])
    assert env.steps == expected and policy.calls == 1 and video.closed == 1
    assert [step for step, _ in video.frames] == list(range(expected + 1))
    assert score_episode(normal_episode(), result, protocol="normal00-control")["classification"] == "success"
    assert set(policy.inputs[0][0]) == {"agentview_image", "robot0_eye_in_hand_image", "proprio"}


@pytest.mark.parametrize("goals", [[True, False], [False, True], [True, True]])
def test_normal00_actual_start_mismatch_is_technical_without_policy_query(goals):
    env, policy, _, result = execute(NormalEnv(lambda step: goals))
    assert result["status"] == "invalid_initial_state" and env.steps == policy.calls == 0
    assert score_episode(normal_episode(), result, protocol="normal00-control")["classification"] == "technical_error"


def test_normal00_missing_start_measurement_is_technical():
    env, policy, _, result = execute(NormalEnv(fail=("evaluator", 0)))
    assert result["status"] == "runtime_error" and env.steps == policy.calls == 0
    assert result["trace"] == [] and result["goal_regression"] is None
    assert score_episode(normal_episode(), result, protocol="normal00-control")["classification"] == "technical_error"


@pytest.mark.parametrize("kind", schema.EVENTS)
def test_normal00_keeps_wrong_grasp_placement_and_damage_failure_rules(kind):
    _, _, _, result = execute(NormalEnv(candidate=lambda candidate, step: candidate == kind and 1 <= step <= 5))
    row = score_episode(normal_episode(), result, protocol="normal00-control")
    assert row["classification"] == "failure" and row["failure_reasons"] == [kind]


@pytest.mark.parametrize("complete,endpoint", [(4, "goal_confirmed"), (5, "horizon")])
def test_normal00_endpoint_requires_five_observations_with_no_extra_horizon_query(complete, endpoint):
    env, policy, video, result = execute(NormalEnv(lambda step: [step >= 1, step >= complete]), horizon=8)
    assert env.steps == 8 and policy.calls == 1 and len(video.frames) == 9
    assert result["exit_reason"] == endpoint


@pytest.mark.parametrize("fault", ["protocol", "schema", "mask", "regression", "applicable", "frame", "identity",
                                  "missing_regression", "missing_frame_regression"])
def test_normal00_schema_rejects_protocol_and_preservation_tampering(fault):
    _, _, _, result = execute()
    identity = None
    if fault == "protocol": result["protocol_version"] = schema.PROTOCOL
    elif fault == "schema": result["schema_version"] = schema.RESULT_SCHEMA
    elif fault == "mask": result["initial_mask"] = [True, False]
    elif fault == "regression": result["goal_regression"] = False
    elif fault == "applicable": result["preservation_applicable"] = True
    elif fault == "frame": result["trace"][1]["goal_regression"] = False
    elif fault == "missing_regression": del result["goal_regression"]
    elif fault == "missing_frame_regression": del result["trace"][1]["goal_regression"]
    else:
        identity = {"protocol_version": schema.PROTOCOL}
        result["identity_sha256"] = schema.canonical_hash(identity)
    with pytest.raises(ValueError):
        schema.validate_protocol_result(result, normal_episode(), identity)
    with pytest.raises(ValueError):
        schema.validate_result(result)


def test_normal00_evidence_roundtrip_binds_explicit_protocol_origin_and_acceptance(tmp_path):
    identity = {"protocol_version": "remaining-headless-normal00-control-v1", "episode_id": "basket_s000_00",
                "state_sha256": "a" * 64, "source_origin": {"manifest_sha256": "d" * 64},
                "source_acceptance": {"schema_version": "remaining-headless-normal00-source-acceptance-v1"}}
    recorder = HeadlessEvidence(tmp_path / "evidence" / "normal", identity)
    _, _, _, result = execute(identity=identity, evidence=recorder)
    assert validate_evidence(tmp_path, result, normal_episode(), identity)["verified"]
    assert result["source_origin"] == identity["source_origin"]
    assert result["source_acceptance"] == identity["source_acceptance"]
    changed = deepcopy(result)
    changed["protocol_version"] = schema.PROTOCOL
    with pytest.raises(ValueError): validate_evidence(tmp_path, changed, normal_episode(), identity)
    changed = deepcopy(result)
    changed["source_origin"]["manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError): schema.validate_normal00_result(changed, normal_episode(), identity)
    changed = deepcopy(result)
    changed["source_acceptance"]["schema_version"] = "fabricated"
    with pytest.raises(ValueError): schema.validate_normal00_result(changed, normal_episode(), identity)
    with pytest.raises(ValueError): schema.validate_normal00_result(changed, normal_episode())
    with pytest.raises(ValueError):
        execute(identity={**identity, "protocol_version": schema.PROTOCOL})


def test_normal00_summary_has_fixed_denominators_and_preservation_na():
    planned = [normal_episode(episode_id=f"task{task}_s{index:03d}_00", task_id=f"task{task}",
               suite="libero_10" if task < 6 else "libero_90", initial_state_index=index, seed=index)
               for task in range(10) for index in range(10)]
    _, _, _, result = execute(ep=planned[0])
    summary = summarize(planned, [result], protocol="normal00-control")
    assert summary["counts"]["expected"] == 100 and summary["counts"]["successes"] == 1
    assert [track["expected"] for track in summary["tracks"]] == [60, 40]
    assert summary["counts"]["classification_counts"]["missing"] == 99
    assert summary["episodes"][0]["preservation_applicable"] is False
    assert "preservation" in render_report(summary).lower() and "N/A" in render_report(summary)


def test_normal00_named_wrapper_and_analyzer_do_not_reinterpret_legacy():
    result = runner.run_normal00_episode(NormalEnv(), Policy(), normal_episode(), horizon=8)
    assert schema.validate_protocol_result(result, protocol="normal00-control")["verified"]
    analysis = schema.analyze_trace(result["trace"], protocol="normal00-control")
    assert analysis["goal_regression"] is None and analysis["preservation_applicable"] is False
    with pytest.raises(ValueError): schema.validate_protocol_result(result, protocol="mask10")
    with pytest.raises(ValueError): runner.run_episode(NormalEnv(), Policy(), normal_episode())
    with pytest.raises(ValueError): runner.run_episode(NormalEnv(), Policy(), normal_episode(), protocol="arbitrary-mask")


def test_normal00_identity_cannot_bind_legacy_acceptance_schema():
    identity = {"protocol_version": "remaining-headless-normal00-control-v1",
                "source_acceptance": {"schema_version": "remaining-headless-mask10-source-acceptance-v1"}}
    with pytest.raises(ValueError): execute(identity=identity)
