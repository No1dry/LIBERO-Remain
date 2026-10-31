"""Live whitelisted inputs and immutable execution binding for headless runs."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from ..observation_artifact import save_observation_artifact, load_observation_artifact
from ..pilot_evidence import observation_sha256
from ..runner import _observation
from .schema import canonical_hash, validate_result

SCHEMA = "remaining-headless-evidence-v1"


def _identity(value):
    if not isinstance(value, dict) or not value.get("episode_id") or not value.get("state_sha256"):
        raise ValueError("headless evidence requires its full source/run identity")
    canonical_hash(value)
    return deepcopy(value)


def _binding(result):
    return {key: deepcopy(value) for key, value in result.items()
            if key not in {"video", "execution_evidence", "evidence_validation"}}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _contained(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError("evidence path must remain relative to its run")
    root, target = Path(root).resolve(), (Path(root) / name).resolve()
    if target == root or root not in target.parents:
        raise ValueError("evidence path escapes its run")
    return target


class HeadlessEvidence:
    def __init__(self, output, identity):
        self.output = Path(output)
        self.identity = _identity(identity)
        self.relative = f"{self.output.parent.name}/{self.output.name}"
        self.output.mkdir(parents=True, exist_ok=False)
        self.data = {"schema_version": SCHEMA, "identity": self.identity,
                     "identity_sha256": canonical_hash(self.identity), "episode_sha256": None,
                     "initial_observation": None, "queries": [], "result_sha256": None, "status": "recording"}
        self._finished = False
        self._write()

    def _write(self):
        temporary = self.output / "execution.json.tmp"
        temporary.write_text(json.dumps(self.data, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, self.output / "execution.json")

    def begin_episode(self, episode):
        if self.data["episode_sha256"] is not None:
            raise ValueError("evidence cannot be reused")
        if any(self.identity[key] != episode[key] for key in ("episode_id", "state_sha256")):
            raise ValueError("evidence source differs from the actual reset episode")
        self.data["episode_sha256"] = canonical_hash(episode)
        self._write()

    def capture_initial(self, observation):
        if self.data["initial_observation"] is not None:
            raise ValueError("initial observation captured twice")
        self.data["initial_observation"] = save_observation_artifact(self.output, "initial.npz", _observation(observation))
        self._write()

    def capture_query_input(self, observation, *, sequence, step):
        if sequence != len(self.data["queries"]) + 1:
            raise ValueError("query input sequence differs")
        reference = save_observation_artifact(self.output, f"query_{sequence:04d}.npz", _observation(observation))
        self.data["queries"].append({"sequence": sequence, "observation_step": step,
                                   "observation_sha256": observation_sha256(observation), "observation": reference})
        self._write()

    def _reference(self, status):
        reference = {"schema_version": SCHEMA, "status": status, "identity_sha256": canonical_hash(self.identity)}
        path = self.output / "execution.json"
        if path.is_file():
            reference.update(path=self.relative + "/execution.json", sha256=_sha(path))
        return reference

    def finish(self, result):
        if self._finished:
            raise ValueError("evidence finalized twice")
        self.data.update(status="recorded", result_sha256=canonical_hash(_binding(result)))
        self._write()
        self._finished = True
        return self._reference("recorded")

    def failure_reference(self, error):
        try:
            reference = self._reference("evidence_error")
        except Exception:
            reference = {"schema_version": SCHEMA, "status": "evidence_error", "identity_sha256": canonical_hash(self.identity)}
        reference["error"] = f"{type(error).__name__}: {error}"
        return reference


def validate_evidence(run_dir, result, episode, identity):
    identity = _identity(identity)
    validated = validate_result(result, episode, identity)
    reference = result.get("execution_evidence", {})
    if reference.get("schema_version") != SCHEMA or reference.get("identity_sha256") != canonical_hash(identity):
        raise ValueError("headless evidence belongs to another run/source/model")
    failed = reference.get("status") == "evidence_error"
    if failed and (result["status"] != "runtime_error" or not str(result.get("error_phase", "")).startswith("evidence")):
        raise ValueError("partial evidence requires an explicit recording failure")
    if not reference.get("path"):
        if failed:
            return {"verified": False, "status": "evidence_error"}
        raise ValueError("missing execution index")
    path = _contained(run_dir, reference["path"])
    if _sha(path) != reference.get("sha256"):
        raise ValueError("execution index bytes changed")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate evidence JSON key")
            value[key] = item
        return value
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite evidence")))
    if (data.get("schema_version") != SCHEMA or data.get("identity") != identity or
            data.get("identity_sha256") != canonical_hash(identity) or
            data.get("episode_sha256") not in (None, canonical_hash(episode))):
        raise ValueError("execution index/source identity differs")
    initial = data.get("initial_observation")
    if initial is not None:
        actual = _observation(load_observation_artifact(path.parent, initial))
        if result.get("initial_observation_sha256") != observation_sha256(actual):
            raise ValueError("actual step-zero observation differs")
    rows = data.get("queries", [])
    for row in rows:
        actual = _observation(load_observation_artifact(path.parent, row["observation"]))
        if observation_sha256(actual) != row["observation_sha256"]:
            raise ValueError("query raw observation differs")
    if failed:
        return {"verified": False, "status": "evidence_error", "path_length_m": validated["path_length_m"]}
    if (reference.get("status") != "recorded" or data.get("status") != "recorded"
            or data.get("episode_sha256") != canonical_hash(episode)
            or data.get("result_sha256") != canonical_hash(_binding(result)) or len(rows) != len(result["queries"])):
        raise ValueError("execution result or query ledger binding differs")
    if result["trace"] and initial is None:
        raise ValueError("missing actual reset observation")
    for saved, query in zip(rows, result["queries"]):
        if any(saved[key] != query[key] for key in ("sequence", "observation_step", "observation_sha256")):
            raise ValueError("query does not refer to its recorded input")
    return {**validated, "status": "recorded", "queries": len(rows)}
