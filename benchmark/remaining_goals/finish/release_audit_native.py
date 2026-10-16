"""Read-only native evidence for the separately authorized release diagnostic.

Importing this module does not import MuJoCo or robosuite. No simulator is
constructed here. Snapshots describe the new replay, not a resumable checkpoint
of the historical run. Collision forces and new distance predicates are absent.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import functools
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path, PureWindowsPath
import random
import time
import xml.etree.ElementTree as ET

import numpy as np

SCHEMA = "remaining-release-native-sidecar-v1"
TYPED_FORMAT = "remaining-release-typed-npz-v1"
TARGETS = ("alphabet_soup_1", "tomato_sauce_1")
PHASES = frozenset({"initialization", "action", "evaluation", "recorder", "cleanup"})
NATIVE_FUNCTIONS = ("mj_step", "mj_step1", "mj_step2", "mj_forward", "mj_resetData",
                    "mj_resetDataKeyframe", "mj_setState", "mj_collision", "mj_getState", "mj_stateSize")
READ_FUNCTIONS = frozenset({"mj_getState", "mj_stateSize"})


class TechnicalError(RuntimeError):
    """Invalid diagnostic evidence, never a physical unknown/release label."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _array(value, shape=None, name="array", *, integer=False):
    result = np.asarray(value)
    if (result.dtype.fields is not None or result.dtype.kind not in ("iu" if integer else "biuf")
            or (shape is not None and result.shape != tuple(shape)) or not np.isfinite(result).all()):
        raise TechnicalError(f"invalid/nonfinite {name}: shape={result.shape}, dtype={result.dtype}")
    return result.copy(order="C")


def _int(value, name, minimum=0):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise TechnicalError(f"invalid {name}")
    return int(value)


def _number(value, name):
    result = _array(value, (), name)
    if result.dtype.kind == "b":
        raise TechnicalError(f"invalid boolean {name}")
    return float(result)


def _technical(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, ET.ParseError) as error:
            raise TechnicalError(f"invalid native diagnostic evidence: {error}") from error
    return wrapped


def _encode(value, arrays):
    if isinstance(value, np.ndarray) or isinstance(value, np.generic) or isinstance(value, float):
        array = _array(value)
        key = f"array_{len(arrays):05d}"
        arrays[key] = array
        return {"array": key, "dtype": array.dtype.str, "shape": list(array.shape),
                "sha256": _sha(array.tobytes(order="C"))}
    if value is None or isinstance(value, (str, bool, int)):
        return {"scalar": value}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TechnicalError("diagnostic dictionary keys must be strings")
        return {"dict": [[key, _encode(value[key], arrays)] for key in sorted(value)]}
    if isinstance(value, (tuple, list)):
        return {"tuple" if isinstance(value, tuple) else "list": [_encode(v, arrays) for v in value]}
    raise TechnicalError(f"unsupported diagnostic value: {type(value).__name__}")


def _fingerprint(value):
    return _sha(_canonical(_encode(value, {})))


def _json(value):
    if isinstance(value, (np.ndarray, np.generic)):
        return _array(value).tolist()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    _encode(value, {})  # Reject unsupported/nonfinite scalars, too.
    return value


