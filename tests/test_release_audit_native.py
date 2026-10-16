"""CPU-only native-sidecar tests; no MuJoCo model/environment is constructed."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.finish import release_audit_native as module


class FakeModel:
    def __init__(self):
        self._model = self
        self.nq = self.nv = 3
        self.na, self.nu = 0, 2
        self.nbody, self.ngeom, self.nsite, self.njnt = 6, 6, 1, 3
        self.nmesh, self.npair, self.nexclude = 1, 1, 1
        self.nmeshgraph = 0
        self.geom_names = ["soup_collision", "sauce_collision", "hand_collision", "left_pad", "right_pad", None]
        self.body_names = ["world", "soup", "sauce", "hand", "left", "right"]
        self.geom_type = np.array([6, 6, 7, 6, 6, 2], dtype=np.int32)
        self.geom_bodyid = np.array([1, 2, 3, 4, 5, 3], dtype=np.int32)
        self.geom_dataid = np.array([-1, -1, 0, -1, -1, -1], dtype=np.int32)
        for key, value in (("geom_contype", 1), ("geom_conaffinity", 1), ("geom_condim", 3),
                           ("geom_group", 0), ("geom_priority", 0)):
            setattr(self, key, np.full(6, value, dtype=np.int32))
        self.geom_size = np.full((6, 3), .01)
        self.geom_pos = np.zeros((6, 3))
        self.geom_quat = np.tile([1., 0., 0., 0.], (6, 1))
        self.geom_friction = np.tile([1., .005, .0001], (6, 1))
        self.geom_solref = np.tile([.02, 1.], (6, 1))
        self.geom_solimp = np.tile([.9, .95, .001, .5, 2.], (6, 1))
        self.geom_rbound = np.array([.02, .025, .04, .005, .005, .01])
        self.geom_margin = np.full(6, .001)
        self.geom_gap = np.zeros(6)
        self.geom_solmix = np.ones(6)
        self.body_parentid = np.array([0, 0, 0, 0, 3, 3], dtype=np.int32)
        self.body_weldid = np.arange(6, dtype=np.int32)
        self.pair_geom1, self.pair_geom2 = np.array([0]), np.array([3])
        self.pair_dim, self.pair_margin, self.pair_gap = np.array([3]), np.array([.003]), np.array([.001])
        self.pair_signature = np.array([(2 << 16) + 5], dtype=np.int32)
        self.pair_solref = np.array([[.02, 1.]])
        self.pair_solreffriction = np.zeros((1, 2))
        self.pair_solimp = np.array([[.9, .95, .001, .5, 2.]])
        self.pair_friction = np.array([[1., 1., .005, .0001, .0001]])
        self.exclude_signature = np.array([(2 << 16) + 3], dtype=np.int32)
        self.mesh_vertadr = np.array([0])
        self.mesh_vertnum = np.array([4])
        self.mesh_faceadr = np.array([0])
        self.mesh_facenum = np.array([4])
        self.mesh_vert = np.array([[0, 0, 0], [0, 0, .01], [0, .01, 0], [.01, 0, 0]], dtype=np.float32)
        self.mesh_face = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int32)
        self.mesh_graphadr = np.array([-1], dtype=np.int32)
        self.mesh_graph = np.array([], dtype=np.int32)
        self.opt = SimpleNamespace(timestep=.002, collision=0, disableflags=0, enableflags=0,
                                   integrator=0, solver=2, cone=0)
        self.xml = "<mujoco model='synthetic-only'/ >".replace("/ >", "/>")

    def geom_name2id(self, name):
        return self.geom_names.index(name)

    def geom_id2name(self, index):
        return self.geom_names[index]

    def body_id2name(self, index):
        return self.body_names[index]

    def mesh_id2name(self, index):
        assert index == 0
        return "synthetic_hand_mesh"

    def get_xml(self):
        return self.xml


class FakeBackend:
    mjtState = SimpleNamespace(mjSTATE_INTEGRATION=4095)

    def __init__(self):
        self.called = []
        for name in module.NATIVE_FUNCTIONS:
            if name not in module.READ_FUNCTIONS:
                setattr(self, name, self._function(name))

    def _function(self, name):
        def call(model, data, *args, **kwargs):
            self.called.append(name)
            if name in ("mj_step", "mj_step2"):
                data.time += .002
            if name in ("mj_resetData", "mj_resetDataKeyframe"):
                data.time = 0.
        return call

    def mj_stateSize(self, model, mask):
        assert mask == 4095
        return 12

    def mj_getState(self, model, data, result, mask):
        assert mask == 4095
        result[:] = np.concatenate(([data.time], data.qpos, data.qvel, data.ctrl, data.qacc_warmstart))


def make_fake():
    model = FakeModel()
    contact = SimpleNamespace(geom1=1, geom2=4, dist=-.0003, pos=np.array([0., .01, .02]),
                              frame=np.eye(3).reshape(9), dim=3, exclude=0, efc_address=0,
                              includemargin=.001, friction=np.array([1., 1., .005, .0001, .0001]))
    data = SimpleNamespace(time=0., ctrl=np.array([.2, -.2]), qpos=np.array([0., -0., .3]),
                           qvel=np.zeros(3), qacc_warmstart=np.zeros(3), ncon=1, nefc=3, contact=[contact],
                           geom_xpos=np.array([[0, 0, .2], [.03, .01, .02], [0, 0, 0], [-.03, 0, 0], [.03, 0, 0], [2, 0, 0]], dtype=float),
                           geom_xmat=np.tile(np.eye(3).reshape(9), (6, 1)))
    data._data = data
    controller = SimpleNamespace(goal_pos=np.array([.1, .2, .3]), goal_ori=np.eye(3),
                                 relative_ori=np.zeros(3), ori_ref=None, new_update=False,
                                 interpolator_pos=None, interpolator_ori=None, control_freq=20,
                                 rng=np.random.default_rng(23))
    gripper = SimpleNamespace(current_action=np.array([.2, -.2]),
                              contact_geoms=["hand_collision", "left_pad", "right_pad"],
                              important_geoms={"left_fingerpad": ["left_pad"], "right_fingerpad": ["right_pad"]})
    native = SimpleNamespace(sim=SimpleNamespace(model=model, data=data), timestep=0, cur_time=0.,
                             model_timestep=.002, control_timestep=.05)
    contract = SimpleNamespace(env=native, inner=native, gripper=gripper,
                               hold=SimpleNamespace(controller=controller),
                               objects={name: SimpleNamespace(contact_geoms=[geometry]) for name, geometry in
                                        zip(module.TARGETS, ("soup_collision", "sauce_collision"))})
    env = SimpleNamespace(env=native, finish_contract=contract)
    return env, FakeBackend()


@pytest.fixture
def setup(monkeypatch, tmp_path):
    env, backend = make_fake()
    monkeypatch.setattr(module, "_runtime_metadata", lambda backend: {"test_only": True, "native_executed": False})
    recorder = module.NativeRecorder(env, tmp_path / "output", backend=backend)
    return recorder, env, backend


def test_import_is_lazy_for_native_and_models(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"mujoco", "robosuite", "libero", "torch"}:
            pytest.fail("diagnostic module import attempted native/model import")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    spec = importlib.util.spec_from_file_location("isolated_release_native", module.__file__)
    isolated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated)
    assert isolated.NativeCallMonitor().backend is None


def test_version_gate_precedes_native_import(monkeypatch):
    monkeypatch.setattr(module.importlib.metadata, "version", lambda name: "3.0.0")
    monkeypatch.setattr(module.importlib, "import_module", lambda *args: pytest.fail("wrong version imported"))
    with pytest.raises(module.TechnicalError, match="2.3.7"):
        module._load_backend()


def test_static_maps_original_geometries_assets_mesh_and_source_hashes(setup, tmp_path):
    recorder, env, backend = setup
    asset = tmp_path / "tiny.stl"
    asset.write_bytes(b"synthetic fixture, not a real triangle mesh")
    env.env.sim.model.xml = f'<mujoco><asset><mesh file="{asset.as_posix()}"/></asset></mujoco>'
    result = recorder.static()
    assert result["read_only"]["unchanged"] is True
    assert result["runtime"]["native_executed"] is False
    assert result["groups"]["hand"] == [2, 3, 4]
    assert result["group_body_ids"]["hand"] == [3, 4, 5]
    assert result["geom_names"][5] is None
    assert result["model_arrays"]["geom_contype"] == [1] * 6
    assert result["pair_filters"]["exclude_signature"] == [(2 << 16) + 3]
    assert result["assets"][0]["sha256"] == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert result["compiled_model_xml_sha256"] == hashlib.sha256(env.env.sim.model.xml.encode()).hexdigest()
    assert len(result["source_files_sha256"]) == 7
    decoded = module.read_typed_npz(recorder.out / result["artifact"]["path"], expected_sha256=result["artifact"]["sha256"])
    assert decoded["meshes"]["0"]["vertices"].dtype == np.float32
    np.testing.assert_array_equal(decoded["meshes"]["0"]["vertices"], env.env.sim.model.mesh_vert)
    assert decoded["model_arrays"]["geom_quat"].shape == (6, 4)
    assert not backend.called


def test_snapshot_retains_typed_native_signed_zero_truth_and_min_pairs(setup):
    recorder, env, backend = setup
    recorder.static()
    truth = {"goals": [True, True], "released": None, "objects": {"tomato_sauce_1": {"released": None}}}
    before = recorder._snapshot()
    record = recorder.capture(0, action_kind="initial", query_index=0, truth=truth)
    assert record["read_only"]["before_sha256"] == record["read_only"]["after_sha256"]
    decoded = module.read_typed_npz(recorder.out / record["artifact"]["path"])
    assert decoded["native"]["integration"].dtype == np.float64
    assert decoded["native"]["integration"].tobytes() == before["integration"].tobytes()
    assert np.signbit(decoded["native"]["integration"][2])
    assert decoded["original_evaluator_truth"] == truth
    assert record["geometry"]["new_release_labels"] is False
    for target in module.TARGETS:
        values = record["geometry"]["targets"][target]
        assert values["minimum_hand_pair"]["hand_name"] in env.finish_contract.gripper.contact_geoms
        assert values["hand_sphere_clearance_m"] == np.min(values["sphere_pair_clearance_m"])
        assert values["pinch_capsule_clearance_m"] == np.min(values["pinch_clearances_m"])
    assert record["contacts"][0]["geom_names"] == ["sauce_collision", "right_pad"]
    assert "force" not in record["contacts"][0]
    assert not backend.called
    assert module._fingerprint(before) == module._fingerprint(recorder._snapshot())


def test_geometry_matches_existing_conservative_formula_bit_for_bit(setup):
    recorder, env, _ = setup
    recorder.static()
    geometry = recorder.capture(0, action_kind="initial")["geometry"]
    from benchmark.remaining_goals.finish.environment import _release
    inner = SimpleNamespace(_check_grasp=lambda *args: False, check_contact=lambda *args: False)
    for name in module.TARGETS:
        _, legacy = _release(env.env, inner, env.finish_contract.gripper, env.finish_contract.objects[name])
        for field in ("hand_sphere_clearance_m", "pinch_capsule_clearance_m"):
            assert np.float64(legacy[field]).tobytes() == np.float64(geometry["targets"][name][field]).tobytes()


def test_action_dtype_and_bits_untouched_and_no_fake_final_query(setup):
    recorder, _, _ = setup
    recorder.static()
    recorder.capture(0, action_kind="initial", query_index=0)
    action = np.array([0., -0., 1., -.5, .2, -.2, -1.], dtype=np.float64)
    saved = action.tobytes()
    result = recorder.capture(1, action_kind="policy", query_index=None, action=action)
    decoded = module.read_typed_npz(recorder.out / result["artifact"]["path"])
    assert decoded["action"].tobytes() == saved == action.tobytes()
    assert decoded["query_index"] is None
    with pytest.raises(module.TechnicalError, match="float64"):
        recorder.capture(2, action_kind="policy", action=action.astype(np.float32))
    with pytest.raises(module.TechnicalError, match="sequential"):
        recorder.capture(293, action_kind="policy", action=action)


@pytest.mark.parametrize("mutation", ["integration", "ctrl", "controller", "gripper", "python", "numpy", "object_rng"])
def test_capture_mutation_is_technical_error_including_writer_side_effect(setup, monkeypatch, mutation):
    recorder, env, _ = setup
    recorder.static()
    py_state, np_state = random.getstate(), np.random.get_state()
    original = module.write_typed_npz
    def write(path, payload):
        result = original(path, payload)
        if mutation == "integration":
            env.env.sim.data.qacc_warmstart[0] += 1
        elif mutation == "ctrl":
            env.env.sim.data.ctrl[0] += 1
        elif mutation == "controller":
            env.finish_contract.hold.controller.goal_pos[0] += 1
        elif mutation == "gripper":
            env.finish_contract.gripper.current_action[0] += .1
        elif mutation == "python":
            random.random()
        elif mutation == "numpy":
            np.random.rand()
        else:
            env.finish_contract.hold.controller.rng.random()
        return result
    monkeypatch.setattr(module, "write_typed_npz", write)
    try:
        with pytest.raises(module.TechnicalError, match="mutated"):
            recorder.capture(0, action_kind="initial")
        assert (recorder.out / "native/0000.npz").is_file()  # explicit partial, never a passed snapshot
        assert recorder._last_step == -1
    finally:
        random.setstate(py_state)
        np.random.set_state(np_state)


def test_static_mutation_is_detected_and_recorder_does_not_own_environment_close(setup):
    recorder, env, _ = setup
    original = env.env.sim.model.get_xml
    def mutating_xml():
        env.finish_contract.gripper.current_action[0] += .1
        return original()
    env.env.sim.model.get_xml = mutating_xml
    with pytest.raises(module.TechnicalError, match="mutated"):
        recorder.static()
    assert not (recorder.out / "static.json").exists()
    recorder.close()
    assert recorder.closed


@pytest.mark.parametrize("field,value", [
    ("geom_rbound", np.array([0., .1, .1, .1, .1, .1])),
    ("geom_size", np.zeros((6, 2))),
    ("geom_type", np.array([99, 6, 7, 6, 6, 2])),
    ("geom_bodyid", np.array([7, 2, 3, 4, 5, 3])),
    ("geom_dataid", np.array([-1, -1, 7, -1, -1, -1])),
    ("geom_margin", np.array([np.nan] * 6)),
    ("geom_contype", np.ones(6, dtype=float)),
    ("body_parentid", np.array([-1, 0, 0, 0, 3, 3])),
    ("mesh_face", np.array([[0, 1, 7]] * 4)),
    ("mesh_vert", np.zeros((3, 3), dtype=np.float32)),
    ("pair_geom1", np.array([8])),
])
def test_bad_static_geometry_is_technical_error(setup, field, value):
    recorder, env, _ = setup
    setattr(env.env.sim.model, field, value)
    with pytest.raises(module.TechnicalError):
        recorder.static()
    assert not (recorder.out / "static.json").exists()


@pytest.mark.parametrize("change", ["absent_name", "duplicate", "pad_not_hand", "duplicate_pad", "bad_asset"])
def test_invalid_groups_and_assets_fail_closed(setup, change):
    recorder, env, _ = setup
    if change == "absent_name":
        env.finish_contract.gripper.contact_geoms[0] = "not-in-model"
    elif change == "duplicate":
        env.finish_contract.gripper.contact_geoms.append("left_pad")
    elif change == "pad_not_hand":
        env.finish_contract.gripper.important_geoms["left_fingerpad"] = ["soup_collision"]
    elif change == "duplicate_pad":
        env.finish_contract.gripper.important_geoms["right_fingerpad"] = ["left_pad"]
    else:
        env.env.sim.model.xml = '<mujoco><asset><mesh file="missing.stl"/></asset></mujoco>'
    with pytest.raises((module.TechnicalError, ValueError)):
        recorder.static()


@pytest.mark.parametrize("field,value", [("dist", float("nan")), ("frame", np.zeros((3, 3))),
                                        ("geom1", 99), ("dim", 2), ("exclude", 9),
                                        ("efc_address", 7), ("friction", np.zeros(4))])
def test_bad_contact_is_technical_error(setup, field, value):
    recorder, env, _ = setup
    recorder.static()
    setattr(env.env.sim.data.contact[0], field, value)
    with pytest.raises(module.TechnicalError):
        recorder.capture(0, action_kind="initial")
    assert not (recorder.out / "native/0000.npz").exists()


@pytest.mark.parametrize("change", ["positions", "rotations", "ctrl", "integration", "goal", "degenerate_pad", "ncon"])
def test_bad_dynamic_state_fails_before_output(setup, change):
    recorder, env, backend = setup
    recorder.static()
    data = env.env.sim.data
    if change == "positions":
        data.geom_xpos[1, 1] = np.inf
    elif change == "rotations":
        data.geom_xmat = np.zeros((6, 3, 3))
    elif change == "ctrl":
        data.ctrl = np.zeros(3)
    elif change == "integration":
        backend.mj_getState = lambda *args: None  # untouched NaN sentinel must fail
    elif change == "goal":
        env.finish_contract.hold.controller.goal_ori = np.zeros(4)
    elif change == "degenerate_pad":
        data.geom_xpos[3] = data.geom_xpos[4]
    else:
        data.ncon = 2
    with pytest.raises(module.TechnicalError):
        recorder.capture(0, action_kind="initial")
    assert not (recorder.out / "native/0000.npz").exists()


def test_unknown_truth_never_hides_nonfinite_measurement(setup):
    recorder, env, _ = setup
    recorder.static()
    env.env.sim.data.geom_xpos[0, 0] = np.nan
    with pytest.raises(module.TechnicalError, match="geom_xpos"):
        recorder.capture(0, action_kind="initial", truth={"released": None})


def test_monitor_counts_initialization_vs_control_native_substeps_and_restores_hooks():
    env, backend = make_fake()
    originals = {key: getattr(backend, key) for key in module.NATIVE_FUNCTIONS}
    model, data = env.env.sim.model, env.env.sim.data
    with module.NativeCallMonitor(backend=backend) as monitor:
        backend.mj_step1(model, data)  # legal original reset call
        backend.mj_forward(model, data)
        monitor.set_phase("action")
        for _ in range(25):
            backend.mj_step(model, data)
        monitor.set_phase("evaluation")
        backend.mj_forward(model, data)
        monitor.set_phase("recorder")
        backend.mj_getState(model, data, np.empty(12), 4095)
        with pytest.raises(module.TechnicalError, match="forbidden"):
            backend.mj_step(model, data)
        with pytest.raises(module.TechnicalError, match="forbidden"):
            backend.mj_setState(model, data, np.zeros(12), 4095)
    result = monitor.summary()
    assert result["phases"]["initialization"]["mj_step1"]["calls"] == 1
    assert result["phases"]["action"]["mj_step"]["calls"] == 25
    assert result["phases"]["action"]["mj_step"]["native_time_delta_sum"] == pytest.approx(.05)
    assert result["phases"]["recorder"]["mj_step"]["failures"] == 1
    assert backend.called.count("mj_step") == 25
    assert "mj_setState" not in backend.called
    assert not result["hooks_active"]
    for key, original in originals.items():
        assert getattr(backend, key) == original


def test_monitor_restores_every_hook_on_exception_and_rejects_nested():
    _, backend = make_fake()
    original = backend.mj_step
    with pytest.raises(RuntimeError, match="injected"):
        with module.NativeCallMonitor(backend=backend) as outer:
            with pytest.raises(module.TechnicalError, match="nest"):
                with module.NativeCallMonitor(backend=backend):
                    pytest.fail("nested monitor entered")
            assert getattr(backend.mj_step, "_release_audit_hook")
            raise RuntimeError("injected")
    assert backend.mj_step == original
    assert not outer.summary()["hooks_active"]


def test_recorder_with_monitor_performs_state_reads_only(setup):
    recorder, _, backend = setup
    with module.NativeCallMonitor(backend=backend) as monitor:
        monitor.set_phase("recorder")
        recorder.static()
        recorder.capture(0, action_kind="initial")
    assert monitor.summary()["counts"]["mj_getState"] == 4
    assert monitor.summary()["counts"]["mj_stateSize"] == 4
    assert sum(value for key, value in monitor.summary()["counts"].items() if key not in module.READ_FUNCTIONS) == 0


def test_existing_outputs_sequential_capture_and_replaced_contract_are_rejected(setup):
    recorder, env, _ = setup
    recorder.static()
    with pytest.raises(module.TechnicalError, match="once"):
        recorder.static()
    recorder.capture(0, action_kind="initial")
    with pytest.raises(module.TechnicalError, match="sequential"):
        recorder.capture(0, action_kind="initial")
    env.finish_contract = deepcopy(env.finish_contract)
    with pytest.raises(module.TechnicalError, match="changed"):
        recorder.capture(1, action_kind="policy", action=np.zeros(7))
    original = recorder.out / "static.npz"
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        module.write_typed_npz(original, {"forged": np.zeros(3)})
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest


def test_typed_roundtrip_rng_continuation_and_invalid_hash(tmp_path):
    path = tmp_path / "state.npz"
    rng = np.random.RandomState(17)
    python = random.Random(19)
    payload = {"rng": rng.get_state(), "python": python.getstate(), "signed": np.array([-0., 0.]),
               "single": np.array([1, 2], dtype=np.int32), "unknown": None}
    reference = module.write_typed_npz(path, payload)
    result = module.read_typed_npz(path, expected_sha256=reference["sha256"])
    resumed, py_resumed = np.random.RandomState(), random.Random()
    resumed.set_state(result["rng"])
    py_resumed.setstate(result["python"])
    np.testing.assert_array_equal(rng.rand(8), resumed.rand(8))
    assert [python.random() for _ in range(8)] == [py_resumed.random() for _ in range(8)]
    assert payload["signed"].tobytes() == result["signed"].tobytes()
    assert result["single"].dtype == np.int32
    with pytest.raises(module.TechnicalError, match="file hash"):
        module.read_typed_npz(path, expected_sha256="0" * 64)


@pytest.mark.parametrize("value", [np.array([np.inf]), np.array([object()]), {"value": float("nan")}])
def test_typed_writer_rejects_nonfinite_or_pickle_values(tmp_path, value):
    with pytest.raises(module.TechnicalError):
        module.write_typed_npz(tmp_path / "invalid.npz", value)
    assert not (tmp_path / "invalid.npz").exists()


@pytest.mark.parametrize("tag,directory", [("mesh", "meshdir"), ("hfield", "meshdir"), ("texture", "texturedir")])
def test_relative_asset_uses_only_absolute_declared_compiler_base(tmp_path, tag, directory):
    base = tmp_path / "assets"
    base.mkdir()
    (base / "sub").mkdir()
    asset = base / "same.bin"
    asset.write_bytes(b"synthetic source")
    xml = f'<mujoco><compiler {directory}="{base.as_posix()}"/><asset><{tag} file="sub/../same.bin"/></asset></mujoco>'
    rows = module._xml_assets(xml)
    assert rows[0]["path"] == str(asset.resolve())
    assert rows[0]["original"] == "sub/../same.bin"
    assert rows[0]["resolution_rule"] == "absolute_compiler_" + directory
    assert rows[0]["sha256"] == hashlib.sha256(asset.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", ["no_base", "relative_base", "escape", "wrong_kind", "missing"])
def test_relative_assets_cannot_fall_back_to_cwd_or_escape(tmp_path, monkeypatch, change):
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "same.bin").write_bytes(b"cwd bait")
    monkeypatch.chdir(tmp_path)
    compiler = f'<compiler meshdir="{base.as_posix()}"/>'
    file, tag = "same.bin", "mesh"
    if change == "no_base":
        compiler = ""
    elif change == "relative_base":
        compiler = '<compiler meshdir="base"/>'
    elif change == "escape":
        file = "../same.bin"
    elif change == "wrong_kind":
        tag = "texture"
    with pytest.raises(module.TechnicalError):
        module._xml_assets(f'<mujoco>{compiler}<asset><{tag} file="{file}"/></asset></mujoco>')


def test_declared_base_symlink_escape_is_rejected_without_symlink_privilege(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path == base / "link.bin":
            return outside
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(module.TechnicalError, match="escapes"):
        module._xml_assets(f'<mujoco><compiler meshdir="{base.as_posix()}"/><asset><mesh file="link.bin"/></asset></mujoco>')


def test_nonrotational_native_matrix_is_not_physical_unknown(setup):
    recorder, env, _ = setup
    recorder.static()
    env.env.sim.data.geom_xmat[1] = np.zeros(9)
    with pytest.raises(module.TechnicalError, match="rotation matrix"):
        recorder.capture(0, action_kind="initial", truth={"released": None})
