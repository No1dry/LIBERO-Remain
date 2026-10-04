"""Runtime compatibility is local, bounded and included in the fingerprint."""

import collections
import collections.abc
from copy import deepcopy
import hashlib
import random
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from benchmark.remaining_goals import libero_compat as compat, libero_env


def test_iterable_shim_changes_only_libero_utils_binding(monkeypatch):
    module = ModuleType("libero.libero.envs.utils")
    module.collections = collections
    monkeypatch.setitem(sys.modules, module.__name__, module)
    before = vars(collections).copy()
    compat.apply_libero_compat()
    first = module.collections
    assert first is not collections
    assert first.Iterable is collections.abc.Iterable
    assert isinstance((1, 2), first.Iterable)
    assert first.OrderedDict is collections.OrderedDict
    assert vars(collections) == before
    compat.apply_libero_compat()
    assert module.collections is first
    with pytest.raises(AttributeError):
        _ = first.unavailable_attribute


def test_foreign_collections_patch_is_not_silently_overwritten(monkeypatch):
    module = ModuleType("libero.libero.envs.utils")
    foreign = SimpleNamespace(Iterable=object)
    module.collections = foreign
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(RuntimeError, match="foreign patch"):
        compat.apply_libero_compat()
    assert module.collections is foreign


class RandomizationError(Exception):
    pass


@pytest.fixture
def reset_errors(monkeypatch):
    monkeypatch.setattr(compat, "_randomization_error_type", lambda: RandomizationError)


@pytest.mark.parametrize("wrapped", [False, True])
def test_only_randomization_is_retried_and_wrapper_loop_is_never_called(reset_errors, wrapped):
    attempts = []
    observation = {"pixels": "native observation"}

    def native_reset():
        attempts.append(1)
        if len(attempts) < 3:
            raise RandomizationError("overlap")
        return observation

    native = SimpleNamespace(parsed_problem={}, reset=native_reset)
    env = SimpleNamespace(env=native, reset=lambda: pytest.fail("unsafe wrapper was called")) if wrapped else native
    assert compat.reset_scene(env, max_attempts=3) is observation
    assert len(attempts) == 3


def test_exhausted_sampling_is_bounded_and_preserves_last_error(reset_errors):
    attempts = []
    error = RandomizationError("unable to place an object")

    def fail():
        attempts.append(1)
        raise error

    env = SimpleNamespace(env=SimpleNamespace(parsed_problem={}, reset=fail))
    with pytest.raises(RuntimeError, match="after 4 RandomizationError attempts") as caught:
        compat.reset_scene(env, max_attempts=4)
    assert len(attempts) == 4 and caught.value.__cause__ is error


@pytest.mark.parametrize("error", [AttributeError("bad API"), OSError("missing asset"),
                                    RuntimeError("renderer"), KeyboardInterrupt()])
def test_nonrandomization_errors_propagate_immediately(reset_errors, error):
    attempts = []

    def fail():
        attempts.append(1)
        raise error

    native = SimpleNamespace(parsed_problem={}, reset=fail)
    with pytest.raises(type(error)) as caught:
        compat.reset_scene(native)
    assert caught.value is error and len(attempts) == 1


@pytest.mark.parametrize("limit", [0, -1, True, 2.5])
def test_invalid_attempt_limit_fails_before_reset(reset_errors, limit):
    with pytest.raises(ValueError, match="positive integer"):
        compat.reset_scene(SimpleNamespace(), max_attempts=limit)


def test_missing_native_interface_has_no_fake_or_wrapper_fallback():
    wrapper = SimpleNamespace(reset=lambda: pytest.fail("wrapper fallback"))
    with pytest.raises(TypeError, match="native LIBERO task"):
        compat.reset_scene(wrapper)


def test_compatibility_implementation_and_rules_are_explicitly_hashed():
    identity = compat.compatibility_identity()
    assert identity["source_sha256"] == hashlib.sha256(Path(compat.__file__).read_bytes()).hexdigest()
    assert identity["rules"] == list(compat.RULES)
    assert "post-step-synchronized-observations-forward-force-v1" in identity["rules"]
    assert "forward-free-ball-unit-quaternion-roundoff-16eps-restore-bits-v1" in identity["rules"]
    assert "panda-gripper-qpos-inverse-position-servo-clipped-command-and-ctrl-v1" in identity["rules"]
    assert "hard-reset-rebuild-bddl-property-samplers-without-history-accumulation-v1" in identity["rules"]
    assert identity["bridge_source_sha256"] == hashlib.sha256(Path(libero_env.__file__).read_bytes()).hexdigest()


