"""CPU-only synthetic contracts; these fixtures are not real LIBERO results."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import regression_env as subject
from benchmark.remaining_goals.observation_artifact import load_observation_artifact
from benchmark.remaining_goals.task_catalog import TASKS


def case(protocol="official", index=3):
    return {"id": f"synthetic_{protocol}_{index}", "task_key": "basket",
            "task_name": TASKS["basket"]["name"], "suite": "libero_10",
            "initial_state_index": index, "policy_seed": 7, "protocol": protocol,
            "horizon": 520, "retention_steps": 0 if protocol == "official" else 150,
            "warmup_steps": 10 if protocol == "official" else 0,
            "settle_steps": 0 if protocol == "official" else 80,
            "env_seed": 0 if protocol == "official" else index, "max_chunk_steps": 8}


def observation(step=0, privileged=False):
    obs = {"agentview_image": np.full((4, 5, 3), step % 256, dtype=np.uint8),
           "robot0_eye_in_hand_image": np.full((4, 5, 3), step % 256, dtype=np.uint8),
           "robot0_eef_pos": np.array([0., 0., 1.]), "robot0_eef_quat": np.array([0., 0., 0., 1.]),
           "robot0_gripper_qpos": np.array([.04, -.04])}
    if privileged:
        obs.update({"object-state": np.ones(3), "goal_truth": [True, True]})
    return obs


class NativeEnv:
    def __init__(self, success=3, fail_step=None, warmup_done=False):
        self.success, self.fail_step, self.warmup_done = success, fail_step, warmup_done
        self.steps = 0
        self.actions = []
        self.reset_count = 0
        self.closed = False
        self.env = self
        self.sim = SimpleNamespace(get_state=lambda: SimpleNamespace(flatten=lambda: np.array([self.steps, 0.], float)))

    def reset(self):
        self.reset_count += 1
        self.steps = 0

    def set_init_state(self, state):
        self.selected = np.asarray(state).copy()
        return observation(privileged=True)

    def _eval_predicate(self, predicate):
        return self.steps >= 10 + self.success

    def check_success(self):
        return self.steps >= 10 + self.success

    def step(self, action):
        if self.steps + 1 == self.fail_step:
            raise RuntimeError("synthetic step failed before advance")
        self.steps += 1
        self.actions.append(list(action))
        return observation(self.steps, True), 0, self.check_success() or (self.warmup_done and self.steps <= 10), {}

    def close(self):
        self.closed = True


class Policy:
    def __init__(self, prediction=None):
        self.prediction = np.tile([.01, .02, .03, .04, .05, .06, -1.], (8, 1)) if prediction is None else prediction
        self.provenance = {"synthetic": True, "python": sys.executable, "random_seed": 7}
        self.reset_count = self.queries = 0
        self.inputs = []
        self.closed = False

    def reset(self):
        self.reset_count += 1

    def predict(self, obs, instruction):
        self.inputs.append((deepcopy(obs), instruction))
        self.queries += 1
        return self.prediction(self.queries) if callable(self.prediction) else self.prediction

    def close(self):
        self.closed = True


@pytest.fixture
def config():
    return {"execution": {"random_seed": 7}, "synthetic": True}


def setup_official(monkeypatch, env=None, policy=None):
    env, policy = env or NativeEnv(), policy or Policy()
    def context(config, requested):
        return {"env": env, "initial_state": np.array([requested["initial_state_index"], 123.]),
                "instruction": "original complete instruction", "goals": deepcopy(TASKS["basket"]["goals"]),
                "dummy_action": np.array([0., 0., 0., 0., 0., 0., -1.]),
                "provenance": {"synthetic": True, "selected_official_state": {"sha256": "fixture"}}}
    monkeypatch.setattr(subject, "_official_context", context)
    monkeypatch.setattr(subject, "SubprocessPolicy", lambda config: policy)
    return env, policy


def test_official_wait_success_and_action_contract(tmp_path, monkeypatch, config):
    env, policy = setup_official(monkeypatch, NativeEnv(success=3, warmup_done=True))
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={})
    assert result["status"] == "completed"
    assert result["common_success"] is result["native_success"] is True
    assert result["n_steps"] == 3 and len(result["trace"]) == 4
    assert result["warmup_steps_completed"] == 10 and len(result["warmup_trace"]) == 10
    assert env.steps == 13 and env.reset_count == 1
    assert env.selected.tolist() == [3., 123.]
    assert result["trace"][0]["goals"] == [False, False]
    assert result["termination_reason"] == "evaluator_success" and result["stop_step"] is None
    assert all(row["stopped"] is False for row in result["trace"])
    assert env.actions[10:] == [policy.prediction[0].tolist()] * 3  # decoded gripper stays -1
    assert result["first_action"] == env.actions[10]
    assert policy.reset_count == 1 and policy.queries == 1
    assert all("goal_truth" not in obs and "object-state" not in obs for obs, _ in policy.inputs)
    assert {text for _, text in policy.inputs} == {"original complete instruction"}
    restored = load_observation_artifact(tmp_path / "case", result["initial_observation"])
    assert restored["agentview_image"][0, 0, 0] == 10
    assert env.closed and policy.closed
    assert json.loads((tmp_path / "case" / "episode.json").read_text()) == result


def test_official_horizon_exact_and_chunk_limit(tmp_path, monkeypatch, config):
    action = np.arange(70, dtype=float).reshape(10, 7) / 100
    env, policy = setup_official(monkeypatch, NativeEnv(success=1000), Policy(action))
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={})
    assert result["status"] == "completed" and result["common_success"] is False
    assert result["native_success"] is False
    assert result["n_steps"] == 520 and env.steps == 530 and policy.queries == 65
    assert len(result["trace"]) == 521
    assert env.actions[10:26] == action[:8].tolist() * 2
    assert result["termination_reason"] == "horizon_exhausted"


def test_official_queue_cannot_cross_cases(tmp_path, monkeypatch, config):
    env1, policy1 = setup_official(monkeypatch, NativeEnv(success=1), Policy(np.full((8, 7), .1)))
    first = subject.execute_case(config, case(), tmp_path / "first", video_config={})
    env2, policy2 = setup_official(monkeypatch, NativeEnv(success=1), Policy(np.full((8, 7), .2)))
    second = subject.execute_case(config, case(index=4), tmp_path / "second", video_config={})
    assert first["first_action"] == [.1] * 7 and second["first_action"] == [.2] * 7
    assert policy1.queries == policy2.queries == 1
    assert env1.selected[0] == 3 and env2.selected[0] == 4


@pytest.mark.parametrize("prediction", [lambda _: None, lambda _: np.zeros(6), lambda _: np.full(7, np.nan)])
def test_official_invalid_prediction_is_runtime_error(tmp_path, monkeypatch, config, prediction):
    env, _ = setup_official(monkeypatch, NativeEnv(success=999), Policy(prediction))
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={})
    assert result["status"] == "runtime_error" and result["prepared"] and result["policy_started"]
    assert result["common_success"] is result["native_success"] is None
    assert result["n_steps"] == 0 and len(result["trace"]) == 1 and env.steps == 10
    assert result["stop_step"] is None


def test_official_runtime_error_preserves_executed_prefix(tmp_path, monkeypatch, config):
    env, _ = setup_official(monkeypatch, NativeEnv(success=999, fail_step=14))
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={})
    assert result["status"] == "runtime_error" and result["error"]["phase"] == "env_step"
    assert result["n_steps"] == 3 and len(result["trace"]) == 4
    assert result["first_action"] == env.actions[10]
    assert result["common_success"] is result["native_success"] is None


def test_preparation_and_model_failure_denominators(tmp_path, monkeypatch, config):
    env, _ = setup_official(monkeypatch, NativeEnv(success=0))
    monkeypatch.setattr(subject, "SubprocessPolicy", lambda _: pytest.fail("must not load a policy for non-00"))
    invalid = subject.execute_case(config, case(), tmp_path / "invalid", video_config={})
    assert invalid["attempted"] and not invalid["prepared"] and not invalid["policy_started"]
    assert invalid["status"] == "preparation_error" and invalid["trace"][0]["goals"] == [True, True]
    assert env.closed
    setup_official(monkeypatch)
    def fail(_):
        raise ImportError("synthetic missing model dependency")
    monkeypatch.setattr(subject, "SubprocessPolicy", fail)
    unloaded = subject.execute_case(config, case(), tmp_path / "unloaded", video_config={})
    assert unloaded["status"] == "model_load_error" and unloaded["prepared"] and not unloaded["policy_started"]
    assert unloaded["n_steps"] == 0 and len(unloaded["trace"]) == 1
    assert unloaded["error"]["phase"] == "model_load"


class RemainEnv:
    def __init__(self, success=2, fail_step=None):
        self.success, self.fail_step = success, fail_step
        self.steps = self.reset_count = 0
        self.closed = False

    def reset(self, episode):
        self.reset_count += 1
        assert episode["initial_mask"] == [False, False]
        return observation()

    def goal_values(self):
        return [self.steps >= self.success] * 2

    def step(self, action):
        if self.steps + 1 == self.fail_step:
            raise RuntimeError("synthetic step failure")
        self.steps += 1
        return observation(self.steps)

    def hold_action(self):
        return np.array([0., 0., 0., 0., 0., 0., -1.])

    def close(self):
        self.closed = True


def setup_remain(monkeypatch, env=None, policy=None):
    env, policy = env or RemainEnv(), policy or Policy()
    calls = []
    def prepare(key, index, output):
        calls.append((key, index, output))
        output.mkdir()
        episode = {"episode_id": "synthetic00", "task_id": key, "task_name": TASKS[key]["name"],
                   "suite": "libero_10", "instruction": "original complete instruction", "seed": index,
                   "goal_specs": deepcopy(TASKS[key]["goals"]), "initial_mask": [False, False],
                   "horizon": 520, "retention_steps": 150}
        return {"status": "prepared", "episode": episode, "environment_config": {"synthetic": True},
                "preparation": {"settle_steps_completed": 80, "audit_steps_completed": 150},
                "provenance": {"synthetic": True, "saved_state_sha256": "fixture"}, "error": None}
    monkeypatch.setattr(subject, "prepare_normal00", prepare)
    monkeypatch.setattr(subject, "LiberoGoalEnv", lambda config: env)
    monkeypatch.setattr(subject, "SubprocessPolicy", lambda config: policy)
    return env, policy, calls


@pytest.mark.parametrize("success,common,joint", [(2, True, True), (520, True, True), (521, False, False), (900, False, False)])
def test_remain_full_budget_no_duplicate_settle(tmp_path, monkeypatch, config, success, common, joint):
    env, policy, calls = setup_remain(monkeypatch, RemainEnv(success=success))
    result = subject.execute_case(config, case("remain"), tmp_path / "case", video_config={})
    assert result["status"] == "completed"
    assert env.steps == result["n_steps"] == 670 and env.reset_count == 1
    assert result["common_success"] is common and result["native_success"] is joint
    assert result["metrics"]["task_success_by_horizon"] is common and result["metrics"]["joint_success"] is joint
    assert result["settle_steps_completed"] == 80 and result["warmup_steps_completed"] == 0
    assert len(calls) == 1 and calls[0][:2] == ("basket", 3)
    assert policy.reset_count == 1 and len(result["trace"]) == 671
    assert result["first_action"] == policy.prediction[0].tolist()
    assert result["termination_reason"] == "horizon_and_retention_exhausted"
    assert result["metrics"] == subject.compute_metrics(result["prepared_episode"], result["trace"])


def test_remain_stop_preserves_existing_hold_semantics(tmp_path, monkeypatch, config):
    env, _, _ = setup_remain(monkeypatch, policy=Policy(lambda _: None))
    result = subject.execute_case(config, case("remain"), tmp_path / "case", video_config={})
    assert result["status"] == "completed" and result["n_steps"] == 670
    assert result["stop_step"] == 0 and all(row["stopped"] for row in result["trace"][1:])
    assert result["first_action"] == env.hold_action().tolist()


def test_remain_error_retains_trace(tmp_path, monkeypatch, config):
    setup_remain(monkeypatch, RemainEnv(fail_step=4))
    result = subject.execute_case(config, case("remain"), tmp_path / "case", video_config={})
    assert result["status"] == "runtime_error" and result["n_steps"] == 3
    assert len(result["trace"]) == 4 and result["first_action"] is not None
    assert result["common_success"] is result["native_success"] is None and result["metrics"] is None


def test_remain_preparation_failure_never_loads_policy(tmp_path, monkeypatch, config):
    monkeypatch.setattr(subject, "prepare_normal00", lambda *a: {
        "status": "preparation_error", "episode": None, "environment_config": None,
        "preparation": {"settle_steps_completed": 29}, "provenance": {"synthetic": True},
        "error": {"phase": "settle", "type": "RuntimeError", "message": "fixture"}})
    monkeypatch.setattr(subject, "SubprocessPolicy", lambda _: pytest.fail("not eligible"))
    result = subject.execute_case(config, case("remain"), tmp_path / "case", video_config={})
    assert result["status"] == "preparation_error" and result["attempted"]
    assert not result["prepared"] and not result["policy_started"] and result["settle_steps_completed"] == 29
    assert result["error"]["phase"] == "settle"
    assert json.loads((tmp_path / "case" / "episode.json").read_text()) == result


@pytest.mark.parametrize("protocol", ["official", "remain"])
def test_video_error_does_not_change_trace_or_scores(tmp_path, monkeypatch, config, protocol):
    setup = setup_official if protocol == "official" else setup_remain
    setup(monkeypatch)
    without = subject.execute_case(config, case(protocol), tmp_path / "off", video_config={})
    class BrokenRecorder:
        def __init__(self, *args, **kwargs):
            pass
        def capture(self, observation, *, step):
            observation.clear()  # must be an isolated copy
            raise OSError("synthetic codec failure")
        def close(self):
            return {"status": "empty", "path": None}
    monkeypatch.setattr(subject, "EpisodeVideoRecorder", BrokenRecorder)
    setup(monkeypatch)
    with_video = subject.execute_case(config, case(protocol), tmp_path / "on", video_config={"enabled": True})
    for key in ("status", "trace", "n_steps", "first_action", "common_success", "native_success", "metrics"):
        assert without[key] == with_video[key]
    assert with_video["video"]["status"] == "video_error"
    assert "video" not in without


@pytest.mark.parametrize("change", [{"horizon": 521}, {"max_chunk_steps": 1}, {"policy_seed": 8},
                                     {"task_name": "wrong"}, {"initial_state_index": True}])
def test_invalid_case_fails_before_output(tmp_path, config, change):
    request = case()
    request.update(change)
    with pytest.raises(ValueError):
        subject.execute_case(config, request, tmp_path / "case", video_config={})
    assert not (tmp_path / "case").exists()


def test_existing_output_never_overwritten(tmp_path, config):
    marker = tmp_path / "keep.txt"
    marker.write_text("prior evidence")
    with pytest.raises(FileExistsError):
        subject.execute_case(config, case(), tmp_path, video_config={})
    assert marker.read_text() == "prior evidence"


def test_official_context_resolves_exact_task_and_source(monkeypatch, tmp_path):
    from benchmark.remaining_goals.adapters import openvla
    from benchmark.remaining_goals.adapters.openvla_oft import UPSTREAM_COMMIT
    native_config = tmp_path / "native-config"
    native_config.mkdir()
    (native_config / "config.yaml").write_text("# synthetic existing config")
    monkeypatch.setenv("LIBERO_CONFIG_PATH", str(native_config))
    source_root = tmp_path / "init"
    source = source_root / "libero_10" / "basket.pruned_init"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic official source, not torch serialized")
    repo = tmp_path / "repo"
    for name in ("run_libero_eval.py", "libero_utils.py"):
        path = repo / "experiments/robot/libero" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic source")
    module_file = tmp_path / "libero.py"
    module_file.write_text("# synthetic native module")
    module = SimpleNamespace(get_libero_path=lambda key: str(source_root), __file__=str(module_file))
    monkeypatch.setitem(sys.modules, "libero", SimpleNamespace(libero=module))
    monkeypatch.setitem(sys.modules, "libero.libero", module)
    task = SimpleNamespace(name=TASKS["basket"]["name"], language="whole instruction",
                           problem_folder="libero_10", init_states_file=source.name)
    tasks = [SimpleNamespace(name="unrelated"), task]
    suite = SimpleNamespace(n_tasks=2, get_task=lambda index: tasks[index])
    env = NativeEnv()
    env.parsed_problem = {"goal_state": [p for g in TASKS["basket"]["goals"] for p in g["predicates"]]}
    calls = []
    def load(cfg, selected_suite, index):
        calls.append((cfg.initial_states_path, selected_suite, index))
        return [np.array([i, i + 1.], float) for i in range(5)], None
    def get_env(selected_task, family, *, resolution):
        assert selected_task is task and family == "openvla" and resolution == 256
        return env, task.language
    api = SimpleNamespace(GenerateConfig=lambda: SimpleNamespace(model_family="openvla"),
                          benchmark=SimpleNamespace(get_benchmark_dict=lambda: {"libero_10": lambda: suite}),
                          load_initial_states=load, get_libero_env=get_env,
                          get_libero_dummy_action=lambda family: [0.] * 6 + [-1.])
    monkeypatch.setattr(openvla, "_options", lambda config: pytest.fail("checkpoint resource validation belongs to model_load"))
    monkeypatch.setattr(openvla, "_load_upstream", lambda options, revision: (api, None, UPSTREAM_COMMIT))
    config = {"adapter_options": {"repo_path": str(repo), "checkpoint": str(tmp_path / "missing-checkpoint"), "suite": "libero_10"}}
    context = subject._official_context(config, case(index=4))
    assert calls == [("DEFAULT", suite, 1)]
    assert context["initial_state"].tolist() == [4., 5.]
    assert context["provenance"]["task_index"] == 1
    assert context["provenance"]["official_initial_states"]["sha256"] == subject._sha(source)
    assert context["provenance"]["selected_official_state"]["sha256"] == subject._array_identity(np.array([4., 5.]))["sha256"]
    with pytest.raises(IndexError, match="outside"):
        subject._official_context(config, case(index=5))


@pytest.mark.parametrize("explicit", [True, False])
def test_missing_native_configuration_fails_before_upstream_import(tmp_path, monkeypatch, explicit):
    from benchmark.remaining_goals.adapters import openvla
    missing = tmp_path / "missing-native-config"
    if explicit:
        monkeypatch.setenv("LIBERO_CONFIG_PATH", str(missing))
    else:
        monkeypatch.delenv("LIBERO_CONFIG_PATH", raising=False)
        monkeypatch.setattr(subject.os.path, "expanduser", lambda path: str(missing))
    monkeypatch.setattr(openvla, "_load_upstream", lambda *a: pytest.fail("must not import upstream"))
    with pytest.raises(FileNotFoundError, match="configuration required before import"):
        subject._official_context({}, case())
    assert not missing.exists()


@pytest.mark.parametrize("bad_report", [[], {"status": "saved", "path": "bad.mp4", "bad": np.zeros(3)}])
def test_invalid_video_close_payload_does_not_poison_case(tmp_path, monkeypatch, config, bad_report):
    setup_official(monkeypatch)
    class Recorder:
        def __init__(self, *args, **kwargs):
            pass
        def capture(self, observation, *, step):
            pass
        def close(self):
            return deepcopy(bad_report)
    monkeypatch.setattr(subject, "EpisodeVideoRecorder", Recorder)
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={"enabled": True})
    assert result["status"] == "completed" and result["common_success"] is True
    assert result["video"]["status"] == "video_error" and result["video"]["path"] is None
    assert json.loads((tmp_path / "case" / "episode.json").read_text()) == result


def test_official_last_raw_frame_retained_when_predicate_read_fails(tmp_path, monkeypatch, config):
    env, _ = setup_official(monkeypatch, NativeEnv(success=999))
    steps = []
    class Recorder:
        def __init__(self, *args, **kwargs):
            pass
        def capture(self, observation, *, step):
            steps.append((step, int(observation["agentview_image"][0, 0, 0])))
        def close(self):
            return {"status": "empty", "path": None, "synthetic": True}
    monkeypatch.setattr(subject, "EpisodeVideoRecorder", Recorder)
    original = subject._native_goals
    def fail_on_first_policy_state(native, specs):
        if native.steps == 11:
            raise RuntimeError("synthetic predicate read failure")
        return original(native, specs)
    monkeypatch.setattr(subject, "_native_goals", fail_on_first_policy_state)
    result = subject.execute_case(config, case(), tmp_path / "case", video_config={"enabled": True})
    assert result["status"] == "runtime_error" and result["error"]["phase"] == "goal_values"
    assert result["n_steps"] == 1 and result["first_action"] == env.actions[10]
    assert len(result["trace"]) == 1 and steps == [(0, 10), (1, 11)]