def write_typed_npz(path, payload):
    """Exclusive no-pickle output; preserve array dtype, shape and raw bits."""
    path = Path(path)
    arrays = {}
    tree = _encode(payload, arrays)
    metadata = {"format": TYPED_FORMAT, "tree": tree, "content_sha256": _sha(_canonical(tree))}
    arrays["metadata_json"] = np.frombuffer(_canonical(metadata), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    return {"format": TYPED_FORMAT, "sha256": _sha(path.read_bytes()),
            "content_sha256": metadata["content_sha256"], "size": path.stat().st_size}


def read_typed_npz(path, *, expected_sha256=None):
    """CPU validation helper for locally produced diagnostic artifacts."""
    import io
    raw = Path(path).read_bytes()
    if expected_sha256 is not None and _sha(raw) != expected_sha256:
        raise TechnicalError("typed artifact file hash mismatch")
    try:
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            encoded = archive["metadata_json"]
            if encoded.dtype != np.uint8 or encoded.ndim != 1:
                raise TechnicalError("invalid typed artifact metadata")
            metadata = json.loads(encoded.tobytes().decode("utf-8"))
            if (metadata.get("format") != TYPED_FORMAT or
                    metadata.get("content_sha256") != _sha(_canonical(metadata["tree"]))):
                raise TechnicalError("typed artifact metadata hash mismatch")
            used = {"metadata_json"}

            def decode(node):
                if "array" in node:
                    key = node["array"]
                    if key in used:
                        raise TechnicalError("reused typed artifact array")
                    used.add(key)
                    array = _array(archive[key])
                    if (array.dtype.str != node["dtype"] or list(array.shape) != node["shape"]
                            or _sha(array.tobytes()) != node["sha256"]):
                        raise TechnicalError("typed artifact array metadata mismatch")
                    return array
                if set(node) == {"scalar"}:
                    _encode(node["scalar"], {})
                    return node["scalar"]
                if set(node) == {"dict"}:
                    result = {}
                    for key, item in node["dict"]:
                        if not isinstance(key, str) or key in result:
                            raise TechnicalError("invalid typed artifact dictionary")
                        result[key] = decode(item)
                    return result
                if set(node) in ({"list"}, {"tuple"}):
                    key = next(iter(node))
                    values = [decode(item) for item in node[key]]
                    return tuple(values) if key == "tuple" else values
                raise TechnicalError("invalid typed artifact tree")

            result = decode(metadata["tree"])
            if used != set(archive.files):
                raise TechnicalError("unused typed artifact arrays")
            return result
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise TechnicalError(f"invalid typed artifact: {error}") from error


def _load_backend():
    if importlib.metadata.version("mujoco") != "2.3.7" or importlib.metadata.version("robosuite") != "1.4.0":
        raise TechnicalError("release diagnostic requires mujoco==2.3.7 and robosuite==1.4.0")
    backend = importlib.import_module("mujoco")
    if backend.mj_versionString() != "2.3.7":
        raise TechnicalError("loaded MuJoCo native library differs from fixed 2.3.7")
    for name in NATIVE_FUNCTIONS:
        if not callable(getattr(backend, name, None)):
            raise TechnicalError(f"fixed native API missing: {name}")
    return backend


def _runtime_metadata(backend):
    packages = {name: importlib.metadata.version(name) for name in ("mujoco", "robosuite", "numpy")}
    if packages["mujoco"] != "2.3.7" or packages["robosuite"] != "1.4.0":
        raise TechnicalError("runtime distribution differs from fixed diagnostic backend")
    root = Path(backend.__file__).resolve().parent
    files = {root / "__init__.py"}
    for pattern in ("*.pyd", "*.dll", "*.so", "*.so.*", "*.dylib"):
        files.update(root.glob(pattern))
    records = [{"path": str(path), "sha256": _sha(path.read_bytes()), "size": path.stat().st_size}
               for path in sorted(files)]
    dependency_sources = {}
    distribution = importlib.metadata.distribution("robosuite")
    for relative in ("utils/binding_utils.py", "environments/base.py", "environments/manipulation/manipulation_env.py",
                     "controllers/osc.py", "controllers/base_controller.py", "controllers/interpolators/linear_interpolator.py",
                     "models/grippers/panda_gripper.py"):
        path = Path(distribution.locate_file("robosuite/" + relative))
        dependency_sources["robosuite/" + relative] = {"path": str(path), "sha256": _sha(path.read_bytes())}
    return {"packages": packages, "native_version": backend.mj_versionString(), "native_files": records,
            "dependency_sources": dependency_sources,
            "native_api_execution": "recorded_by_this_user_run", "mujoco_py_backend": False}


def _xml_assets(xml):
    """Hash only resolved compiler-declared sources; never guess a cwd base.

    MuJoCo 2.3.7 user_objects.cc uses meshdir also for height fields. A relative
    filename needs a declared absolute meshdir/texturedir; absolute filenames
    take precedence. Inner '..' is accepted only if resolution stays in base.
    """
    tree = ET.fromstring(xml)
    compiler = tree.find("compiler")
    attributes = {} if compiler is None else dict(compiler.attrib)
    if attributes.get("strippath", "false").lower() not in ("false", "0"):
        raise TechnicalError("compiled XML strippath source mapping is unsupported")
    records = []
    for node in tree.iter():
        for key, value in node.attrib.items():
            if not key.startswith("file"):
                continue
            allowed = {"file"} if node.tag in ("mesh", "hfield") else {
                "file", "fileleft", "fileright", "fileup", "filedown", "filefront", "fileback"} if node.tag == "texture" else set()
            if key not in allowed or not value:
                raise TechnicalError(f"unsupported compiled XML file reference: {node.tag}.{key}")
            raw = Path(value)
            base = None
            if raw.is_absolute():
                path, rule = raw.resolve(), "absolute_file"
            else:
                if PureWindowsPath(value).drive or PureWindowsPath(value).root:
                    raise TechnicalError("compiled XML source has incompatible platform path")
                directory = "texturedir" if node.tag == "texture" else "meshdir"
                raw_base = attributes.get(directory)
                if not raw_base or not Path(raw_base).is_absolute():
                    raise TechnicalError(f"relative {node.tag} file needs an absolute compiler.{directory}")
                base = Path(raw_base).resolve()
                path = (base / raw).resolve()
                if not path.is_relative_to(base):
                    raise TechnicalError("compiled XML asset escapes declared compiler directory")
                rule = "absolute_compiler_" + directory
            if not path.is_file():
                raise TechnicalError(f"compiled XML asset file missing: {path}")
            records.append({"tag": node.tag, "attribute": key, "original": value, "path": str(path),
                            "compiler_base": None if base is None else str(base), "resolution_rule": rule,
                            "sha256": _sha(path.read_bytes()), "size": path.stat().st_size})
    return records


class NativeCallMonitor:
    """Count Python native entry calls, not unobservable internal C subcalls.

    Original initialization/evaluation calls remain permitted. Recorder phase
    allows only state-size/state-copy reads. Wrappers are always restored.
    """
    def __init__(self, *, backend=None):
        self.backend = backend
        self.phase = "initialization"
        self._originals = {}
        self._stats = {}

    def set_phase(self, phase):
        if phase not in PHASES:
            raise TechnicalError(f"unknown native monitor phase: {phase}")
        self.phase = phase

    def __enter__(self):
        if self._originals:
            raise TechnicalError("native monitor is already entered")
        self.backend = self.backend if self.backend is not None else _load_backend()
        try:
            for name in NATIVE_FUNCTIONS:
                function = getattr(self.backend, name)
                if getattr(function, "_release_audit_hook", False):
                    raise TechnicalError("native monitor cannot nest")
                self._originals[name] = function
                setattr(self.backend, name, self._wrapper(name, function))
        except BaseException:
            self.close()
            raise
        return self

    def _wrapper(self, name, function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            phase = self.phase
            row = self._stats.setdefault(phase, {}).setdefault(name, {
                "calls": 0, "failures": 0, "wall_seconds": 0., "native_time_before": None,
                "native_time_after": None, "native_time_delta_sum": 0.})
            row["calls"] += 1
            data = args[1] if len(args) > 1 and hasattr(args[1], "time") else kwargs.get("d")
            before = _number(data.time, "native time") if data is not None else None
            if row["native_time_before"] is None:
                row["native_time_before"] = before
            started = time.perf_counter()
            try:
                if phase == "recorder" and name not in READ_FUNCTIONS:
                    raise TechnicalError(f"forbidden diagnostic native call: {name}")
                return function(*args, **kwargs)
            except BaseException:
                row["failures"] += 1
                raise
            finally:
                row["wall_seconds"] += time.perf_counter() - started
                after = _number(data.time, "native time") if data is not None else None
                row["native_time_after"] = after
                if before is not None and after is not None:
                    row["native_time_delta_sum"] += after - before
        wrapped._release_audit_hook = True
        return wrapped

    def summary(self):
        return {"count_scope": "Python calls to fixed MuJoCo entry points; internal C calls are not separately counted",
                "phases": deepcopy(self._stats),
                "counts": {name: sum(phase.get(name, {}).get("calls", 0) for phase in self._stats.values())
                           for name in NATIVE_FUNCTIONS}, "hooks_active": bool(self._originals)}

    def close(self):
        for name, function in self._originals.items():
            setattr(self.backend, name, function)
        self._originals.clear()

    def __exit__(self, *exc):
        self.close()


class Recorder:
    """Attach to one successfully reset FinishLiberoEnv; never own its close."""
    def __init__(self, env, out, *, backend=None):
        self.owner = env
        self.native = env.env
        self.contract = env.finish_contract
        if self.contract is None or self.contract.env is not self.native:
            raise TechnicalError("recorder requires the successful current FINISH reset")
        self.sim = self.native.sim
        self.model, self.data = self.sim.model, self.sim.data
        self.backend = backend if backend is not None else _load_backend()
        self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.closed = False
        self._static = None
        self._last_step = -1
        self.mask = int(self.backend.mjtState.mjSTATE_INTEGRATION)
        if self.mask != 4095:
            raise TechnicalError("unexpected MuJoCo 2.3.7 integration-state mask")

    def _state(self):
        size = _int(self.backend.mj_stateSize(self.model._model, self.mask), "integration size", 1)
        result = np.empty(size, dtype=np.float64)
        result.fill(np.nan)
        try:
            self.backend.mj_getState(self.model._model, self.data._data, result, self.mask)
        except (TypeError, ValueError) as error:
            raise TechnicalError(f"native integration state read failed: {error}") from error
        return _array(result, (size,), "integration state")

    def _external(self):
        controller = self.contract.hold.controller
        gripper = self.contract.gripper
        fields = {"goal_pos": _array(controller.goal_pos, (3,), "OSC goal_pos"),
                  "goal_ori": _array(controller.goal_ori, (3, 3), "OSC goal_ori")}
        for name in ("relative_ori", "ori_ref", "new_update", "ee_pos", "ee_ori_mat", "ee_pos_vel",
                     "ee_ori_vel", "joint_pos", "joint_vel", "torques", "kp", "kd", "control_freq"):
            if hasattr(controller, name):
                fields[name] = deepcopy(getattr(controller, name))
        for name in ("interpolator_pos", "interpolator_ori"):
            interpolator = getattr(controller, name, None)
            if interpolator is None:
                fields[name] = None
            else:
                fields[name] = {key: deepcopy(getattr(interpolator, key))
                                for key in ("start", "goal", "step", "total_steps", "dim", "order")}
        current = _array(gripper.current_action, (2,), "gripper current_action")
        if np.any(np.abs(current) > 1):
            raise TechnicalError("gripper current_action outside [-1,1]")
        rng = {"python_global": random.getstate(), "numpy_global": np.random.get_state(), "objects": {}}
        for label, obj in (("owner", self.owner), ("native", self.native), ("inner", self.contract.inner),
                           ("controller", controller), ("gripper", gripper)):
            # Inspect existing attributes, never call a property that creates an RNG.
            for name, value in vars(obj).items():
                if isinstance(value, np.random.Generator):
                    rng["objects"][label + "." + name] = deepcopy(value.bit_generator.state)
                elif isinstance(value, np.random.RandomState):
                    rng["objects"][label + "." + name] = value.get_state()
                elif isinstance(value, random.Random):
                    rng["objects"][label + "." + name] = value.getstate()
        clocks = {label: {key: deepcopy(getattr(obj, key)) for key in
                         ("cur_time", "timestep", "model_timestep", "control_timestep", "done") if hasattr(obj, key)}
                  for label, obj in (("owner", self.owner), ("native", self.native), ("inner", self.contract.inner))}
        return {"controller": fields, "gripper_current_action": current, "rng": rng, "clocks": clocks}

    def _snapshot(self):
        if self.closed or self.owner.finish_contract is not self.contract or self.native.sim is not self.sim:
            raise TechnicalError("recorder closed or native contract/model changed")
        return {"integration": self._state(), "ctrl": _array(self.data.ctrl, (int(self.model.nu),), "ctrl"),
                "time": _number(self.data.time, "native time"), "external": self._external()}

    @contextmanager
    def _guard(self):
        before = self._snapshot()
        proof = {"before_sha256": _fingerprint(before)}
        try:
            yield before, proof
        finally:
            after = self._snapshot()
            proof.update(after_sha256=_fingerprint(after))
            proof["unchanged"] = proof["before_sha256"] == proof["after_sha256"]
            if not proof["unchanged"]:
                raise TechnicalError("diagnostic recorder mutated integration/controller/gripper/RNG state")

    def _names(self, kind, count):
        function = getattr(self.model, kind + "_id2name")
        names = [function(index) for index in range(count)]
        if any(name is not None and (not isinstance(name, str) or not name) for name in names):
            raise TechnicalError(f"invalid {kind} name table")
        present = [name for name in names if name is not None]
        if len(present) != len(set(present)):
            raise TechnicalError(f"duplicate {kind} names")
        return names

    def _ids(self, names):
        if not isinstance(names, (list, tuple)) or not names or len(set(names)) != len(names):
            raise TechnicalError("missing/duplicate contact geometry group")
        result = []
        for name in names:
            if not isinstance(name, str) or not name:
                raise TechnicalError("invalid contact geometry name")
            index = _int(self.model.geom_name2id(name), "geom ID")
            if index >= int(self.model.ngeom) or self.model.geom_id2name(index) != name:
                raise TechnicalError("contact geometry name/ID mismatch")
            result.append(index)
        return result

    def _static_payload(self):
        # Read native fields directly; robosuite's compatibility wrapper is not
        # itself an API guarantee for every mjModel field (e.g. exclusions).
        model = self.model._model
        dims = {name: _int(getattr(model, name), name) for name in
                ("nq", "nv", "na", "nu", "nbody", "ngeom", "nsite", "njnt", "nmesh", "nmeshgraph", "npair", "nexclude")}
        n = dims["ngeom"]
        names = self._names("geom", n)
        bodies = self._names("body", dims["nbody"])
        groups = {name: self._ids(list(self.contract.objects[name].contact_geoms)) for name in TARGETS}
        groups["hand"] = self._ids(list(self.contract.gripper.contact_geoms))
        for key in ("left_fingerpad", "right_fingerpad"):
            groups[key] = self._ids(self.contract.gripper.important_geoms[key])
            if not set(groups[key]).issubset(groups["hand"]):
                raise TechnicalError("fingerpad geometries must belong to hand contact geometry")
        if set(groups["left_fingerpad"]) & set(groups["right_fingerpad"]):
            raise TechnicalError("left/right fingerpad geometry groups overlap")
        relevant = sorted(set(index for group in groups.values() for index in group))
        arrays = {}
        integers = ("geom_type", "geom_bodyid", "geom_dataid", "geom_contype", "geom_conaffinity",
                    "geom_condim", "geom_group", "geom_priority")
        for key in integers:
            arrays[key] = _array(getattr(model, key), (n,), key, integer=True)
        for key, width in (("geom_size", 3), ("geom_pos", 3), ("geom_quat", 4), ("geom_friction", 3),
                           ("geom_solref", 2), ("geom_solimp", 5)):
            arrays[key] = _array(getattr(model, key), (n, width), key)
        for key in ("geom_rbound", "geom_margin", "geom_gap", "geom_solmix"):
            arrays[key] = _array(getattr(model, key), (n,), key)
        for key in ("body_parentid", "body_weldid"):
            arrays[key] = _array(getattr(model, key), (dims["nbody"],), key, integer=True)
            if np.any((arrays[key] < 0) | (arrays[key] >= dims["nbody"])):
                raise TechnicalError(f"invalid {key} references")
        if np.any((arrays["geom_bodyid"] < 0) | (arrays["geom_bodyid"] >= dims["nbody"])):
            raise TechnicalError("invalid geometry body references")
        for index in relevant:
            if int(arrays["geom_type"][index]) not in (2, 3, 4, 5, 6, 7):
                raise TechnicalError("unsupported target/hand collision geometry type")
            if arrays["geom_rbound"][index] <= 0 or np.any(arrays["geom_size"][index] < 0):
                raise TechnicalError("invalid relevant geometry size/radius")
            if int(arrays["geom_condim"][index]) not in (1, 3, 4, 6):
                raise TechnicalError("invalid relevant geometry contact dimension")
            if abs(float(np.linalg.norm(arrays["geom_quat"][index])) - 1) > 1e-7:
                raise TechnicalError("invalid compiled geometry quaternion")
        pair_arrays = {}
        for key in ("pair_geom1", "pair_geom2", "pair_dim"):
            pair_arrays[key] = _array(getattr(model, key), (dims["npair"],), key, integer=True)
        for key in ("pair_geom1", "pair_geom2"):
            if np.any((pair_arrays[key] < 0) | (pair_arrays[key] >= n)):
                raise TechnicalError("invalid predefined pair geometry ID")
        for key in ("pair_margin", "pair_gap"):
            pair_arrays[key] = _array(getattr(model, key), (dims["npair"],), key)
        for key, width in (("pair_solref", 2), ("pair_solreffriction", 2), ("pair_solimp", 5), ("pair_friction", 5)):
            pair_arrays[key] = _array(getattr(model, key), (dims["npair"], width), key)
        pair_arrays["pair_signature"] = _array(model.pair_signature, (dims["npair"],), "pair_signature", integer=True)
        pair_arrays["exclude_signature"] = _array(model.exclude_signature, (dims["nexclude"],), "exclude_signature", integer=True)
        mesh_graph = _array(model.mesh_graph, (dims["nmeshgraph"],), "mesh_graph", integer=True)
        meshes = {}
        for index in relevant:
            if int(arrays["geom_type"][index]) != 7:
                continue
            mesh = int(arrays["geom_dataid"][index])
            if not 0 <= mesh < dims["nmesh"]:
                raise TechnicalError("invalid geometry mesh data ID")
            if str(mesh) in meshes:
                continue
            first = _int(model.mesh_vertadr[mesh], "mesh vertex address")
            count = _int(model.mesh_vertnum[mesh], "mesh vertex count", 1)
            face_first = _int(model.mesh_faceadr[mesh], "mesh face address")
            face_count = _int(model.mesh_facenum[mesh], "mesh face count", 1)
            vertices = _array(model.mesh_vert[first:first + count], (count, 3), "compiled mesh vertices")
            faces = _array(model.mesh_face[face_first:face_first + face_count], (face_count, 3), "mesh faces", integer=True)
            if np.any((faces < 0) | (faces >= count)):
                raise TechnicalError("invalid compiled mesh face indices")
            graph_address = _int(model.mesh_graphadr[mesh], "mesh graph address", -1)
            if graph_address >= dims["nmeshgraph"]:
                raise TechnicalError("invalid compiled mesh graph address")
            meshes[str(mesh)] = {"name": self.model.mesh_id2name(mesh), "vertices": vertices, "faces": faces,
                                "vertices_sha256": _sha(vertices.tobytes()), "vertices_shape": list(vertices.shape),
                                "faces_sha256": _sha(faces.tobytes()), "faces_shape": list(faces.shape),
                                "vertex_address": first, "face_address": face_first,
                                "graph_address": graph_address,
                                "collision_semantics": "convex hull of compiled vertices; faces are not a new distance predicate"}
        xml = self.model.get_xml()
        if not isinstance(xml, str) or not xml:
            raise TechnicalError("compiled model XML unavailable")
        assets = _xml_assets(xml)
        options = {key: deepcopy(getattr(model.opt, key)) for key in
                   ("timestep", "collision", "disableflags", "enableflags", "integrator", "solver", "cone")}
        repo = Path(__file__).resolve().parents[3]
        source_paths = ["benchmark/remaining_goals/finish/" + name for name in
                        ("release_audit.py", "release_audit_plan.py", "release_audit_native.py", "environment.py", "runner.py")]
        source_paths += ["benchmark/remaining_goals/" + name for name in ("libero_env.py", "libero_compat.py")]
        sources = {name: _sha((repo / name).read_bytes()) for name in source_paths}
        return {"schema_version": SCHEMA, "dimensions": dims, "geom_names": names, "body_names": bodies,
                "groups": groups,
                "group_body_ids": {key: sorted({int(arrays["geom_bodyid"][i]) for i in ids}) for key, ids in groups.items()},
                "relevant_geom_ids": relevant, "model_arrays": arrays, "pair_filters": pair_arrays,
                "meshes": meshes, "mesh_graph": mesh_graph, "model_options": options, "compiled_model_xml": xml,
                "mesh_transform_semantics": "MuJoCo 2.3.7 has no mjModel mesh_pos/mesh_quat; use compiled mesh_vert with geom_pos/quat and recorded geom_xpos/xmat",
                "compiled_model_xml_sha256": _sha(xml.encode("utf-8")), "assets": assets,
                "runtime": _runtime_metadata(self.backend), "source_files_sha256": sources,
                "integration_mask": self.mask, "limitation": "new replay diagnostics, not a historical or general resume checkpoint"}

    @_technical
    def static(self):
        if self._static is not None:
            raise TechnicalError("static native evidence may be written only once")
        with self._guard() as (_, proof):
            payload = self._static_payload()
            reference = write_typed_npz(self.out / "static.npz", payload)
        reference["path"] = "static.npz"
        result = _json(payload)
        result["read_only"] = proof
        result["artifact"] = reference
        with (self.out / "static.json").open("xb") as stream:
            stream.write(_canonical(result))
        self._static = payload
        return result

    def _contacts(self):
        data = self.data._data
        count = _int(data.ncon, "ncon")
        if count > len(data.contact):
            raise TechnicalError("contact count exceeds native contact storage")
        records = []
        nefc = _int(data.nefc, "nefc")
        n = self._static["dimensions"]["ngeom"]
        for index in range(count):
            contact = data.contact[index]
            ids = [_int(getattr(contact, key), key) for key in ("geom1", "geom2")]
            if any(value >= n for value in ids):
                raise TechnicalError("invalid contact geometry ID")
            dim = _int(contact.dim, "contact dim")
            excluded = _int(contact.exclude, "contact exclude")
            address = _int(contact.efc_address, "contact efc_address", -1)
            if dim not in (1, 3, 4, 6) or excluded not in (0, 1, 2, 3) or address >= nefc:
                raise TechnicalError("invalid contact constraint metadata")
            records.append({"index": index, "geom_ids": ids, "geom_names": [self.model.geom_id2name(i) for i in ids],
                            "dist": _number(contact.dist, "contact dist"), "pos": _array(contact.pos, (3,), "contact pos"),
                            "frame": _array(contact.frame, (9,), "contact frame"), "dim": dim, "exclude": excluded,
                            "efc_address": address, "includemargin": _number(contact.includemargin, "contact includemargin"),
                            "friction": _array(contact.friction, (5,), "contact friction")})
        return records

    def _geometry(self):
        static = self._static
        n = static["dimensions"]["ngeom"]
        positions = _array(self.data._data.geom_xpos, (n, 3), "geom_xpos")
        rotations = _array(self.data._data.geom_xmat, (n, 9), "geom_xmat")
        matrices = rotations.reshape(n, 3, 3)
        if (not np.allclose(matrices.transpose(0, 2, 1) @ matrices, np.eye(3), rtol=0, atol=1e-7)
                or np.any(np.abs(np.linalg.det(matrices) - 1) > 1e-7)):
            raise TechnicalError("invalid native geometry rotation matrix")
        radii = static["model_arrays"]["geom_rbound"]
        groups, names = static["groups"], static["geom_names"]
        hand = groups["hand"]
        left, right = groups["left_fingerpad"], groups["right_fingerpad"]
        a, b = positions[left].mean(axis=0), positions[right].mean(axis=0)
        axis = b - a
        length2 = float(axis @ axis)
        if length2 <= 1e-12:
            raise TechnicalError("degenerate fingerpad segment")
        pad_radius = max(float(np.max(np.linalg.norm(positions[left] - a, axis=1) + radii[left])),
                         float(np.max(np.linalg.norm(positions[right] - b, axis=1) + radii[right])))
        targets = {}
        for name in TARGETS:
            ids = groups[name]
            points = positions[ids]
            separation = np.linalg.norm(points[:, None] - positions[hand][None, :], axis=2) - radii[ids, None] - radii[hand][None, :]
            pair = np.unravel_index(int(np.argmin(separation)), separation.shape)
            fraction = np.clip((points - a) @ axis / length2, 0, 1)
            closest = a + fraction[:, None] * axis
            pinch = np.linalg.norm(points - closest, axis=1) - radii[ids] - pad_radius
            winner = int(np.argmin(pinch))
            targets[name] = {"target_geom_ids": ids, "hand_geom_ids": hand, "sphere_pair_clearance_m": separation,
                             "hand_sphere_clearance_m": float(np.min(separation)),
                             "minimum_hand_pair": {"target_id": ids[pair[0]], "hand_id": hand[pair[1]],
                                                   "target_name": names[ids[pair[0]]], "hand_name": names[hand[pair[1]]]},
                             "pinch_fractions": fraction, "pinch_closest_points": closest, "pinch_clearances_m": pinch,
                             "pinch_capsule_clearance_m": float(np.min(pinch)), "minimum_pinch_target_id": ids[winner],
                             "minimum_pinch_target_name": names[ids[winner]]}
        return {"geom_xpos": positions, "geom_xmat": rotations, "targets": targets,
                "pinch_segment": {"a": a, "b": b, "radius": pad_radius, "length_squared": length2},
                "measurement_only": True, "new_release_labels": False}

    @_technical
    def capture(self, step, *, action_kind, query_index=None, action=None, truth=None):
        step = _int(step, "snapshot step")
        if self._static is None or step != self._last_step + 1 or step > 292:
            raise TechnicalError("native capture requires static evidence and sequential steps 0..292")
        if action_kind != ("initial" if step == 0 else "policy"):
            raise TechnicalError("invalid diagnostic action phase")
        if query_index is not None:
            query_index = _int(query_index, "query index")
        if step == 0:
            if action is not None:
                raise TechnicalError("initial snapshot must have no action")
        else:
            action = _array(action, (7,), "original action")
            if action.dtype != np.dtype("float64"):
                raise TechnicalError("original action must retain float64 dtype")
        with self._guard() as (before, proof):
            payload = {"schema_version": SCHEMA, "step": step, "action_kind": action_kind,
                       "query_index": query_index, "action": action, "original_evaluator_truth": deepcopy(truth),
                       "integration_mask": self.mask, "native": before, "geometry": self._geometry(),
                       "contacts": self._contacts(), "contact_timing": "existing arrays at evaluator boundary; no forward/collision/force recomputation"}
            _fingerprint(payload)
            relative = f"native/{step:04d}.npz"
            reference = write_typed_npz(self.out / relative, payload)
        reference["path"] = relative
        self._last_step = step
        return {"schema_version": SCHEMA, "step": step, "action_kind": action_kind, "query_index": query_index,
                "native_time": before["time"], "read_only": proof, "artifact": reference,
                "geometry": _json(payload["geometry"]), "contacts": _json(payload["contacts"])}

    def close(self):
        self.closed = True


# Runner-facing name; Recorder is retained as the originally agreed API.
NativeRecorder = Recorder
