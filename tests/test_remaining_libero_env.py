"""LIBERO bridge contract tests with fakes; not real simulator acceptance.

The fake mirrors official ControlEnv -> BDDL task nesting and its non-stepping
post-process / observable refresh APIs. No LIBERO, torch, or renderer is loaded.
"""

from copy import deepcopy
import collections
import hashlib
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import libero_env


_REAL_IDENTITY = libero_env.environment_identity
XML = '<mujoco model="test"><worldbody/></mujoco>'
OFFICIAL_GOALS = [["on", "object_a", "bin_a"], ["in", "object_b", "bin_b"]]


def sha256(value):
    return hashlib.sha256(value).hexdigest()


class FakeSim:
    def __init__(self, events):
        self.events = events
        self.state = np.zeros(4)
        self.xml = XML
        self.model = SimpleNamespace(get_xml=lambda: self.xml)
        self.data = SimpleNamespace(qacc_warmstart=np.ones(2))

    def get_state(self):
        return SimpleNamespace(flatten=lambda: self.state.copy())

    def set_state_from_flattened(self, state):
        self.events.append("set_state")
        self.state = state.copy()

    def forward(self):
        self.events.append("forward")


class FakeController:
    def __init__(self, sim):
        self.sim = sim
        self.cached_position = None
        self.goal_position = None

    def update(self, force=False):
        assert force is True
        self.sim.events.append("controller_update")
        self.cached_position = self.sim.state[1:].copy()

    def reset_goal(self):
        self.sim.events.append("controller_reset_goal")
        self.goal_position = self.cached_position.copy()


class FakeTask:
    def __init__(self):
        self.events = []
        self.sim = FakeSim(self.events)
        self.robots = [SimpleNamespace(controller=FakeController(self.sim))]
        self.parsed_problem = {"goal_state": deepcopy(OFFICIAL_GOALS)}
        self.done = False
        self.actions = []
        self.visual_state = 0
        self.raw = None
        self.disagree_success = False

    def _eval_predicate(self, predicate):
        index = {tuple(p): i + 1 for i, p in enumerate(OFFICIAL_GOALS)}[tuple(predicate)]
        return bool(self.sim.state[index] > .5)

    def _check_success(self):
        self.events.append("check_success")
        result = all(self._eval_predicate(p) for p in self.parsed_problem["goal_state"])
        return not result if self.disagree_success else result

    def _post_process(self):
        self.events.append("post_process")
        self.visual_state = int(self.sim.state[1])

    def _update_observables(self, force=False):
        assert force is True
        self.events.append("update_observables")
        image = np.arange(12, dtype=np.uint8).reshape(2, 2, 3) + self.visual_state
        self.raw = {
            "agentview_image": image, "robot0_eye_in_hand_image": image + 20,
            "robot0_eef_pos": self.sim.state[1:].copy(),
            "robot0_eef_quat": np.array([0., 0., 0., 1.]),
            "robot0_gripper_qpos": np.zeros(2), "robot0_joint_pos": np.zeros(7),
            "robot0_joint_vel": np.zeros(7),
            "object-state": np.array([999.]), "goal_mask": [True, False],
            "object_a_pos": np.array([1., 2., 3.]),
        }

    def _get_observations(self):
        # Official wrapper regeneration calls this without force_update.
        self.events.append("get_observations")
        return self.raw


