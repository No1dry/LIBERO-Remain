"""Lossless live FINISH evidence; no simulator calls or model preprocessing."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import zlib

import numpy as np

from ..observation_artifact import save_observation_artifact, load_observation_artifact
from ..pilot_evidence import _contained, observation_sha256
from ..runner import _observation
from .schema import (PROTOCOL, HASH, INPUT_SCHEMA, digest, input_sha256, json_bytes,
                     validate_finish_result, validate_input_evidence)

EVIDENCE_SCHEMA = "remaining-finish-evidence-v1"
INPUT_REFERENCE_SCHEMA = "remaining-finish-input-artifact-v1"
_REQUIRED_IDENTITY = {"run_id", "run_config_sha256", "manifest_hash", "episode_id", "state_sha256",
                      "protocol_version", "mode", "head_sha256"}
_BINDING = ("schema_version", "protocol_version", "episode_id", "instruction", "initial_mask", "mode",
            "configuration", "status", "error", "error_phase", "exit_reason", "finish_step", "timeout_step",
            "n_steps", "policy_queries", "hold_contract", "trace", "queries", "executed_actions")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(value):
    if not isinstance(value, dict) or not _REQUIRED_IDENTITY.issubset(value):
        raise ValueError("FINISH evidence requires a complete run/episode/head identity")
    if any(not isinstance(value[key], str) or not value[key] for key in _REQUIRED_IDENTITY):
        raise ValueError("FINISH identity fields must be nonempty strings")
    if value["protocol_version"] != PROTOCOL or value["mode"] not in {"active", "shadow"}:
        raise ValueError("FINISH evidence protocol/mode differs")
    for key, item in value.items():
        if key.endswith("_sha256") or key == "manifest_hash":
            if not isinstance(item, str) or not HASH.fullmatch(item):
                raise ValueError(f"invalid FINISH identity digest: {key}")
    for key in ("horizon", "retention_steps", "max_chunk_steps"):
        if key in value and (type(value[key]) is not int or value[key] < (1 if key == "max_chunk_steps" else 0)):
            raise ValueError("invalid bound FINISH execution budget")
    json_bytes(value)
    return deepcopy(value)


def _binding(result):
    return {key: deepcopy(result.get(key)) for key in _BINDING}


def _png(pixels):
    """Deterministic lossless RGB PNG, without editing pixels or Pillow imports."""
    pixels = np.ascontiguousarray(pixels)
    if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError("crop PNG requires original uint8 RGB pixels")
    height, width = pixels.shape[:2]
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    scanlines = b"".join(b"\x00" + row.tobytes() for row in pixels)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate FINISH evidence JSON key")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"nonfinite FINISH evidence JSON value: {value}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject)


class FinishEvidence:
    """Own one fresh ``run/evidence/<key>`` directory and its real input files."""
    def __init__(self, output: Path, identity: dict):
        self.output = Path(output).absolute()
        if self.output.parent.name != "evidence":
            raise ValueError("FINISH evidence output must be run/evidence/<episode-key>")
        self.run_dir = self.output.parent.parent
        self.relative = (Path("evidence") / self.output.name).as_posix()
        _contained(self.run_dir, self.relative + "/execution.json", ".json")
        self.identity = _identity(identity)
        self.data = {"schema_version": EVIDENCE_SCHEMA, "identity": deepcopy(self.identity),
                     "identity_sha256": digest(self.identity), "source_episode_sha256": None,
                     "configuration": None, "recording_status": "recording",
                     "capture_origin": "live_runner_reset_and_same_policy_forward",
                     "initial_observation": None, "initial_observation_typed_sha256": None,
                     "query_inputs": {}, "result": None}
        self._ready = self._finished = False

    def _write(self):
        if not self._ready:
            self.output.mkdir(parents=True, exist_ok=False)
            self._ready = True
        temporary = self.output / "execution.json.tmp"
        temporary.write_bytes(json_bytes(self.data) + b"\n")
        os.replace(temporary, self.output / "execution.json")

    def _reference(self, reference):
        return {**reference, "path": self.relative + "/" + reference["path"]}

    def begin_episode(self, episode, *, mode, configuration):
        if self.data["source_episode_sha256"] is not None:
            raise RuntimeError("FINISH evidence cannot be reused")
        if mode != self.identity["mode"]:
            raise ValueError("FINISH evidence mode differs from runner mode")
        for key in ("episode_id", "state_sha256"):
            if episode.get(key) != self.identity[key]:
                raise ValueError(f"FINISH evidence belongs to another {key}")
        for key, value in configuration.items():
            if key in self.identity and self.identity[key] != value:
                raise ValueError("FINISH execution budget differs from bound run configuration")
        self.data.update(source_episode_sha256=digest(episode), configuration=deepcopy(configuration))
        self._write()

    def capture_initial(self, observation):
        if self.data["initial_observation"] is not None:
            raise RuntimeError("initial FINISH observation can be captured only once")
        _observation(observation)
        reference = save_observation_artifact(self.output, "initial_observation.npz", observation)
        self.data["initial_observation"] = self._reference(reference)
        self.data["initial_observation_typed_sha256"] = observation_sha256(observation)
        loaded = load_observation_artifact(self.run_dir, self.data["initial_observation"])
        if observation_sha256(loaded) != self.data["initial_observation_typed_sha256"]:
            raise ValueError("live reset observation failed lossless roundtrip")
        self._write()

    def capture_query(self, sequence, value, head_identity):
        if head_identity["artifact_sha256"] != self.identity["head_sha256"]:
            raise ValueError("returned FINISH head differs from the configured artifact")
        if type(sequence) is not int or sequence < 1 or str(sequence) in self.data["query_inputs"]:
            raise ValueError("invalid/reused FINISH query input sequence")
        value = validate_input_evidence(value)
        arrays = {key: value[key] for key in ("tensors", "crops")}
        local = save_observation_artifact(self.output, f"query_{sequence:04d}.npz", arrays)
        reference = {"schema_version": INPUT_REFERENCE_SCHEMA, "input_sha256": input_sha256(value),
                     "tensor_dtypes": deepcopy(value["tensor_dtypes"]), "arrays": self._reference(local), "crops": {}}
        # Register each real artifact immediately so partial failures retain it.
        self.data["query_inputs"][str(sequence)] = reference
        for camera, pixels in value["crops"].items():
            name = f"query_{sequence:04d}_{camera}.png"
            raw = _png(pixels)
            with (self.output / name).open("xb") as stream:
                stream.write(raw)
            reference["crops"][camera] = {"path": self.relative + "/" + name, "sha256": _sha(raw),
                                           "pixels_sha256": observation_sha256({camera: pixels})}
        self._write()
        return deepcopy(reference)

    def record(self, result):
        self.data["result"] = _binding(result)
        self._write()

    def _finish_reference(self, status):
        reference = {"schema_version": EVIDENCE_SCHEMA, "status": status, "identity_sha256": digest(self.identity)}
        path = self.output / "execution.json"
        if self._ready and path.is_file():
            reference.update(path=self.relative + "/execution.json", sha256=_sha(path.read_bytes()))
        if self.data["initial_observation"] is not None:
            reference["initial_observation"] = deepcopy(self.data["initial_observation"])
        return reference

    def finish(self, result):
        if self._finished:
            raise RuntimeError("FINISH evidence already finalized")
        self.data.update(result=_binding(result), recording_status="finished")
        self._write()
        self._finished = True
        return self._finish_reference("recorded")

    def failure_reference(self, error):
        reference = self._finish_reference("evidence_error")
        reference["error"] = f"{type(error).__name__}: {error}"
        return reference


def load_query_input(run_dir, reference, *, complete=True):
    """Load and verify original typed inputs and their unedited crop PNGs."""
    if not isinstance(reference, dict) or reference.get("schema_version") != INPUT_REFERENCE_SCHEMA:
        raise ValueError("missing FINISH processed-input artifact")
    arrays = load_observation_artifact(run_dir, reference["arrays"])
    if set(arrays) != {"tensors", "crops"}:
        raise ValueError("processed-input archive contains unapproved metadata/truth")
    value = validate_input_evidence({"schema_version": INPUT_SCHEMA, "tensor_dtypes": reference["tensor_dtypes"], **arrays})
    if input_sha256(value) != reference.get("input_sha256"):
        raise ValueError("actual processed-input hash differs from the query ledger")
    crops = reference.get("crops")
    if not isinstance(crops, dict) or not set(crops).issubset({"agentview", "wrist"}):
        raise ValueError("invalid camera crop references")
    if complete and set(crops) != {"agentview", "wrist"}:
        raise ValueError("missing one of the actual camera crop images")
    for camera, image in crops.items():
        path = _contained(run_dir, image["path"], ".png")
        raw = path.read_bytes()
        pixels = value["crops"][camera]
        if (_sha(raw) != image.get("sha256") or raw != _png(pixels)
                or image.get("pixels_sha256") != observation_sha256({camera: pixels})):
            raise ValueError("crop PNG/hash does not match the actual same-forward pixels")
    return value


def _validate(run_dir, result, episode, identity):
    identity = _identity(identity)
    reference = result.get("finish_evidence")
    if not isinstance(reference, dict) or reference.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("missing FINISH evidence; legacy STOP evidence is not compatible")
    if reference.get("identity_sha256") != digest(identity):
        raise ValueError("FINISH evidence identity differs")
    failure = reference.get("status") == "evidence_error"
    if failure:
        if result.get("status") != "runtime_error" or not str(result.get("error_phase", "")).startswith("evidence_"):
            raise ValueError("partial FINISH evidence requires an explicit technical evidence error")
    elif reference.get("status") != "recorded":
        raise ValueError("unsupported FINISH evidence status")
    if reference.get("initial_observation") is not None:
        load_observation_artifact(run_dir, reference["initial_observation"])
    if not reference.get("path"):
        if not failure or reference.get("sha256") is not None:
            raise ValueError("recorded FINISH evidence requires an index")
        return {"verified": False, "status": "evidence_error", "reason": "index_unavailable"}
    raw = _contained(run_dir, reference["path"], ".json").read_bytes()
    if _sha(raw) != reference.get("sha256"):
        raise ValueError("FINISH evidence index bytes changed")
    data = _strict_json(raw)
    if (data.get("schema_version") != EVIDENCE_SCHEMA or data.get("identity") != identity
            or data.get("identity_sha256") != digest(identity)
            or data.get("source_episode_sha256") not in (None, digest(episode))):
        raise ValueError("FINISH evidence belongs to a different source/run/head")
    initial = data.get("initial_observation")
    if initial != reference.get("initial_observation"):
        raise ValueError("initial observation references disagree")
    if initial is not None:
        observation = load_observation_artifact(run_dir, initial)
        _observation(observation)
        if observation_sha256(observation) != data.get("initial_observation_typed_sha256"):
            raise ValueError("actual initial observation dtype/value hash changed")
    inputs = data.get("query_inputs")
    if not isinstance(inputs, dict):
        raise ValueError("invalid FINISH query input table")
    for sequence, item in inputs.items():
        if not isinstance(sequence, str) or not sequence.isdecimal() or str(int(sequence)) != sequence or int(sequence) < 1:
            raise ValueError("invalid query input sequence")
        # Even explicit failures never exempt an existing claimed file/hash.
        partial_query = (result.get("status") == "runtime_error" and result.get("error_phase") == "evidence_query"
                         and result.get("queries") and sequence == str(result["queries"][-1].get("sequence"))
                         and result["queries"][-1].get("input_evidence") is None
                         and result["queries"][-1].get("accepted_chunk_length") == 0)
        load_query_input(run_dir, item, complete=not (failure or partial_query))
    if failure:
        return {"verified": False, "status": "evidence_error", "reason": "partial_recording"}
    if (data.get("recording_status") != "finished" or data.get("source_episode_sha256") != digest(episode)
            or data.get("capture_origin") != "live_runner_reset_and_same_policy_forward"
            or data.get("result") != _binding(result)):
        raise ValueError("FINISH result/ledger is not bound to this finalized live execution")
    validate_finish_result(result, episode)
    if result["mode"] != identity["mode"] or data["configuration"] != result["configuration"]:
        raise ValueError("FINISH mode/budget differs from its recorded run")
    for key, value in result["configuration"].items():
        if key in identity and value != identity[key]:
            raise ValueError("FINISH budget differs from the bound run configuration")
    if (result["trace"] or result["queries"]) and initial is None:
        raise ValueError("missing actual step-zero observation")
    used = set()
    for row in result["queries"]:
        sequence = str(row["sequence"])
        if row["sequence"] == 1 and row["observation_sha256"] != data["initial_observation_typed_sha256"]:
            raise ValueError("first policy query did not use the captured live reset observation")
        item = row.get("input_evidence")
        if row["status"] == "valid":
            if item is None:
                # A failed save can leave a truthful result with no accepted actions.
                if result["status"] != "runtime_error" or result.get("error_phase") != "evidence_query" or row["accepted_chunk_length"]:
                    raise ValueError("valid query lacks its actual processed-input archive")
                if sequence in inputs:
                    used.add(sequence)
                continue
            if item != inputs.get(sequence) or item.get("input_sha256") != row["input_sha256"]:
                raise ValueError("query input references/hash differ from the saved evidence")
            if row["head_identity"]["artifact_sha256"] != identity["head_sha256"]:
                raise ValueError("query used a different head artifact")
            used.add(sequence)
        elif item is not None:
            raise ValueError("failed inference claimed a valid processed input")
    if used != set(inputs):
        raise ValueError("unbound or substituted FINISH query input artifact")
    return {"verified": True, "status": "recorded", "protocol_version": PROTOCOL,
            "queries": len(result["queries"]), "n_steps": result["n_steps"]}


def validate_finish_evidence(run_dir, result, episode, identity):
    """Verify live inputs, head/run identity and exact execution ledger offline."""
    try:
        return _validate(run_dir, result, episode, identity)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(f"malformed FINISH evidence: {error}") from error