def test_environment_fingerprint_changes_when_compatibility_changes(tmp_path, monkeypatch):
    package = ModuleType("libero.libero")
    package.__file__ = str(tmp_path / "__init__.py")
    Path(package.__file__).write_text("# official fixture", encoding="utf-8")
    parent = ModuleType("libero")
    parent.libero = package
    monkeypatch.setitem(sys.modules, "libero", parent)
    monkeypatch.setitem(sys.modules, "libero.libero", package)
    monkeypatch.setattr(libero_env.importlib.metadata, "version", lambda name: "1.0")
    first = libero_env.environment_identity()
    assert first["lock"]["compatibility"] == compat.compatibility_identity()
    altered = deepcopy(first["lock"]["compatibility"])
    altered["source_sha256"] = "different-implementation"
    monkeypatch.setattr(libero_env, "compatibility_identity", lambda: altered)
    second = libero_env.environment_identity()
    assert first["lock"]["source_sha256"] == second["lock"]["source_sha256"]
    assert first["fingerprint"] != second["fingerprint"]


class OpenSampler:
    def __init__(self, name="cabinet_top", state_type="open", joint_ranges=(-.16, -.14)):
        self.name = name
        self.state_type = state_type
        self.joint_ranges = joint_ranges
        self.mujoco_objects = []


class SwitchSampler(OpenSampler):
    pass


def property_scene(monkeypatch, *, failures=0):
    monkeypatch.setattr(compat, "_property_sampler_types", lambda: (OpenSampler, SwitchSampler))
    native = SimpleNamespace(hard_reset=True, deterministic_reset=False,
                             parsed_problem={"initial_state": [["open", "cabinet_top"]]},
                             object_property_initializers=[OpenSampler()])
    native.get_object = lambda name: SimpleNamespace(object_properties={
        "articulation": {"default_open_ranges": [-.16, -.14]}})
    native.rng = random.Random(0)
    native.calls = 0
    native.sampler_counts = []

    def reset():
        native.calls += 1
        # Mirrors upstream _load_model appending without clearing the list.
        if native.hard_reset and not native.deterministic_reset:
            native.object_property_initializers.append(OpenSampler())
        native.sampler_counts.append(len(native.object_property_initializers))
        for _ in native.object_property_initializers:
            native.rng.random()
        fixture_position = native.rng.random()
        if native.calls <= failures:
            raise RandomizationError("retry placement")
        return fixture_position

    native.reset = reset
    return native


def test_repeated_hard_resets_keep_fixture_rng_independent_of_history(reset_errors, monkeypatch):
    native = property_scene(monkeypatch)
    positions = []
    for _ in range(3):
        native.rng.seed(19)
        positions.append(compat.reset_scene(native))
    assert positions[0] == positions[1] == positions[2]
    assert native.sampler_counts == [1, 1, 1]
    # Distinguish the regression from a test that would pass without the fix.
    unfixed = property_scene(monkeypatch)
    unfixed.rng.seed(19)
    first = unfixed.reset()
    unfixed.rng.seed(19)
    assert unfixed.reset() != first


def test_randomization_retries_rebuild_without_appending_extra_property_samplers(reset_errors, monkeypatch):
    native = property_scene(monkeypatch, failures=2)
    assert isinstance(compat.reset_scene(native, max_attempts=3), float)
    assert native.sampler_counts == [1, 1, 1]


@pytest.mark.parametrize("hard,deterministic", [(False, False), (True, True), (False, True)])
def test_resets_without_model_regeneration_preserve_property_samplers(reset_errors, monkeypatch, hard, deterministic):
    native = property_scene(monkeypatch)
    native.hard_reset, native.deterministic_reset = hard, deterministic
    original = native.object_property_initializers
    compat.reset_scene(native)
    assert native.object_property_initializers is original
    assert native.sampler_counts == [1]


@pytest.mark.parametrize("corruption", ["foreign_type", "undeclared_target", "modified_range", "custom_objects", "missing_list"])
def test_unknown_property_sampler_contract_is_not_silently_discarded(reset_errors, monkeypatch, corruption):
    native = property_scene(monkeypatch)
    if corruption == "foreign_type":
        native.object_property_initializers.append(object())
    elif corruption == "undeclared_target":
        native.object_property_initializers[0].name = "other"
    elif corruption == "modified_range":
        native.object_property_initializers[0].joint_ranges = [-1., 1.]
    elif corruption == "custom_objects":
        native.object_property_initializers[0].mujoco_objects = [object()]
    else:
        del native.object_property_initializers
    original = getattr(native, "object_property_initializers", None)
    with pytest.raises(RuntimeError, match="property sampler"):
        compat.reset_scene(native)
    assert getattr(native, "object_property_initializers", None) is original
    assert native.calls == 0