class FakeControlEnv:
    """No __getattr__: mirrors the official wrapper's explicit delegation."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.env = FakeTask()
        self.closed = False
        self.done = False
        self.seed_value = None

    @property
    def sim(self):
        return self.env.sim

    @property
    def robots(self):
        return self.env.robots

    def seed(self, seed):
        self.seed_value = seed

    def reset(self):
        self.env.events.clear()
        self.env.events.append("reset")
        self.env.sim.state[:] = 0
        self.env.sim.data.qacc_warmstart[:] = 1
        self.env.visual_state = 0
        self.env.done = self.done = False
        self.env._update_observables(force=True)
        return self.env._get_observations()

    def check_success(self):
        return self.env._check_success()

    def step(self, action):
        assert not self.done and not self.env.done, "executing action in terminated episode"
        self.env.actions.append(list(action))
        self.env.sim.state[0] += .05
        self.env._post_process()
        self.env._update_observables(force=True)
        self.done = self.env.done = True
        return self.env._get_observations(), 1., True, {"goal_mask": [True, False]}

    def close(self):
        self.closed = True


@pytest.fixture
def fake_libero(tmp_path, monkeypatch):
    bddl_root = tmp_path / "bddl"
    (bddl_root / "table").mkdir(parents=True)
    bddl = bddl_root / "table" / "task.bddl"
    bddl.write_text("(define (problem test))", encoding="utf-8")
    package_dir = tmp_path / "libero_package"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("# fake package\n", encoding="utf-8")
    parent = ModuleType("libero")
    package = ModuleType("libero.libero")
    envs = ModuleType("libero.libero.envs")
    utils = ModuleType("libero.libero.envs.utils")
    utils.collections = collections
    errors = ModuleType("robosuite.utils.errors")
    errors.RandomizationError = type("RandomizationError", (Exception,), {})
    parent.libero = package
    package.__file__ = str(init_file)
    task = SimpleNamespace(name="test_task", language="put A and B away",
                           problem_folder="table", bddl_file="task.bddl")
    suite = SimpleNamespace(get_task=lambda task_id: task,
                            get_task_names=lambda: [task.name])
    package.benchmark = SimpleNamespace(get_benchmark_dict=lambda: {"test_suite": lambda: suite})
    package.get_libero_path = lambda name: str(bddl_root)
    package.envs = envs
    created = []

    def factory(**kwargs):
        env = FakeControlEnv(**kwargs)
        # Explicit native-task reset protocol used by the bounded helper.
        env.env.reset = env.reset
        created.append(env)
        return env

    envs.OffScreenRenderEnv = factory
    for name, module in (("libero", parent), ("libero.libero", package),
                         ("libero.libero.envs", envs), ("libero.libero.envs.utils", utils),
                         ("robosuite.utils.errors", errors)):
        monkeypatch.setitem(sys.modules, name, module)
    identity = {"name": "libero", "fingerprint": "frozen-fingerprint"}
    monkeypatch.setattr(libero_env, "environment_identity", lambda freq=20: deepcopy(identity))
    state = np.array([.75, 1., 0., .25])
    state_file = tmp_path / "state.npy"
    np.save(state_file, state)
    episode = {
        "suite": "test_suite", "libero_task_id": 0, "task_name": task.name,
        "instruction": task.language, "seed": 42,
        "state_path": "state.npy", "state_sha256": sha256(state_file.read_bytes()),
        "bddl_sha256": sha256(bddl.read_bytes()), "model_xml_sha256": sha256(XML.encode()),
        "goal_specs": [{"id": "A", "predicates": [OFFICIAL_GOALS[0]]},
                       {"id": "B", "predicates": [OFFICIAL_GOALS[1]]}],
    }
    return SimpleNamespace(config={"manifest_dir": str(tmp_path), "environment": identity},
                           episode=episode, state=state, state_file=state_file,
                           bddl=bddl, created=created, task=task, suite=suite,
                           package_dir=package_dir)


def test_reset_restores_exact_physics_controller_and_fresh_fixture_observation(fake_libero):
    f = fake_libero
    env = libero_env.LiberoGoalEnv(f.config)
    obs = env.reset(f.episode)
    wrapped = f.created[0]
    inner = wrapped.env
    np.testing.assert_array_equal(wrapped.sim.state, f.state)
    np.testing.assert_array_equal(wrapped.sim.data.qacc_warmstart, [0, 0])
    np.testing.assert_array_equal(inner.robots[0].controller.goal_position, f.state[1:])
    np.testing.assert_array_equal(obs["robot0_eef_pos"], f.state[1:])
    np.testing.assert_array_equal(obs["agentview_image"], np.arange(12).reshape(2, 2, 3) + 1)
    assert wrapped.seed_value == 42
    assert inner.actions == []
    assert inner.events[-9:] == ["set_state", "forward", "controller_update",
                                 "controller_reset_goal", "forward", "check_success", "post_process",
                                 "update_observables", "get_observations"]
    assert env.goal_values() == [True, False]


def test_observations_filter_privilege_copy_buffers_and_preserve_raw_orientation(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    obs = env.reset(fake_libero.episode)
    assert set(obs) == set(libero_env.OBSERVATION_KEYS)
    raw = fake_libero.created[0].env.raw
    for key in libero_env.OBSERVATION_KEYS:
        np.testing.assert_array_equal(obs[key], raw[key])
        assert not np.shares_memory(obs[key], raw[key])
    obs["agentview_image"][:] = 0
    assert raw["agentview_image"].any()


def test_reuse_same_task_rechecks_xml_and_state_without_recreating_environment(fake_libero):
    f = fake_libero
    env = libero_env.LiberoGoalEnv(f.config)
    env.reset(f.episode)
    env.step(np.zeros(7))
    env.reset(f.episode)
    assert len(f.created) == 1
    np.testing.assert_array_equal(env.env.sim.state, f.state)
    f.created[0].sim.xml += " "
    with pytest.raises(ValueError, match="model_xml_sha256"):
        env.reset(f.episode)
    with pytest.raises(RuntimeError, match="successful reset"):
        env.goal_values()


@pytest.mark.parametrize("field", ["state_sha256", "bddl_sha256", "model_xml_sha256"])
@pytest.mark.parametrize("replacement", [None, "0" * 64])
def test_missing_or_mismatched_hashes_never_fall_back(fake_libero, field, replacement):
    spec = deepcopy(fake_libero.episode)
    spec[field] = replacement
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    with pytest.raises(ValueError, match=field):
        env.reset(spec)
    with pytest.raises(RuntimeError, match="successful reset"):
        env.step(np.zeros(7))
    if fake_libero.created:
        assert "set_state" not in fake_libero.created[-1].env.events


def test_fingerprint_mismatch_fails_before_creating_simulator(fake_libero):
    config = deepcopy(fake_libero.config)
    config["environment"]["fingerprint"] = "other"
    with pytest.raises(ValueError, match="fingerprint"):
        libero_env.LiberoGoalEnv(config)
    assert not fake_libero.created


@pytest.mark.parametrize("field", ["task_name", "instruction"])
def test_native_task_identity_must_match_manifest(fake_libero, field):
    spec = deepcopy(fake_libero.episode)
    spec[field] = "incorrect"
    with pytest.raises(ValueError, match="ID/name/instruction"):
        libero_env.LiberoGoalEnv(fake_libero.config).reset(spec)
    assert not fake_libero.created


def test_cached_task_does_not_allow_modified_instruction_or_bddl(fake_libero):
    f = fake_libero
    env = libero_env.LiberoGoalEnv(f.config)
    env.reset(f.episode)
    spec = deepcopy(f.episode)
    spec["instruction"] = "shorter instruction"
    with pytest.raises(ValueError, match="inconsistent"):
        env.reset(spec)
    f.bddl.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="BDDL content changed"):
        env.reset(f.episode)


def test_file_replacement_after_schema_verification_is_rejected(fake_libero, monkeypatch):
    original_verify = libero_env.verify_state_file

    def replace_after_verify(episode, base_dir):
        path = original_verify(episode, base_dir)
        np.save(path, np.zeros(4))
        return path

    monkeypatch.setattr(libero_env, "verify_state_file", replace_after_verify)
    with pytest.raises(ValueError, match="between verification and restoration"):
        libero_env.LiberoGoalEnv(fake_libero.config).reset(fake_libero.episode)


def test_state_shape_mismatch_fails_before_setting_simulator_state(fake_libero):
    f = fake_libero
    np.save(f.state_file, np.zeros(8))
    f.episode["state_sha256"] = sha256(f.state_file.read_bytes())
    with pytest.raises(ValueError, match="state vector shape"):
        libero_env.LiberoGoalEnv(f.config).reset(f.episode)
    assert "set_state" not in f.created[0].env.events


@pytest.mark.parametrize("predicates", [
    [OFFICIAL_GOALS[0]], [OFFICIAL_GOALS[1], OFFICIAL_GOALS[1]],
    [["on", "other_object", "bin_a"]], [["and", OFFICIAL_GOALS[0]]], [],
])
def test_goal_groups_must_exactly_partition_official_predicates(fake_libero, predicates):
    spec = deepcopy(fake_libero.episode)
    spec["goal_specs"][1]["predicates"] = predicates
    with pytest.raises(ValueError, match="predicate|conjunction"):
        libero_env.LiberoGoalEnv(fake_libero.config).reset(spec)


def test_predicate_names_normalize_but_object_identity_does_not(fake_libero):
    spec = deepcopy(fake_libero.episode)
    spec["goal_specs"][0]["predicates"][0][0] = "On"
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(spec)
    assert env.goal_values() == [True, False]
    spec["goal_specs"][0]["predicates"][0][1] = "OBJECT_A"
    with pytest.raises(ValueError, match="partition"):
        env.reset(spec)


def test_grouped_truth_is_checked_against_official_success(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    fake_libero.created[0].env.disagree_success = True
    with pytest.raises(RuntimeError, match="disagree"):
        env.goal_values()


@pytest.mark.parametrize("broken_hook", ["_post_process", "_update_observables", "_get_observations"])
def test_missing_nonstepping_refresh_hooks_fail_closed(fake_libero, broken_hook):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    setattr(fake_libero.created[0].env, broken_hook, None)
    with pytest.raises((RuntimeError, TypeError)):
        env.reset(fake_libero.episode)
    with pytest.raises(RuntimeError, match="successful reset"):
        env.goal_values()


def test_type_error_inside_refresh_is_not_swallowed(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)

    def broken_post_process():
        raise TypeError("internal visualization bug")

    fake_libero.created[0].env._post_process = broken_post_process
    with pytest.raises(TypeError, match="internal visualization bug"):
        env.reset(fake_libero.episode)


def test_missing_controller_fails_instead_of_using_stale_goal(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    fake_libero.created[0].env.robots = []
    with pytest.raises(RuntimeError, match="controllers"):
        env.reset(fake_libero.episode)


def test_refresh_cannot_advance_or_change_physical_state(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    inner = fake_libero.created[0].env
    original = inner._post_process

    def mutating_refresh():
        original()
        inner.sim.state[0] += 1

    inner._post_process = mutating_refresh
    with pytest.raises(RuntimeError, match="changed simulator state"):
        env.reset(fake_libero.episode)


def test_steps_after_done_use_unmodified_decoded_action_and_hide_info(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    action = np.array([.1, -.2, .3, -.4, .5, -.6, .7])
    first = env.step(action)
    second = env.step(action)
    assert len(fake_libero.created[0].env.actions) == 2
    np.testing.assert_array_equal(fake_libero.created[0].env.actions, [action, action])
    assert set(first) == set(second) == set(libero_env.OBSERVATION_KEYS)


@pytest.mark.parametrize("action", [np.zeros(6), np.zeros((1, 7)), np.full(7, np.nan)])
def test_bad_decoded_actions_never_reach_libero(fake_libero, action):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    with pytest.raises(ValueError, match="decoded 7D"):
        env.step(action)
    assert not fake_libero.created[0].env.actions


def test_no_implicit_hold_and_explicit_hold_is_copied(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    with pytest.raises(RuntimeError, match="validated hold"):
        env.hold_action()
    action = [0, 0, 0, 0, 0, 0, -1]
    config = {**fake_libero.config, "hold_action": action, "hold_contract": "released-state validation"}
    explicit = libero_env.LiberoGoalEnv(config)
    action[0] = 99
    returned = explicit.hold_action()
    returned[1] = 99
    np.testing.assert_array_equal(explicit.hold_action(), [0, 0, 0, 0, 0, 0, -1])


@pytest.mark.parametrize("contract", [None, "", "   ", True])
def test_explicit_hold_requires_documented_contract(fake_libero, contract):
    config = {**fake_libero.config, "hold_action": [0] * 7, "hold_contract": contract}
    with pytest.raises(ValueError, match="hold_contract"):
        libero_env.LiberoGoalEnv(config)


def test_close_is_idempotent_and_invalidates_previous_episode(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    with pytest.raises(RuntimeError, match="successful reset"):
        env.goal_values()
    env.reset(fake_libero.episode)
    wrapper = fake_libero.created[0]
    env.close()
    env.close()
    assert wrapper.closed
    with pytest.raises(RuntimeError, match="successful reset"):
        env.step(np.zeros(7))


@pytest.mark.parametrize("explicit_stop", [False, True])
def test_bridge_runs_through_runner_without_privilege_or_done_shortcuts(fake_libero, explicit_stop):
    from benchmark.remaining_goals.runner import run_episode

    class Policy:
        def reset(self):
            pass

        def predict(self, obs, instruction):
            assert set(obs) == set(libero_env.OBSERVATION_KEYS)
            assert instruction == fake_libero.episode["instruction"]
            return None if explicit_stop else np.zeros((3, 7))

    config = {**fake_libero.config, "hold_action": [0, 0, 0, 0, 0, 0, -1],
              "hold_contract": "fake released-state controller"}
    spec = {**fake_libero.episode, "episode_id": "bridge-test", "task_id": "two-goals",
            "initial_mask": [True, False], "horizon": 2, "retention_steps": 1}
    result = run_episode(libero_env.LiberoGoalEnv(config), Policy(), spec)
    assert result["status"] == "completed", result["error"]
    assert result["n_steps"] == 3
    assert result["policy_queries"] == 1
    assert result["trace"][-1]["goals"] == [True, False]
    assert all(row["stopped"] == explicit_stop for row in result["trace"][1:])


def test_environment_identity_locks_source_version_and_control_frequency(fake_libero, monkeypatch):
    monkeypatch.setattr(libero_env.importlib.metadata, "version", lambda package: "1.0")
    identity = _REAL_IDENTITY(20)
    assert identity == _REAL_IDENTITY(20)
    assert identity["fingerprint"] != _REAL_IDENTITY(10)["fingerprint"]
    (fake_libero.package_dir / "changed.bddl").write_text("(goal)", encoding="utf-8")
    changed = _REAL_IDENTITY(20)
    assert identity["fingerprint"] != changed["fingerprint"]
    monkeypatch.setattr(libero_env.importlib.metadata, "version", lambda package: "2.0")
    assert changed["fingerprint"] != _REAL_IDENTITY(20)["fingerprint"]


@pytest.mark.parametrize("asset_name,original,changed", [
    ("meshes/object.obj", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
     b"v 0 0 0\nv 2 0 0\nv 0 1 0\nf 1 2 3\n"),
    ("textures/wall.png", b"\x89PNG\r\n\x1a\ntexture-payload-a", b"\x89PNG\r\n\x1a\ntexture-payload-b"),
])
def test_actual_asset_bytes_change_environment_identity(fake_libero, asset_name, original, changed):
    asset = fake_libero.package_dir / "assets" / asset_name
    asset.parent.mkdir(parents=True)
    asset.write_bytes(original)
    first = _REAL_IDENTITY()
    asset.write_bytes(changed)
    second = _REAL_IDENTITY()
    assert first["lock"]["source_sha256"] == second["lock"]["source_sha256"]
    assert first["lock"]["assets_sha256"] != second["lock"]["assets_sha256"]
    assert first["fingerprint"] != second["fingerprint"]


def test_python_cache_files_do_not_change_asset_or_environment_lock(fake_libero):
    assets = fake_libero.package_dir / "assets"
    assets.mkdir()
    (assets / "object.obj").write_bytes(b"v 0 0 0\n")
    first = _REAL_IDENTITY()
    for folder in (fake_libero.package_dir, assets):
        cache = folder / "__pycache__"
        cache.mkdir()
        (cache / "generated.cpython-310.pyc").write_bytes(b"bytecode-cache")
    (assets / "legacy.pyc").write_bytes(b"legacy-bytecode-cache")
    (assets / "legacy.pyo").write_bytes(b"legacy-optimized-cache")
    assert _REAL_IDENTITY() == first


def test_asset_path_and_file_set_are_locked(fake_libero):
    assets = fake_libero.package_dir / "assets"
    assets.mkdir()
    original = assets / "first.obj"
    original.write_bytes(b"same-asset-bytes")
    first = _REAL_IDENTITY()
    original.rename(assets / "renamed.obj")
    renamed = _REAL_IDENTITY()
    assert first["lock"]["assets_sha256"] != renamed["lock"]["assets_sha256"]
    (assets / "extra.png").write_bytes(b"new-texture")
    assert renamed["fingerprint"] != _REAL_IDENTITY()["fingerprint"]


def test_large_assets_are_hashed_without_read_bytes(fake_libero, monkeypatch):
    from pathlib import Path
    assets = fake_libero.package_dir / "assets"
    assets.mkdir()
    mesh = assets / "large.msh"
    mesh.write_bytes(b"mesh-payload" * 300000)
    expected = _REAL_IDENTITY()
    read_bytes = Path.read_bytes

    def guarded_read_bytes(path):
        if path.is_relative_to(assets):
            raise AssertionError("asset must be streamed instead of read_bytes")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    assert _REAL_IDENTITY() == expected


def test_create_scene_by_name_without_manifest_or_implicit_reset(fake_libero):
    f = fake_libero
    env, task, bddl = libero_env.create_scene(
        "test_suite", f.task.name, image_size=128, control_freq=10,
    )
    assert env is f.created[0]
    assert task is f.task
    assert bddl == f.bddl
    assert env.kwargs == {"bddl_file_name": str(f.bddl), "camera_heights": 128,
                          "camera_widths": 128, "control_freq": 10}
    assert env.seed_value is None
    assert env.env.events == []
    assert env.env.actions == []


@pytest.mark.parametrize("suite,name", [("missing", "test_task"),
                                        ("test_suite", "missing"),
                                        ("", "test_task"), ("test_suite", " ")])
def test_create_scene_rejects_unknown_or_empty_identity(fake_libero, suite, name):
    with pytest.raises(ValueError):
        libero_env.create_scene(suite, name)
    assert not fake_libero.created


@pytest.mark.parametrize("settings", [{"image_size": 0}, {"image_size": True},
                                      {"control_freq": -1}, {"control_freq": 20.5}])
def test_create_scene_rejects_invalid_settings(fake_libero, settings):
    with pytest.raises(ValueError, match="positive integer"):
        libero_env.create_scene("test_suite", "test_task", **settings)
    assert not fake_libero.created


def test_create_scene_rejects_ambiguous_name_and_missing_bddl(fake_libero):
    f = fake_libero
    f.suite.get_task_names = lambda: [f.task.name, f.task.name]
    with pytest.raises(ValueError, match="exactly once"):
        libero_env.create_scene("test_suite", f.task.name)
    f.suite.get_task_names = lambda: [f.task.name]
    f.task.bddl_file = "nonexistent.bddl"
    with pytest.raises(ValueError, match="BDDL file is missing"):
        libero_env.create_scene("test_suite", f.task.name)
    assert not f.created


def test_model_xml_hash_preserves_bytes_formatting_and_absolute_paths():
    env = FakeControlEnv()
    xml = '<mujoco><asset><mesh file="/install-a/mesh.obj"/></asset></mujoco>'
    env.sim.xml = xml
    expected = sha256(xml.encode("utf-8"))
    assert libero_env.model_xml_hash(env) == expected
    env.sim.xml = xml.encode("utf-8")
    assert libero_env.model_xml_hash(env) == expected
    env.sim.xml = xml + "\n"
    assert libero_env.model_xml_hash(env) != expected
    env.sim.xml = xml.replace("/install-a/", "/install-b/")
    assert libero_env.model_xml_hash(env) != expected


def test_model_xml_hash_rejects_non_xml_value():
    env = FakeControlEnv()
    env.sim.xml = None
    with pytest.raises(ValueError, match="text or bytes"):
        libero_env.model_xml_hash(env)


def test_restore_raw_state_refreshes_everything_without_manifest_reset_or_step():
    env = FakeControlEnv()
    state = np.array([.75, 1., 0., .25])
    original = state.copy()
    obs = libero_env.restore_raw_state(env, state)
    np.testing.assert_array_equal(state, original)
    np.testing.assert_array_equal(env.sim.state, original)
    np.testing.assert_array_equal(env.sim.data.qacc_warmstart, [0, 0])
    np.testing.assert_array_equal(env.env.robots[0].controller.goal_position, original[1:])
    np.testing.assert_array_equal(obs["robot0_eef_pos"], original[1:])
    assert env.env.events == ["set_state", "forward", "controller_update",
                              "controller_reset_goal", "forward", "check_success", "post_process",
                              "update_observables", "get_observations"]
    assert set(obs) == set(libero_env.OBSERVATION_KEYS)
    assert env.env.actions == []
    assert env.seed_value is None


def test_fresh_observation_uses_current_state_without_controller_reset_or_restore():
    env = FakeControlEnv()
    libero_env.restore_raw_state(env, np.array([.75, 1., 0., .25]))
    controller = env.env.robots[0].controller
    previous_goal = controller.goal_position.copy()
    env.sim.state[:] = [2., 0., 1., .8]
    state = env.sim.state.copy()
    env.env.events.clear()
    obs = libero_env.fresh_observation(env)
    np.testing.assert_array_equal(env.sim.state, state)
    np.testing.assert_array_equal(controller.goal_position, previous_goal)
    np.testing.assert_array_equal(obs["robot0_eef_pos"], state[1:])
    np.testing.assert_array_equal(obs["agentview_image"], np.arange(12).reshape(2, 2, 3))
    assert env.env.events == ["forward", "check_success", "post_process", "update_observables", "get_observations"]
    assert env.env.actions == []


def test_helpers_also_support_unwrapped_native_task():
    env = FakeTask()
    state = np.array([.5, 1., 0., .2])
    first = libero_env.restore_raw_state(env, state)
    second = libero_env.fresh_observation(env)
    np.testing.assert_array_equal(first["robot0_eef_pos"], second["robot0_eef_pos"])
    np.testing.assert_array_equal(env.sim.state, state)


@pytest.mark.parametrize("state", [np.zeros(3), np.zeros((1, 4)), [],
                                   [0, 0, 0, float("nan")], [0, 0, 0, float("inf")],
                                   ["a", "b", "c", "d"], np.ones(4, dtype=complex)])
def test_restore_raw_state_rejects_bad_state_before_mutation(state):
    env = FakeControlEnv()
    before = env.sim.state.copy()
    with pytest.raises(ValueError, match="state"):
        libero_env.restore_raw_state(env, state)
    np.testing.assert_array_equal(env.sim.state, before)
    assert "set_state" not in env.env.events


def test_restore_raw_state_detects_controller_mutating_physics():
    env = FakeControlEnv()
    controller = env.env.robots[0].controller
    update = controller.update

    def mutating_controller(force=False):
        env.sim.state[3] += .1
        update(force=force)

    controller.update = mutating_controller
    with pytest.raises(RuntimeError, match="changed simulator state"):
        libero_env.restore_raw_state(env, np.zeros(4))


def test_fresh_observation_detects_success_hook_mutating_physics():
    env = FakeControlEnv()

    def mutating_success():
        env.sim.state[0] += .1
        return False

    env.check_success = mutating_success
    with pytest.raises(RuntimeError, match="changed simulator state"):
        libero_env.fresh_observation(env)


def test_native_stale_observations_are_replaced_after_exactly_one_physics_step(fake_libero):
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    initial = env.reset(fake_libero.episode)
    wrapped = fake_libero.created[0]
    native = wrapped.env
    controller = native.robots[0].controller
    original_goal = controller.goal_position.copy()
    derived_position = native.sim.state[1:].copy()
    original_forward = native.sim.forward
    original_update = native._update_observables
    action = np.array([.1, -.2, .3, -.4, .5, -.6, 1.])

    def forward():
        nonlocal derived_position
        original_forward()
        derived_position = native.sim.state[1:].copy()

    def update(force=False):
        original_update(force=force)
        # Model the derived Cartesian data which only forward brings current.
        native.raw["robot0_eef_pos"] = derived_position.copy()

    def stale_step(decoded):
        native.actions.append(decoded)
        stale = deepcopy(native.raw)
        native.sim.state[:] = [.8, 2., 1., .75]
        wrapped.done = native.done = True
        # No final forward/cache refresh, as in the stale native observation
        # case found in the real 150-step candidate audits.
        return stale, 1., True, {"goal_mask": [True, True]}

    native.sim.forward = forward
    native._update_observables = update
    wrapped.step = stale_step
    native.events.clear()
    returned = env.step(action)
    np.testing.assert_array_equal(native.sim.state, [.8, 2., 1., .75])
    assert len(native.actions) == 1 and native.actions[0] == action.tolist()
    np.testing.assert_array_equal(returned["robot0_eef_pos"], [2., 1., .75])
    np.testing.assert_array_equal(returned["agentview_image"], np.arange(12).reshape(2, 2, 3) + 2)
    np.testing.assert_array_equal(returned["robot0_eye_in_hand_image"], np.arange(12).reshape(2, 2, 3) + 22)
    assert not np.array_equal(returned["agentview_image"], initial["agentview_image"])
    assert set(returned) == set(libero_env.OBSERVATION_KEYS)
    assert native.events == ["forward", "check_success", "post_process", "update_observables", "get_observations"]
    np.testing.assert_array_equal(controller.goal_position, original_goal)
    # A second independent synchronization agrees exactly, without another
    # physical step or a tolerance increase.
    refreshed = libero_env.fresh_observation(wrapped)
    for key in returned:
        np.testing.assert_array_equal(returned[key], refreshed[key])
    assert len(native.actions) == 1


def test_synchronization_rejects_forward_that_advances_physics():
    env = FakeControlEnv()

    def bad_forward():
        env.sim.state[0] += .002

    env.sim.forward = bad_forward
    with pytest.raises(RuntimeError, match="non-stepping observation refresh changed simulator state"):
        libero_env.fresh_observation(env)


def test_synchronization_requires_explicit_forward_hook():
    env = FakeControlEnv()
    env.sim.forward = None
    with pytest.raises(RuntimeError, match="forward hook is missing"):
        libero_env.fresh_observation(env)


def test_manifest_reset_uses_same_public_restore_helper(fake_libero, monkeypatch):
    original = libero_env.restore_raw_state
    calls = []

    def wrapped(env, state):
        calls.append((env, state.copy()))
        return original(env, state)

    monkeypatch.setattr(libero_env, "restore_raw_state", wrapped)
    env = libero_env.LiberoGoalEnv(fake_libero.config)
    env.reset(fake_libero.episode)
    assert len(calls) == 1
    assert calls[0][0] is fake_libero.created[0]
    np.testing.assert_array_equal(calls[0][1], fake_libero.state)
