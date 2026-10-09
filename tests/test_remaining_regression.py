"""CPU-only normal00 orchestration checks; no simulator or model is executed."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from benchmark.remaining_goals import regression as regression
from benchmark.remaining_goals import regression_worker


@pytest.fixture
def config():
    return {
        "model_id": "openvla_oft", "policy_id": "synthetic-sog10-regression",
        "policy_factory": regression.FACTORY, "suite": "libero_10",
        "runtime": {"python_executable": "model-env/python", "cuda_visible_devices": "0"},
        "execution": {"random_seed": 7, "max_chunk_steps": 8},
        "adapter_options": {"repo_path": "uninstalled-official-repo",
                            "checkpoint": "unavailable-checkpoint", "suite": "libero_10",
                            "repo_revision": regression.OFT_REVISION, "random_seed": 7},
        "checkpoint_source": {"repository": regression.SOG10_REPOSITORY,
                              "revision": regression.SOG10_REVISION},
    }


def result_for(plan, case, *, status="completed", success=True, prepared=True,
               policy_started=True):
    row = {**deepcopy(case), "plan_hash": plan["plan_hash"], "attempted": True,
           "status": status, "prepared": prepared, "policy_started": policy_started,
           "common_success": success if status == "completed" else None,
           "native_success": success if status == "completed" else None}
    if case["protocol"] == "remain" and status == "completed":
        row["metrics"] = {name: success for name in
                          ("joint_success", "stable_final_success", "task_success_by_horizon")}
    return row


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_plan_is_exact_ten_cases_and_explicit_two_protocol_budgets(config):
    before = deepcopy(config)
    plan = regression.build_plan(config)
    assert config == before
    assert plan["purpose"] == "normal00-capability-regression"
    assert plan["complete_paired_benchmark"] is False
    assert plan["expected"] == 10
    assert plan["expected_by_protocol"] == {"official": 5, "remain": 5}
    assert len({case["id"] for case in plan["cases"]}) == 10
    assert [(case["initial_state_index"], case["protocol"]) for case in plan["cases"]] == [
        (index, protocol) for index in range(5) for protocol in ("official", "remain")]
    budget = plan["budget"]
    assert budget["max_policy_control_steps"] == 5950
    assert budget["official_warmup_steps"] == 50
    assert budget["max_rollout_physics_steps"] == 6000
    assert budget["separate_remain_preparation_steps"] == 1150
    assert budget["max_policy_queries"] == 745
    assert budget["model_loads"] == 10
    assert budget["wall_clock_estimate_seconds"] is None
    assert plan["checkpoint_bytes_verified"] is False
    assert "not_checked" in plan["resource_validation"]
    for case in plan["cases"]:
        assert case["horizon"] == 520 and case["policy_seed"] == 7
        assert case["max_chunk_steps"] == 8
        if case["protocol"] == "official":
            assert (case["warmup_steps"], case["retention_steps"], case["env_seed"]) == (10, 0, 0)
            assert case["settle_steps"] == case["preparation_audit_steps"] == 0
            assert case["environment_interpreter"] == config["runtime"]["python_executable"]
        else:
            assert (case["warmup_steps"], case["retention_steps"]) == (0, 150)
            assert (case["settle_steps"], case["preparation_audit_steps"]) == (80, 150)
            assert case["env_seed"] == case["initial_state_index"]
            assert case["environment_interpreter"] == sys.executable


@pytest.mark.parametrize("protocol", ["official", "remain", "both"])
def test_plan_preserves_requested_noncontiguous_index_order(config, protocol):
    plan = regression.build_plan(config, indices=[4, 0, 9], protocol=protocol)
    names = ["official", "remain"] if protocol == "both" else [protocol]
    assert [(case["initial_state_index"], case["protocol"]) for case in plan["cases"]] == [
        (index, name) for index in (4, 0, 9) for name in names]
    assert plan["indices"] == [4, 0, 9]


@pytest.mark.parametrize("indices", [[], [1, 1], [-1], [True], [1.0], "0 1", None])
def test_plan_rejects_ambiguous_or_duplicate_indices(config, indices):
    with pytest.raises(ValueError):
        regression.build_plan(config, indices=indices)


@pytest.mark.parametrize("section,key,value", [
    ("execution", "random_seed", 8), ("execution", "random_seed", True),
    ("execution", "max_chunk_steps", 5), ("adapter_options", "random_seed", 0),
    ("adapter_options", "repo_revision", "other-code"),
    ("adapter_options", "suite", "libero_90"),
    ("checkpoint_source", "revision", "other-weights"),
    ("runtime", "startup_timeout_seconds", float("nan")),
])
def test_plan_refuses_different_reviewed_model_contract(config, section, key, value):
    config[section][key] = value
    with pytest.raises(ValueError):
        regression.build_plan(config)


def test_summary_keeps_error_unknown_missing_and_protocol_denominators_separate(config):
    plan = regression.build_plan(config)
    cases = plan["cases"]
    rows = [result_for(plan, cases[0]),
            result_for(plan, cases[2], status="preparation_error", prepared=False, policy_started=False),
            result_for(plan, cases[4], status="model_load_error", prepared=True, policy_started=False),
            result_for(plan, cases[6], status="runtime_error", prepared=None, policy_started=None),
            result_for(plan, cases[1], success=False)]
    # One official case was entered and interrupted before producing a record.
    attempted = [row["id"] for row in rows] + [cases[8]["id"]]
    report = regression.summarize(plan, rows, attempted_ids=attempted)
    assert (report["expected"], report["attempted"], report["completed"], report["missing"]) == (10, 6, 2, 5)
    assert report["pool_protocol_scores"] is False and report["uir"] is None
    official, remain = report["by_protocol"]
    assert (official["expected"], official["attempted"], official["completed"], official["missing"]) == (5, 5, 1, 1)
    assert official["prepared"] == 2 and official["policy_started"] == 1
    assert official["preparation_status_unknown"] == official["policy_start_status_unknown"] == 1
    assert official["preparation_error"] == official["model_load_error"] == official["runtime_error"] == 1
    assert official["common_success"] == {
        "numerator": 1, "denominator": 1, "rate": 1.0, "conservative_expected_rate": 0.2}
    assert (remain["expected"], remain["attempted"], remain["completed"], remain["missing"]) == (5, 1, 1, 4)
    assert remain["common_success"]["rate"] == 0.0
    assert remain["remain_metrics"]["joint_success"]["rate"] == 0.0
    assert cases[8]["id"] in official["missing_ids"]


def test_no_valid_results_means_unknown_rates_not_zero_valid_rate(config):
    plan = regression.build_plan(config)
    report = regression.summarize(plan, [])
    assert report["attempted"] == report["completed"] == 0 and report["missing"] == 10
    for group in report["by_protocol"]:
        assert group["common_success"]["rate"] is None
        assert group["common_success"]["denominator"] == 0
        assert group["common_success"]["conservative_expected_rate"] == 0.0


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_id", "wrong_index_type", "wrong_protocol",
                                      "wrong_plan", "unknown_status", "error_with_success", "unattempted"])
def test_summary_rejects_unbound_or_unscorable_result(config, mutation):
    plan = regression.build_plan(config, indices=[0])
    row = result_for(plan, plan["cases"][0])
    rows, attempted = [row], None
    if mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation == "unknown_id":
        row["id"] = "not-planned"
    elif mutation == "wrong_index_type":
        row["initial_state_index"] = False
    elif mutation == "wrong_protocol":
        row["protocol"] = "remain"
    elif mutation == "wrong_plan":
        row["plan_hash"] = "wrong"
    elif mutation == "unknown_status":
        row["status"] = "skipped"
    elif mutation == "error_with_success":
        row["status"] = "runtime_error"
    elif mutation == "unattempted":
        attempted = []
    with pytest.raises(ValueError):
        regression.summarize(plan, rows, attempted_ids=attempted)


def test_execution_calls_each_exact_case_once_with_distinct_new_request_paths(config, tmp_path):
    plan = regression.build_plan(config, indices=[4, 0])
    seen = []

    def execute(runtime, case, directory, video_config, **paths):
        assert not directory.exists()  # Child owns mkdir; parent cannot reuse prior case output.
        assert paths["request_path"].is_file()
        request = read_json(paths["request_path"])
        assert request["case"] == case and request["config"] == runtime
        assert request["video_config"] == video_config == plan["video_config"]
        assert Path(runtime["adapter_options"]["checkpoint"]).is_absolute()
        assert Path(runtime["runtime"]["python_executable"]).is_absolute()
        seen.append((case["id"], directory, paths["request_path"], paths["log_path"]))
        directory.mkdir()
        return result_for(plan, case)

    output = tmp_path / "run"
    report = regression.run_plan(config, plan, output, executor=execute)
    assert [row[0] for row in seen] == [case["id"] for case in plan["cases"]]
    assert all(len({row[index] for row in seen}) == 4 for index in range(1, 4))
    assert report["completed"] == report["expected"] == 4
    assert read_json(output / "run.json")["status"] == "finished"
    assert read_json(output / "plan.json") == plan


def test_executor_failure_and_wrong_previous_identity_remain_current_case_errors(config, tmp_path):
    plan = regression.build_plan(config, indices=[0, 1], protocol="official")
    previous = result_for(plan, plan["cases"][0])
    seen = []

    def execute(runtime, case, directory, video_config, **paths):
        seen.append(case["id"])
        return deepcopy(previous)  # Second process wrongly emits first case identity.

    output = tmp_path / "wrong-identity"
    report = regression.run_plan(config, plan, output, executor=execute)
    run = read_json(output / "run.json")
    assert seen == [case["id"] for case in plan["cases"]]
    assert run["status"] == "finished_with_errors"
    assert run["results"][1]["id"] == plan["cases"][1]["id"]
    assert run["results"][1]["status"] == "runtime_error"
    assert run["results"][1]["common_success"] is None
    assert report["by_protocol"][0]["runtime_error"] == 1
    assert report["by_protocol"][0]["common_success"]["conservative_expected_rate"] == 0.5


def test_executor_exception_does_not_replace_index_or_guess_preparation_status(config, tmp_path):
    plan = regression.build_plan(config, indices=[4, 0], protocol="remain")
    seen = []

    def execute(runtime, case, directory, video_config, **paths):
        seen.append(case["initial_state_index"])
        if len(seen) == 1:
            raise RuntimeError("synthetic child crash before result")
        return result_for(plan, case, success=False)

    report = regression.run_plan(config, plan, tmp_path / "errors", executor=execute)
    assert seen == [4, 0]
    group = report["by_protocol"][0]
    assert (group["expected"], group["attempted"], group["completed"], group["missing"]) == (2, 2, 1, 0)
    assert group["runtime_error"] == group["preparation_status_unknown"] == group["policy_start_status_unknown"] == 1
    assert group["common_success"]["denominator"] == 1


def test_keyboard_interrupt_preserves_fixed_missing_denominator_and_attempted_boundary(config, tmp_path):
    plan = regression.build_plan(config, indices=[0, 1, 2], protocol="official")
    count = 0

    def execute(runtime, case, directory, video_config, **paths):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt("synthetic cancellation")
        return result_for(plan, case)

    output = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        regression.run_plan(config, plan, output, executor=execute)
    run, report = read_json(output / "run.json"), read_json(output / "summary.json")
    assert run["status"] == "aborted" and count == 2
    assert (report["expected"], report["attempted"], report["completed"], report["missing"]) == (3, 2, 1, 2)
    assert report["by_protocol"][0]["common_success"]["conservative_expected_rate"] == 1 / 3


def test_existing_output_and_altered_plan_are_refused_before_execution(config, tmp_path):
    plan = regression.build_plan(config, indices=[0], protocol="official")
    output = tmp_path / "history"
    output.mkdir()
    sentinel = output / "summary.json"
    sentinel.write_bytes(b"preserve historical bytes\n")

    def forbidden(*args, **kwargs):
        pytest.fail("executor must not run")

    with pytest.raises(FileExistsError):
        regression.run_plan(config, plan, output, executor=forbidden)
    assert sentinel.read_bytes() == b"preserve historical bytes\n"
    altered = deepcopy(plan)
    altered["cases"][0]["horizon"] = 521
    with pytest.raises(ValueError):
        regression.run_plan(config, altered, tmp_path / "changed-plan", executor=forbidden)
    assert not (tmp_path / "changed-plan").exists()


def test_dry_run_never_executes_or_creates_run_and_optional_plan_is_exclusive(config, tmp_path, monkeypatch, capsys):
    config_file, output, plan_file = tmp_path / "config.json", tmp_path / "future-run", tmp_path / "plan.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("dry run must not execute or prepare")

    monkeypatch.setattr(regression, "run_plan", forbidden)
    args = ["--config", str(config_file), "--task", "basket", "--indices", "4", "0",
            "--protocol", "both", "--out", str(output), "--dry-run", "--plan-out", str(plan_file),
            "--save-video", "--video-camera", "both", "--video-fps", "20", "--video-stride", "1"]
    assert regression.main(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == read_json(plan_file)
    assert printed["indices"] == [4, 0] and printed["expected"] == 4
    assert printed["video_config"] == {"enabled": True, "camera": "both", "fps": 20.0, "stride": 1}
    assert not output.exists()
    before = plan_file.read_bytes()
    with pytest.raises(FileExistsError):
        regression.main(args)
    assert plan_file.read_bytes() == before and not output.exists()


def test_dry_plan_cannot_create_files_inside_future_output(config, tmp_path):
    config_file, output = tmp_path / "config.json", tmp_path / "future-run"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        regression.main(["--config", str(config_file), "--indices", "0", "--out", str(output),
                         "--dry-run", "--plan-out", str(output / "plan.json")])
    assert not output.exists()


def test_subprocess_uses_protocol_interpreter_and_drops_foreign_environment(config, tmp_path, monkeypatch):
    plan = regression.build_plan(config, indices=[2])
    captured = []
    monkeypatch.setenv("PYTHONHOME", "foreign-python-home")
    monkeypatch.setenv("PYTHONPATH", "foreign-module-tree")
    monkeypatch.setenv("LIBERO_CONFIG_PATH", "remain-config")

    class Process:
        def __init__(self, command, **options):
            captured.append((command, options, self))
            request = read_json(Path(command[command.index("--request") + 1]))
            directory = Path(command[command.index("--out") + 1])
            directory.mkdir()
            (directory / "episode.json").write_text(json.dumps(result_for(plan, request["case"])), encoding="utf-8")

        def wait(self, timeout):
            assert timeout == 25
            return 0

    monkeypatch.setattr(regression.subprocess, "Popen", Process)
    for index, case in enumerate(plan["cases"]):
        request = tmp_path / f"request-{index}.json"
        request.write_text(json.dumps({"case": case}), encoding="utf-8")
        result = regression._execute_process(config, case, tmp_path / f"case-{index}", plan["video_config"],
                                             request_path=request, log_path=tmp_path / f"case-{index}.log", timeout=25)
        assert result["id"] == case["id"]
    assert captured[0][0][0] == config["runtime"]["python_executable"]
    assert captured[1][0][0] == sys.executable
    assert captured[0][2] is not captured[1][2]
    for _, options, _ in captured:
        environment = options["env"]
        assert "PYTHONHOME" not in environment
        assert environment["PYTHONPATH"] != "foreign-module-tree"
        assert environment["PYTHONHASHSEED"] == "7"
        assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert "LIBERO_CONFIG_PATH" not in captured[0][1]["env"]
    assert captured[1][1]["env"]["LIBERO_CONFIG_PATH"] == "remain-config"


def test_explicit_official_config_is_resolved_and_child_only_and_rejects_empty_values(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIBERO_CONFIG_PATH", "parent-remain-config")
    config["runtime"]["official_libero_config_path"] = "existing-native-config"
    before = deepcopy(config)
    normalized = regression._normalise_runtime_paths(config)
    expected = str((tmp_path / "existing-native-config").resolve())
    assert normalized["runtime"]["official_libero_config_path"] == expected
    assert config == before
    plan = regression.build_plan(config, indices=[0], protocol="official")
    case, directory, captured = plan["cases"][0], tmp_path / "case", []

    class Process:
        def __init__(self, command, **options):
            captured.append(options["env"])
            directory.mkdir()
            (directory / "episode.json").write_text(json.dumps(result_for(plan, case)), encoding="utf-8")

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(regression.subprocess, "Popen", Process)
    regression._execute_process(normalized, case, directory, plan["video_config"],
                                request_path=tmp_path / "request.json", log_path=tmp_path / "case.log", timeout=1)
    assert captured[0]["LIBERO_CONFIG_PATH"] == expected
    assert os.environ["LIBERO_CONFIG_PATH"] == "parent-remain-config"
    for invalid in ("", "   ", None, 7):
        changed = deepcopy(config)
        changed["runtime"]["official_libero_config_path"] = invalid
        with pytest.raises(ValueError):
            regression.build_plan(changed)


@pytest.mark.parametrize("failure", ["missing_result", "nonzero_completed", "timeout"])
def test_subprocess_failures_cannot_be_read_as_success(config, tmp_path, monkeypatch, failure):
    plan = regression.build_plan(config, indices=[0], protocol="official")
    case, directory = plan["cases"][0], tmp_path / "case"
    terminated = []

    class Process:
        def __init__(self, *args, **kwargs):
            if failure == "nonzero_completed":
                directory.mkdir()
                (directory / "episode.json").write_text(json.dumps(result_for(plan, case)), encoding="utf-8")

        def wait(self, timeout):
            if failure == "timeout":
                raise subprocess.TimeoutExpired("synthetic child", timeout)
            return 2

    monkeypatch.setattr(regression.subprocess, "Popen", Process)
    monkeypatch.setattr(regression, "_terminate", lambda process: terminated.append(process))
    error_type = subprocess.TimeoutExpired if failure == "timeout" else RuntimeError
    with pytest.raises(error_type):
        regression._execute_process(config, case, directory, plan["video_config"],
                                    request_path=tmp_path / "request.json", log_path=tmp_path / "child.log", timeout=1)
    assert len(terminated) == (1 if failure == "timeout" else 0)


@pytest.mark.parametrize("conflicting_identity", [False, True])
def test_case_worker_does_not_overwrite_conflicting_backend_identity(config, tmp_path, monkeypatch, conflicting_identity):
    plan = regression.build_plan(config, indices=[0], protocol="official")
    case = {**plan["cases"][0], "plan_hash": plan["plan_hash"]}
    output, request = tmp_path / "case", tmp_path / "request.json"
    request.write_text(json.dumps({"config": config, "case": case, "video_config": plan["video_config"]}), encoding="utf-8")
    fake = ModuleType("benchmark.remaining_goals.regression_env")

    def execute_case(actual_config, actual_case, directory, *, video_config):
        assert actual_config == config and actual_case == case and video_config == plan["video_config"]
        directory.mkdir()
        row = result_for(plan, case)
        if conflicting_identity:
            row["initial_state_index"] = 4
        return row

    fake.execute_case = execute_case
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    if conflicting_identity:
        with pytest.raises(ValueError):
            regression_worker.main(["--request", str(request), "--out", str(output)])
        assert not (output / "episode.json").exists()
    else:
        assert regression_worker.main(["--request", str(request), "--out", str(output)]) == 0
        assert read_json(output / "episode.json")["initial_state_index"] == 0
