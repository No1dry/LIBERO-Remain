"""File-only, fixed-source plans for the authorized init35 action-prefix audit.

No simulator, checkpoint, policy, processor or feature extractor is imported.
The constants identify the reviewed source bytes, not the diagnostic code.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np

from .data import _contained, canonical_hash, read_json
from .workflow import file_sha, load_source, read_run, write_json
from ..observation_artifact import load_observation_artifact
from ..pilot_evidence import observation_sha256


SCHEMA = "remaining-release-observability-plan-v1"
FILE_MANIFEST_SCHEMA = "remaining-release-observability-file-manifest-v1"
SOURCE_COMMIT = "3433f487d38efe0a08e4c814e87412aad5aba9fe"
RUN_ID = "65c8ef90d9d7495ebc8234cb814e3b5a"
EPISODE_ID = "basket_s035_00"
STATE_PATH = "sources/035/states/basket_s035_00.npy"
MAX_ACTION_STEPS = 292
SOURCE_SHA256 = {
    "run": "0c0fa4803d1e7a8a9b1a3a1ab2fe15f55c7b2e35a66436117d2fddd60283fb9b",
    "raw": "049ac123d348402177c30c9b2915b88e9573ea3bed18663c0f1fcc3eb6af3e78",
    "bank": "084e55537c25e515153e48624d807483b3348f9cee67db77425f69d5eaa6080c",
    "state": "e1d42bfb1aa9c21e52615e95e8f834eedbf361592c259d654e5a807423ba408f",
    "model_xml": "dad2437d1c2f8cbff26232c252f241978ce7de02cc6e34da0267fc94f4607163",
    "bddl": "2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618",
}
CONFIGURATION = {"horizon": 520, "retention_steps": 150, "max_chunk_steps": 8}
COMPARISON = {
    "actions": "original_json_decoded_float64_bit_exact",
    "query_observations": "original_raw_observation_sha256_exact",
    "evaluator": "original_typed_truth_and_float64_evidence_exact",
    "first_mismatch": "stop_and_preserve_partial",
    "new_numeric_tolerance": None,
}


def _budget(episode_id, value):
    if episode_id != EPISODE_ID:
        raise ValueError("release audit authorizes only basket_s035_00")
    if type(value) is not int or not 1 <= value <= MAX_ACTION_STEPS:
        raise ValueError("max_action_steps must be an integer in 1..292")


def _pin(path, key):
    actual = file_sha(path)
    if actual != SOURCE_SHA256[key]:
        raise ValueError(f"fixed {key} SHA256 mismatch: expected={SOURCE_SHA256[key]} actual={actual}")
    return actual


def _array(value, shape):
    raw = np.asarray(value)
    if raw.shape != shape or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
        raise ValueError(f"action shape/dtype must be finite numeric {shape}; actual={raw.shape}/{raw.dtype}")
    return np.ascontiguousarray(raw, dtype="<f8")


def _same_bits(left, right):
    return left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()


def _typed(array):
    return {"dtype": array.dtype.str, "shape": list(array.shape),
            "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest()}


def _source_files(run_dir, metadata, results, bank_path, bank):
    """Inventory exactly the files consumed by the historical validators."""
    files = {}

    def add(path, role, expected_sha=None):
        path = Path(path).resolve()
        entry = {"path": str(path), "sha256": file_sha(path), "bytes": path.stat().st_size}
        if expected_sha is not None and entry["sha256"] != expected_sha:
            raise ValueError(f"source file changed while freezing {role}")
        if str(path) not in files:
            files[str(path)] = {**entry, "roles": []}
        files[str(path)]["roles"].append(role)

    def reference(root, value, role):
        add(_contained(root, value["path"]), role, value["sha256"])

    add(run_dir / "run.json", "source_run", SOURCE_SHA256["run"])
    for ref, result in zip(metadata["results"], results):
        reference(run_dir, ref, "raw_result")
        evidence = result["finish_evidence"]
        reference(run_dir, evidence, "execution_evidence")
        index = read_json(_contained(run_dir, evidence["path"]))
        reference(run_dir, index["initial_observation"], "live_initial_observation")
        for item in index["query_inputs"].values():
            reference(run_dir, item["arrays"], "actual_query_inputs")
            for crop in item["crops"].values():
                reference(run_dir, crop, "actual_query_crop")
        if result.get("video", {}).get("status") == "saved":
            reference(run_dir, result["video"], "original_video")
    add(bank_path, "normal_bank", SOURCE_SHA256["bank"])
    audit_hashes = {}
    for item in bank["preparations"]:
        reference(bank_path.parent, item, "normal_preparation")
        preparation = read_json(_contained(bank_path.parent, item["path"]))
        audit_hashes[preparation["episode"]["episode_id"]] = preparation["provenance"]["technical_audit_sha256"]
    for episode in bank["episodes"]:
        add(_contained(bank_path.parent, episode["state_path"]), "settled_state", episode["state_sha256"])
        reference(bank_path.parent, episode["initial_observation"], "construction_initial_observation")
        add(_contained(bank_path.parent, episode["construction"]["technical_audit"]), "normal_technical_audit",
            audit_hashes[episode["episode_id"]])
    return [files[key] for key in sorted(files)]


def _inspect_sources(source_run, episode_id, maximum):
    _budget(episode_id, maximum)
    run_dir = Path(source_run).resolve()
    _pin(run_dir / "run.json", "run")
    _pin(_contained(run_dir, "raw/0000.json"), "raw")
    metadata, results = read_run(run_dir)
    frozen = metadata["plan"]
    if (metadata.get("run_id") != RUN_ID or metadata.get("status") != "completed"
            or metadata.get("mode") != "shadow" or metadata.get("purpose") != "validation_shadow"
            or metadata.get("configuration") != CONFIGURATION):
        raise ValueError("source run is not the fixed completed H520/W150 chunk8 validation shadow")
    selected = [e for e in metadata["episodes"] if e.get("episode_id") == episode_id]
    selected_results = [r for r in results if r.get("episode_id") == episode_id]
    if len(selected) != 1 or len(selected_results) != 1:
        raise ValueError("source run must contain the authorized episode exactly once")
    episode, result = deepcopy(selected[0]), selected_results[0]
    raw_ref = next(r for r in metadata["results"] if r["episode_id"] == episode_id)
    if raw_ref["path"] != "raw/0000.json" or raw_ref["sha256"] != SOURCE_SHA256["raw"]:
        raise ValueError("authorized raw result must be raw/0000.json with its fixed SHA256")
    if (type(episode.get("initial_state_index")) is not int or episode["initial_state_index"] != 35
            or type(episode.get("seed")) is not int or episode["seed"] != 35
            or episode.get("initial_mask") != [False, False] or episode.get("task_id") != "basket"
            or episode.get("suite") != "libero_10" or episode.get("state_path") != STATE_PATH
            or episode.get("state_sha256") != SOURCE_SHA256["state"]
            or episode.get("model_xml_sha256") != SOURCE_SHA256["model_xml"]
            or episode.get("bddl_sha256") != SOURCE_SHA256["bddl"]):
        raise ValueError("episode differs from the fixed init35 settled-bank state/XML/BDDL")
    bank_path = Path(frozen["source_path"]).resolve()
    _pin(bank_path, "bank")
    if frozen.get("source_file_sha256") != SOURCE_SHA256["bank"]:
        raise ValueError("run plan did not bind the authorized normal-bank file bytes")
    source = frozen["config"]["source"]
    if source.get("kind") != "normal_bank" or Path(source["manifest"]).resolve() != bank_path:
        raise ValueError("source must be the original normal bank, not an official raw init or edited state")
    bank, _ = load_source(source)
    if canonical_hash(bank) != metadata["manifest_hash"]:
        raise ValueError("run and original normal bank manifest identities differ")
    saved = [e for e in bank["episodes"] if e.get("episode_id") == episode_id]
    plain_episode = {key: value for key, value in episode.items() if key != "eval_source"}
    if len(saved) != 1 or saved[0] != plain_episode:
        raise ValueError("selected run episode differs from its original saved bank episode")
    environment = {"manifest_dir": str(bank_path.parent), "environment": deepcopy(bank["environment"]),
                   "image_size": 256, "control_freq": 20}
    if frozen.get("environment_config") != environment:
        raise ValueError("original run environment configuration differs from its bank")
    state_path = _contained(bank_path.parent, STATE_PATH)
    _pin(state_path, "state")
    with state_path.open("rb") as stream:
        state = np.load(stream, allow_pickle=False)
    if state.dtype != np.dtype("float64") or state.ndim != 1 or not state.size or not np.isfinite(state).all():
        raise ValueError("original settled state must be finite float64, not a substitute init")
    if (result.get("status") != "completed" or result.get("configuration") != CONFIGURATION
            or result.get("mode") != "shadow" or result.get("n_steps") != 670
            or result.get("timeout_step") != 520 or result.get("finish_step") is not None
            or len(result.get("queries", [])) != 66):
        raise ValueError("authorized source must retain its complete original shadow ledger")
    queries = result["queries"]
    if [q["observation_step"] for q in queries] != list(range(0, 521, 8)):
        raise ValueError("original query boundaries must be 0,8,...,520; no inserted query")
    actions = _array([row["action"] for row in result["executed_actions"][:maximum]], (maximum, 7))
    for number, (action, event) in enumerate(zip(actions, result["executed_actions"]), 1):
        sequence, chunk_index = (number - 1) // 8 + 1, (number - 1) % 8
        query = queries[sequence - 1]
        if (event["step"] != number or event["action_kind"] != "policy" or event.get("hold_cause") is not None
                or event.get("query_sequence") != sequence or event.get("chunk_index") != chunk_index):
            raise ValueError("action prefix must preserve original sequential policy/chunk ownership")
        for candidate in (result["trace"][number]["action"], query["candidate_actions"][chunk_index],
                          query["accepted_actions"][chunk_index]):
            if not _same_bits(action, _array(candidate, (7,))):
                raise ValueError("original action/trace/query differ in float64 bits, including signed zero")
    initial_ref = result["finish_evidence"]["initial_observation"]
    initial = load_observation_artifact(run_dir, initial_ref)
    initial_hash = observation_sha256(initial)
    if queries[0]["observation_sha256"] != initial_hash:
        raise ValueError("step0 must bind the original live reset observation, not construction pixels")
    files = _source_files(run_dir, metadata, results, bank_path, bank)
    if file_sha(run_dir / "run.json") != SOURCE_SHA256["run"] or file_sha(bank_path) != SOURCE_SHA256["bank"]:
        raise ValueError("source identity changed while preparing the diagnostic plan")
    query_by_step = {q["observation_step"]: deepcopy(q) for q in queries if q["observation_step"] <= maximum}
    payload = {"schema_version": SCHEMA, "status": "plan_ready", "source_commit": SOURCE_COMMIT,
               "source_run": str(run_dir), "source_bank": str(bank_path), "run_id": RUN_ID,
               "episode_id": episode_id, "initial_state_index": 35, "max_action_steps": maximum,
               "maximum_snapshots": maximum + 1, "control_freq": 20,
               "source_sha256": deepcopy(SOURCE_SHA256), "source_files": files,
               "episode": episode, "environment_config": environment,
               "original_run_config_sha256": metadata["run_config_sha256"],
               "original_head_sha256": metadata["head_sha256"],
               "initial_observation": deepcopy(initial_ref), "initial_observation_sha256": initial_hash,
               "state_identity": _typed(state), "actions_identity": _typed(actions),
               "original_query_steps": list(query_by_step),
               "query_observation_sha256": {str(k): q["observation_sha256"] for k, q in query_by_step.items()},
               "prefix_ledger_sha256": canonical_hash({"trace": result["trace"][:maximum+1],
                                                      "actions": result["executed_actions"][:maximum]}),
               "comparison": deepcopy(COMPARISON), "begin_hold_allowed": False,
               "vla_forward_calls": 0, "head_inference_calls": 0, "processor_calls": 0,
               "notice": "File-only plan; no native/model calls, new release labels, score or stopping-capability claim."}
    context = {"metadata": metadata, "episode": episode, "source_result": result,
               "environment_config": environment, "actions": actions, "query_by_step": query_by_step,
               "trace": deepcopy(result["trace"][:maximum+1]), "initial_observation": initial,
               "initial_observation_sha256": initial_hash, "state": state}
    return payload, context


def _outside(out, roots):
    for root in roots:
        root = Path(root).resolve()
        if out == root or out.is_relative_to(root):
            raise ValueError("diagnostic output must be outside every protected source tree")


def _manifest(directory):
    return {"schema_version": FILE_MANIFEST_SCHEMA,
            "files": [{"path": name, "sha256": file_sha(directory / name),
                       "bytes": (directory / name).stat().st_size} for name in ("plan.json", "actions.npz")]}


def create_plan(source_run, episode_id=EPISODE_ID, max_action_steps=292, out=None):
    """Validate original files and exclusively create ``plan.json/actions.npz``."""
    if out is None:
        raise ValueError("a fresh output directory is required")
    output = Path(out).resolve()
    if output.exists():
        raise FileExistsError(output)
    payload, context = _inspect_sources(source_run, episode_id, max_action_steps)
    roots = [payload["source_run"], str(Path(payload["source_bank"]).parent)]
    _outside(output, roots)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "actions.npz").open("xb") as stream:
        np.savez_compressed(stream, actions=context["actions"])
    payload.update(protected_roots=[*roots, str(output)],
                   actions_artifact={"path": "actions.npz", "sha256": file_sha(output / "actions.npz"),
                                     "dtype": payload["actions_identity"]["dtype"],
                                     "shape": payload["actions_identity"]["shape"],
                                     "array_sha256": payload["actions_identity"]["sha256"]})
    payload["plan_sha256"] = canonical_hash(payload)
    write_json(output / "plan.json", payload)
    write_json(output / "manifest.json", _manifest(output))
    return deepcopy(payload)


def load_plan(plan_path):
    """Revalidate all files and return a fresh, execution-ready read-only context."""
    path = Path(plan_path).resolve()
    if path.name != "plan.json" or read_json(path.parent / "manifest.json") != _manifest(path.parent):
        raise ValueError("diagnostic plan file manifest differs from plan.json/actions.npz")
    saved = read_json(path)
    if (saved.get("schema_version") != SCHEMA or saved.get("status") != "plan_ready"
            or saved.get("plan_sha256") != canonical_hash({k:v for k,v in saved.items() if k != "plan_sha256"})):
        raise ValueError("diagnostic plan schema/hash is invalid")
    for ref in saved.get("source_files", []):
        target = Path(ref["path"])
        if not target.is_absolute() or not target.is_file() or file_sha(target) != ref["sha256"] or target.stat().st_size != ref["bytes"]:
            raise ValueError("frozen diagnostic source file bytes changed")
    rebuilt, context = _inspect_sources(saved["source_run"], saved["episode_id"], saved["max_action_steps"])
    roots = [rebuilt["source_run"], str(Path(rebuilt["source_bank"]).parent)]
    _outside(path.parent, roots)
    reference = saved.get("actions_artifact", {})
    if reference.get("path") != "actions.npz":
        raise ValueError("diagnostic action archive path differs")
    archive = _contained(path.parent, reference["path"])
    if file_sha(archive) != reference.get("sha256"):
        raise ValueError("diagnostic action archive SHA256 differs")
    with np.load(archive, allow_pickle=False) as stored:
        if stored.files != ["actions"]:
            raise ValueError("diagnostic action archive must contain only actions")
        actions = stored["actions"]
    if actions.dtype != np.dtype("<f8") or not _same_bits(actions, context["actions"]):
        raise ValueError("diagnostic actions must preserve original finite float64 bits")
    if reference != {"path": "actions.npz", "sha256": file_sha(archive),
                     "dtype": rebuilt["actions_identity"]["dtype"],
                     "shape": rebuilt["actions_identity"]["shape"],
                     "array_sha256": rebuilt["actions_identity"]["sha256"]}:
        raise ValueError("diagnostic action archive metadata differs")
    rebuilt.update(protected_roots=[*roots, str(path.parent)], actions_artifact=deepcopy(reference))
    rebuilt["plan_sha256"] = canonical_hash(rebuilt)
    if rebuilt != saved:
        raise ValueError("diagnostic plan payload differs from revalidated original inputs")
    context["plan"] = deepcopy(saved)
    context["actions"] = actions
    for array in (context["actions"], context["state"]):
        array.setflags(write=False)
    return context
