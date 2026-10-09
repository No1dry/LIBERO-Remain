"""Optional evaluator evidence from live runner observations and action queues.

No simulator, policy, render or inference call is made here. Observation hashes
describe the raw, whitelisted observation before adapter preprocessing, not the
final encoder tensors. Only step zero has a lossless observation archive.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

import numpy as np

from .observation_artifact import load_observation_artifact, save_observation_artifact


SCHEMA_VERSION = "remaining-goals-execution-evidence-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY = {"run_id", "manifest_hash", "run_config_sha256", "episode_id", "state_sha256",
             "selection_sha256", "instruction_mode"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _digest(value):
    return _hash(_json(value))


def _identity(value):
    if not isinstance(value, dict) or not _IDENTITY.issubset(value):
        raise ValueError("execution evidence requires the complete run/selection/episode identity")
    if any(not isinstance(value[key], str) or not value[key] for key in _IDENTITY):
        raise ValueError("execution evidence identity fields must be nonempty strings")
    for key, item in value.items():
        if key.endswith("_sha256") or key == "manifest_hash":
            if not isinstance(item, str) or not _HASH.fullmatch(item):
                raise ValueError(f"invalid execution identity digest: {key}")
    if "max_chunk_steps" in value and (type(value["max_chunk_steps"]) is not int or value["max_chunk_steps"] < 1):
        raise ValueError("identity max_chunk_steps must be a positive integer")
    _json(value)
    return deepcopy(value)


def observation_sha256(observation):
    """Hash keys, original array dtype/shape and exact C-order raw bytes."""
    digest = hashlib.sha256()
    def visit(value):
        if isinstance(value, dict):
            if not value or any(not isinstance(key, str) for key in value):
                raise ValueError("observation dictionaries require string keys")
            digest.update(_json(["dict", sorted(value)]))
            for key in sorted(value):
                visit(value[key])
        else:
            array = np.asarray(value)
            if array.dtype.kind not in "fiu" or not array.size or not np.isfinite(array).all():
                raise ValueError("observation hashes require finite real arrays")
            raw = np.ascontiguousarray(array).tobytes()
            digest.update(_json(["array", array.dtype.str, list(array.shape), len(raw)]))
            digest.update(raw)
    visit(observation)
    return digest.hexdigest()


def _contained(base, relative, suffix):
    if not isinstance(relative, str) or not relative:
        raise ValueError("evidence reference requires a relative path")
    posix, windows = PurePosixPath(relative.replace("\\", "/")), PureWindowsPath(relative)
    if (posix.is_absolute() or windows.drive or windows.root or ".." in posix.parts
            or posix.suffix != suffix or any(":" in part or part.endswith((" ", ".")) for part in posix.parts)):
        raise ValueError("evidence path must be contained and portable")
    base = Path(base).resolve()
    target = (base / Path(*posix.parts)).resolve()
    if not target.is_relative_to(base):
        raise ValueError("evidence path escaped its run")
    return target


def _result_binding(result):
    return {**{key: deepcopy(result.get(key)) for key in
               ("status", "n_steps", "policy_queries", "stop_step", "error", "error_phase")},
            "trace_sha256": _digest(result["trace"])}


def _action(value):
    array = np.asarray(value)
    if array.shape != (7,) or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
        raise ValueError("evidence action must be a finite decoded 7-vector")
    return array.astype(np.float64)


def _same_action(left, right):
    return _action(left).tobytes() == _action(right).tobytes()


class EpisodeEvidence:
    """Record one episode in a fresh ``run_dir/evidence/<episode-key>`` directory.

    Hooks are used only by the runner. Failed writes are fatal technical errors,
    unlike optional video encoding failures. Existing evidence is never reused.
    """
    def __init__(self, output: Path, identity: dict):
        self.output = Path(output).absolute()
        if self.output.parent.name != "evidence":
            raise ValueError("episode evidence output must be run_dir/evidence/<episode-key>")
        self.relative = (Path("evidence") / self.output.name).as_posix()
        _contained(self.output.parent.parent, self.relative + "/execution.json", ".json")
        self.identity = _identity(identity)
        self.data = {"schema_version": SCHEMA_VERSION, "identity": self.identity,
                     "identity_sha256": _digest(self.identity), "recording_status": "recording",
                     "capture_origin": "live_env_reset_after_runner_observation_whitelist",
                     "observation_scope": "raw observation before adapter preprocessing; not final encoder tensors",
                     "episode_sha256": None, "configuration": None, "initial_observation": None,
                     "initial_observation_typed_sha256": None, "queries": [], "executed_actions": [], "result": None}
        self._ready = False
        self._pending = None
        self._finished = False

    def _write(self):
        if not self._ready:
            self.output.mkdir(parents=True, exist_ok=False)
            self._ready = True
        body = {**self.data, "prepared_query": self._pending}
        temporary = self.output / "execution.json.tmp"
        temporary.write_bytes(_json(body) + b"\n")
        os.replace(temporary, self.output / "execution.json")

    def begin_episode(self, episode, *, max_chunk_steps, scheduled_steps):
        if self.data["episode_sha256"] is not None:
            raise RuntimeError("episode evidence cannot be reused")
        for key in ("episode_id", "state_sha256"):
            if episode.get(key) != self.identity[key]:
                raise ValueError(f"execution evidence identity differs from episode {key}")
        if "max_chunk_steps" in self.identity and self.identity["max_chunk_steps"] != max_chunk_steps:
            raise ValueError("runner chunk limit differs from the bound run configuration")
        self.data["episode_sha256"] = _digest(episode)
        self.data["configuration"] = {"max_chunk_steps": max_chunk_steps, "scheduled_steps": scheduled_steps}
        self._write()

    def capture_initial(self, observation):
        if self.data["initial_observation"] is not None:
            raise RuntimeError("actual initial observation can only be captured once")
        self.data["initial_observation"] = save_observation_artifact(self.output, "initial_observation.npz", observation)
        self.data["initial_observation_typed_sha256"] = observation_sha256(observation)
        loaded = load_observation_artifact(self.output, self.data["initial_observation"])
        if observation_sha256(loaded) != self.data["initial_observation_typed_sha256"]:
            raise ValueError("actual initial observation failed its lossless typed roundtrip")
        self._write()

    def prepare_query(self, observation, *, obs_step, sequence):
        if self._pending is not None or sequence != len(self.data["queries"]) + 1:
            raise RuntimeError("execution evidence query sequence is inconsistent")
        if obs_step != len(self.data["executed_actions"]):
            raise RuntimeError("query observation does not follow the executed action prefix")
        self._pending = {"sequence": sequence, "observation_step": obs_step,
                         "observation_sha256": observation_sha256(observation),
                         "response": "pending", "returned_shape": None, "returned_chunk_length": None,
                         "accepted_chunk_length": 0, "accepted_actions": [], "executed_steps": []}
        # Prepared is not a claimed model call. finish() uses the runner's true
        # query counter to distinguish evidence failure from a predict failure.
        self._write()

    def query_returned(self, prediction):
        if self._pending is None:
            raise RuntimeError("query return without a prepared input")
        row = self._pending
        self._pending = None
        self.data["queries"].append(row)
        if prediction is None:
            row.update(response="stop", returned_chunk_length=0)
        else:
            row["response"] = "returned_unvalidated"
            try:
                shape = list(np.asarray(prediction).shape)
                row["returned_shape"] = shape
                if shape == [7]:
                    row["returned_chunk_length"] = 1
                elif len(shape) == 2 and shape[1] == 7:
                    row["returned_chunk_length"] = shape[0]
            except (TypeError, ValueError):
                pass  # the unchanged runner owns action validation
        self._write()

    def accept_actions(self, actions, *, chunk_limit):
        row = self.data["queries"][-1]
        array = np.asarray(actions)
        if (row["response"] != "returned_unvalidated" or array.ndim != 2 or array.shape[1] != 7
                or len(array) < 1 or not np.isfinite(array).all()):
            raise ValueError("evidence expected the runner's validated action chunk")
        accepted = array[:chunk_limit]
        row.update(response="actions", returned_chunk_length=len(array),
                   accepted_chunk_length=len(accepted), accepted_actions=accepted.tolist())
        self._write()

    def action_executed(self, step, action, *, stopped):
        if step != len(self.data["executed_actions"]) + 1 or not self.data["queries"]:
            raise RuntimeError("execution evidence step sequence is inconsistent")
        row = self.data["queries"][-1]
        offset = len(row["executed_steps"])
        if stopped:
            if row["response"] != "stop":
                raise RuntimeError("hold action has no explicit policy STOP")
        elif (row["response"] != "actions" or offset >= row["accepted_chunk_length"]
              or not _same_action(action, row["accepted_actions"][offset])):
            raise RuntimeError("executed action differs from the accepted policy chunk")
        row["executed_steps"].append(step)
        self.data["executed_actions"].append({"step": step, "query_sequence": row["sequence"],
                                               "chunk_index": None if stopped else offset,
                                               "stopped": bool(stopped), "action": _action(action).tolist()})
        self._write()

    def _reference(self, status):
        result = {"schema_version": SCHEMA_VERSION, "status": status,
                  "identity_sha256": self.data["identity_sha256"]}
        path = self.output / "execution.json"
        if self._ready and path.is_file():
            result.update(path=self.relative + "/execution.json", sha256=_hash(path.read_bytes()))
        if self.data["initial_observation"] is not None:
            initial = deepcopy(self.data["initial_observation"])
            initial["path"] = self.relative + "/" + initial["path"]
            result["initial_observation"] = initial
        return result

    def finish(self, result):
        if self._finished:
            raise RuntimeError("episode evidence finish called twice")
        if self._pending is not None:
            if result["policy_queries"] == len(self.data["queries"]) + 1:
                self._pending["response"] = "error"
                self.data["queries"].append(self._pending)
            self._pending = None
        for row in self.data["queries"]:
            executed = len(row["executed_steps"])
            row["execution_interval"] = ([row["executed_steps"][0], row["executed_steps"][-1]] if executed else None)
            row["executed_policy_actions"] = executed if row["response"] == "actions" else 0
            row["executed_hold_actions"] = executed if row["response"] == "stop" else 0
            row["unexecuted_accepted_actions"] = row["accepted_chunk_length"] - row["executed_policy_actions"]
        self.data.update(recording_status="finished", result=_result_binding(result))
        self._write()
        self._finished = True
        return self._reference("recorded")

    def failure_reference(self, error):
        """Best available references after a write failure; never invent a file."""
        try:
            result = self._reference("evidence_error")
        except Exception:
            result = {"schema_version": SCHEMA_VERSION, "status": "evidence_error",
                      "identity_sha256": self.data["identity_sha256"]}
        result["error"] = f"{type(error).__name__}: {error}"
        return result


def _read_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate execution evidence JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite execution evidence JSON value: {value}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


def _validate_execution_evidence(run_dir, result, episode, identity):
    """Check saved evidence against this run, source episode and actual trace.

    Explicit evidence-write failures can remain readable error records. Every
    file they *do* reference is still verified; this never excuses corruption.
    The returned report distinguishes partial evidence from verified recording.
    """
    identity = _identity(identity)
    for key in ("n_steps", "policy_queries"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError(f"execution result {key} must be a nonnegative integer")
    if result.get("stop_step") is not None and (type(result["stop_step"]) is not int or result["stop_step"] < 0):
        raise ValueError("execution STOP boundary must be an integer or null")
    reference = result.get("execution_evidence")
    if not isinstance(reference, dict) or reference.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("missing execution evidence reference")
    if reference.get("identity_sha256") != _digest(identity):
        raise ValueError("execution evidence identity hash mismatch")
    failure = reference.get("status") == "evidence_error"
    if failure and (result.get("status") != "runtime_error" or not str(result.get("error_phase", "")).startswith("evidence_")):
        raise ValueError("evidence_error requires an explicit evidence runtime error")
    if not failure and reference.get("status") != "recorded":
        raise ValueError("unsupported execution evidence status")
    initial_reference = reference.get("initial_observation")
    if initial_reference is not None:
        # A claimed initial archive is never exempted by failure status.
        load_observation_artifact(run_dir, initial_reference)
    if not reference.get("path"):
        if not failure or reference.get("sha256") is not None:
            raise ValueError("recorded execution evidence needs its index file")
        return {"verified": False, "status": "evidence_error", "reason": "index_unavailable"}
    path = _contained(run_dir, reference["path"], ".json")
    raw = path.read_bytes()
    if _hash(raw) != reference.get("sha256"):
        raise ValueError("execution evidence file hash mismatch")
    data = _read_json(raw)
    if (data.get("schema_version") != SCHEMA_VERSION or data.get("identity") != identity
            or data.get("identity_sha256") != _digest(identity)):
        raise ValueError("execution evidence belongs to another run/selection/episode")
    if data.get("episode_sha256") not in (None, _digest(episode)):
        raise ValueError("execution evidence source episode differs")
    initial = data.get("initial_observation")
    if initial is not None:
        observation = load_observation_artifact(path.parent, initial)
        from .runner import _observation
        _observation(observation)  # never permit an artifact containing truth fields
        typed_hash = observation_sha256(observation)
        if typed_hash != data.get("initial_observation_typed_sha256"):
            raise ValueError("actual step-zero typed observation hash mismatch")
        expected_initial = {**initial, "path": (PurePosixPath(reference["path"]).parent / initial["path"]).as_posix()}
        if initial_reference != expected_initial:
            raise ValueError("result and index initial observation references differ")
    elif initial_reference is not None:
        raise ValueError("index did not capture the referenced initial observation")
    if failure:
        # Partial index may precede the last successful physical action. Its
        # files and identity were checked above, but it cannot certify a trace.
        return {"verified": False, "status": "evidence_error", "reason": "partial_recording"}
    if data.get("recording_status") != "finished" or data.get("prepared_query") is not None:
        raise ValueError("recorded execution evidence is not finalized")
    if data.get("result") != _result_binding(result):
        raise ValueError("execution evidence result/trace binding mismatch")
    if (data.get("capture_origin") != "live_env_reset_after_runner_observation_whitelist"
            or data.get("episode_sha256") != _digest(episode)):
        raise ValueError("execution evidence is not bound to the actual runner reset")
    config = data.get("configuration")
    total = episode["retention_steps"] + (0 if all(episode["initial_mask"]) else episode["horizon"])
    if (not isinstance(config, dict) or config.get("scheduled_steps") != total
            or type(config.get("scheduled_steps")) is not int
            or type(config.get("max_chunk_steps")) is not int or config["max_chunk_steps"] < 1):
        raise ValueError("execution evidence rollout budget differs")
    if "max_chunk_steps" in identity and config["max_chunk_steps"] != identity["max_chunk_steps"]:
        raise ValueError("execution chunk limit differs from the bound run configuration")
    queries, actions = data.get("queries"), data.get("executed_actions")
    if not isinstance(queries, list) or not isinstance(actions, list):
        raise ValueError("execution evidence query/action tables must be lists")
    if len(queries) != result["policy_queries"] or len(actions) != result["n_steps"]:
        raise ValueError("execution evidence actual query/action counts differ")
    if (queries or result["trace"]) and initial is None:
        raise ValueError("missing actual initial observation")
    next_step = 1
    stop_step = None
    for sequence, row in enumerate(queries, 1):
        if (type(row.get("sequence")) is not int or type(row.get("observation_step")) is not int
                or row.get("sequence") != sequence or row.get("observation_step") != next_step - 1
                or not isinstance(row.get("observation_sha256"), str) or not _HASH.fullmatch(row["observation_sha256"])):
            raise ValueError("query sequence or decision observation step/hash differs")
        if sequence == 1 and row["observation_sha256"] != data["initial_observation_typed_sha256"]:
            raise ValueError("first query did not use the captured step-zero observation")
        response = row.get("response")
        accepted = row.get("accepted_chunk_length")
        if type(accepted) is not int or accepted < 0 or not isinstance(row.get("accepted_actions"), list):
            raise ValueError("invalid accepted chunk metadata")
        executed = row.get("executed_steps")
        if (not isinstance(executed, list) or any(type(step) is not int for step in executed)
                or executed != list(range(next_step, next_step + len(executed)))):
            raise ValueError("query execution interval is not contiguous")
        if response == "actions":
            returned = row.get("returned_chunk_length")
            if (type(returned) is not int or returned < 1 or accepted != min(returned, config["max_chunk_steps"])
                    or len(row["accepted_actions"]) != accepted or len(executed) > accepted
                    or not isinstance(row.get("returned_shape"), list)
                    or any(type(dimension) is not int for dimension in row["returned_shape"])
                    or row.get("returned_shape") not in ([7], [returned, 7])
                    or (row.get("returned_shape") == [7] and returned != 1)):
                raise ValueError("returned/accepted action chunk lengths differ")
            if sequence < len(queries) and len(executed) != accepted:
                raise ValueError("next query occurred before the prior chunk was exhausted")
            for action in row["accepted_actions"]:
                _action(action)
        elif response in {"stop", "error", "returned_unvalidated"}:
            if accepted != 0 or row["accepted_actions"] or sequence != len(queries):
                raise ValueError("STOP/error response cannot have an accepted chunk or later query")
            if response == "stop":
                if row.get("returned_chunk_length") != 0 or row.get("returned_shape") is not None:
                    raise ValueError("invalid STOP response metadata")
                stop_step = row["observation_step"]
            elif executed or result["status"] == "completed":
                raise ValueError("an invalid/failed prediction cannot execute actions or complete")
        else:
            raise ValueError("unsupported query response")
        interval = [executed[0], executed[-1]] if executed else None
        policy_count = len(executed) if response == "actions" else 0
        hold_count = len(executed) if response == "stop" else 0
        if (row.get("execution_interval") != interval or row.get("executed_policy_actions") != policy_count
                or row.get("executed_hold_actions") != hold_count
                or row.get("unexecuted_accepted_actions") != accepted - policy_count):
            raise ValueError("query execution summary differs from executed steps")
        for offset, step in enumerate(executed):
            event = actions[step - 1]
            if (event.get("step") != step or event.get("query_sequence") != sequence
                    or event.get("stopped") is not (response == "stop")
                    or event.get("chunk_index") != (None if response == "stop" else offset)):
                raise ValueError("executed action query association differs")
            _action(event.get("action"))
            if response == "actions" and not _same_action(event["action"], row["accepted_actions"][offset]):
                raise ValueError("executed action differs from the accepted chunk prefix")
        next_step += len(executed)
    if next_step != len(actions) + 1 or result.get("stop_step") != stop_step:
        raise ValueError("action coverage or explicit STOP boundary differs")
    if len(result["trace"]) > len(actions) + 1:
        raise ValueError("trace extends beyond acknowledged physical actions")
    for expected_step, row in enumerate(result["trace"]):
        step = row["step"]
        if type(step) is not int or step != expected_step:
            raise ValueError("trace must be a contiguous prefix starting at zero")
        if step == 0:
            if row.get("action") is not None or row.get("stopped") is not False:
                raise ValueError("step-zero trace must precede any physical action or STOP")
            continue
        if type(step) is not int or not 1 <= step <= len(actions):
            raise ValueError("trace step is outside executed evidence")
        event = actions[step - 1]
        if row["stopped"] is not event["stopped"] or not _same_action(row["action"], event["action"]):
            raise ValueError("trace action differs from live execution evidence")
    if result["status"] == "completed" and (len(actions) != total or len(result["trace"]) != total + 1):
        raise ValueError("completed evidence lacks the full scheduled rollout")
    return {"verified": True, "status": "recorded", "queries": len(queries), "executed_steps": len(actions),
            "initial_observation": deepcopy(initial_reference)}


def validate_execution_evidence(run_dir, result, episode, identity):
    """Validate complete or explicitly failed partial live execution evidence.

    Malformed structures are rejected as ValueError; genuine file access
    failures remain errors. Referenced corrupt bytes are never excused by a
    runtime-error label. A failed partial recording returns verified=False.
    """
    try:
        return _validate_execution_evidence(run_dir, result, episode, identity)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"malformed execution evidence: {exc}") from exc
