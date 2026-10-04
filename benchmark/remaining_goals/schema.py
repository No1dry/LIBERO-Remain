"""JSON manifest contract for the remaining-goals benchmark.

Validation checks declarations, grouping, provenance and file integrity.  In
particular, ``construction.legal`` is a reviewed declaration, not proof of
physical feasibility or of the declared initial goal mask.  No model outcome
is used to admit or exclude an episode.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np


SCHEMA_VERSION = "remaining-goals-v0.1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LOGICAL_OPERATORS = {"and", "or", "not", "imply", "implies", "iff", "xor", "forall", "exists", "when"}
_TASK_FIELDS = ("suite", "libero_task_id", "task_name", "instruction", "goal_specs")
_GROUP_FIELDS = _TASK_FIELDS + ("horizon", "retention_steps", "initial_state_index", "split")


def _error(location: str, message: str) -> None:
    raise ValueError(f"{location}: {message}")


def _text(value: Any, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _error(location, "must be a non-empty string")


def _integer(value: Any, location: str, minimum: int | None = None) -> None:
    if type(value) is not int or (minimum is not None and value < minimum):
        suffix = f" >= {minimum}" if minimum is not None else ""
        _error(location, f"must be an integer{suffix} (booleans are not integers)")


def _json_value(value: Any, location: str) -> None:
    """Reject non-JSON values even in otherwise unknown extension fields."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _error(location, "JSON numbers must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_value(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _error(location, "JSON object keys must be strings")
            _json_value(item, f"{location}.{key}")
        return
    _error(location, f"must contain only JSON values, got {type(value).__name__}")


def manifest_hash(manifest: dict[str, Any]) -> str:
    """Hash all JSON content except the top-level ``content_hash`` field.

    Dictionary ordering is insignificant; episode/list ordering is significant.
    Unknown extension fields and nested fields named ``content_hash`` are hashed.
    """
    if not isinstance(manifest, dict):
        _error("manifest", "must be an object")
    payload = {key: value for key, value in manifest.items() if key != "content_hash"}
    _json_value(payload, "manifest")
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _state_path(raw: Any, base_dir: Path | None) -> Path:
    _text(raw, "state_path")
    windows = PureWindowsPath(raw)
    portable = PurePosixPath(raw.replace("\\", "/"))
    if windows.drive or windows.root or portable.is_absolute():
        _error("state_path", "must be relative to the manifest directory")
    if ".." in portable.parts or any(":" in part or part.endswith((" ", ".")) for part in portable.parts):
        _error("state_path", "parent traversal, Windows path aliases, and drive/stream syntax are forbidden")
    if "\x00" in raw or portable.suffix.lower() != ".npy":
        _error("state_path", "must name a .npy file")
    relative = Path(*portable.parts)
    if base_dir is None:
        return relative
    try:
        base = Path(base_dir).resolve()
        resolved = (base / relative).resolve()
        resolved.relative_to(base)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("state_path: resolved path escapes the manifest directory or is invalid") from exc
    return resolved


def verify_state_file(episode: dict[str, Any], base_dir: Path) -> Path:
    """Verify a contained .npy file's SHA-256 and finite, non-empty 1-D state.

    Hashing and decoding use the same bytes.  Pickle/object arrays and complex or
    non-numeric state arrays are rejected; no LIBERO installation is required.
    """
    if not isinstance(episode, dict):
        _error("episode", "must be an object")
    path = _state_path(episode.get("state_path"), base_dir)
    digest = episode.get("state_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        _error("state_sha256", "must be a lowercase SHA-256 hex digest")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"state_path: cannot read state file {path}") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        _error("state_sha256", f"digest mismatch for {path}")
    try:
        state = np.load(io.BytesIO(raw), allow_pickle=False)
    except (OSError, ValueError, TypeError, EOFError) as exc:
        raise ValueError(f"state_path: invalid non-pickled NumPy state file {path}") from exc
    if not isinstance(state, np.ndarray):
        if hasattr(state, "close"):
            state.close()
        _error("state_path", "must contain a single NumPy array, not an archive")
    if state.ndim != 1 or state.size == 0 or state.dtype.kind not in "fiu":
        _error("state_path", "state must be a non-empty one-dimensional real numeric array")
    if not np.isfinite(state).all():
        _error("state_path", "state must contain only finite values")
    return path


def _validate_goals(goals: Any, location: str) -> None:
    if not isinstance(goals, list) or len(goals) not in (2, 3):
        _error(location, "must contain exactly 2 or 3 goals")
    goal_ids: set[str] = set()
    for index, goal in enumerate(goals):
        here = f"{location}[{index}]"
        if not isinstance(goal, dict):
            _error(here, "must be an object")
        _text(goal.get("id"), f"{here}.id")
        _text(goal.get("language"), f"{here}.language")
        if goal["id"] in goal_ids:
            _error(here, "goal id must be unique within the task")
        goal_ids.add(goal["id"])
        predicates = goal.get("predicates")
        if not isinstance(predicates, list) or not predicates:
            _error(f"{here}.predicates", "must be a non-empty conjunction of atomic predicates")
        for pred_index, predicate in enumerate(predicates):
            where = f"{here}.predicates[{pred_index}]"
            if not isinstance(predicate, list) or not predicate:
                _error(where, "must be a non-empty flat list of string tokens")
            for token in predicate:
                _text(token, where)
                if any(char.isspace() or char in "()" for char in token):
                    _error(where, "predicate tokens cannot contain whitespace or parentheses")
            if predicate[0].casefold() in _LOGICAL_OPERATORS:
                _error(where, "only positive atomic predicates are supported; no logical operators")


def validate_manifest(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
    check_files: bool = False,
    require_complete_masks: bool = True,
    allow_unreviewed: bool = False,
) -> None:
    """Validate structure, complete paired masks, provenance, and optional files.

    ``require_complete_masks=False`` permits partial groups for construction
    tooling, but never duplicate masks, inconsistent task mappings, or split
    leakage.  Evaluation loaders require complete groups.  Extra JSON fields
    are allowed and participate in the manifest hash.
    """
    if not isinstance(manifest, dict):
        _error("manifest", "must be an object")
    _json_value(manifest, "manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        _error("schema_version", f"must be {SCHEMA_VERSION!r}")
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        _error("environment", "must be an object")
    if environment.get("name") not in ("libero", "toy"):
        _error("environment.name", "must be 'libero' or 'toy'")
    _text(environment.get("fingerprint"), "environment.fingerprint")
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        _error("episodes", "must be a non-empty list")
    if check_files and base_dir is None:
        _error("base_dir", "is required when check_files=True")

    episode_ids: set[str] = set()
    task_definitions: dict[str, dict[str, Any]] = {}
    native_task_ids: dict[tuple[str, int], str] = {}
    groups: dict[tuple[str, str, str], tuple[dict[str, Any], set[tuple[bool, ...]]]] = {}
    source_splits: dict[str, str] = {}
    for index, episode in enumerate(episodes):
        here = f"episodes[{index}]"
        if not isinstance(episode, dict):
            _error(here, "must be an object")
        for field in ("episode_id", "task_id", "suite", "task_name", "instruction", "source_id", "pose_id"):
            _text(episode.get(field), f"{here}.{field}")
        if episode["episode_id"] in episode_ids:
            _error(f"{here}.episode_id", "must be unique")
        episode_ids.add(episode["episode_id"])
        for field in ("libero_task_id", "initial_state_index"):
            _integer(episode.get(field), f"{here}.{field}", 0)
        _integer(episode.get("seed"), f"{here}.seed")
        for field in ("horizon", "retention_steps"):
            _integer(episode.get(field), f"{here}.{field}", 1)
        if episode.get("split") not in ("train", "val", "test"):
            _error(f"{here}.split", "must be 'train', 'val', or 'test'")
        _validate_goals(episode.get("goal_specs"), f"{here}.goal_specs")
        mask = episode.get("initial_mask")
        if not isinstance(mask, list) or len(mask) != len(episode["goal_specs"]) or any(type(bit) is not bool for bit in mask):
            _error(f"{here}.initial_mask", "must contain one JSON boolean per goal")
        _state_path(episode.get("state_path"), base_dir)
        digest = episode.get("state_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            _error(f"{here}.state_sha256", "must be a lowercase SHA-256 hex digest")
        construction = episode.get("construction")
        if not isinstance(construction, dict):
            _error(f"{here}.construction", "must be an object")
        for field in ("method", "reviewed_by"):
            _text(construction.get(field), f"{here}.construction.{field}")
        if construction.get("legal") is not True and not (allow_unreviewed and construction.get("legal") is False):
            _error(f"{here}.construction.legal", "must be true to enter evaluation; this declaration does not prove feasibility")

        task_id = episode["task_id"]
        task_definition = {field: episode[field] for field in _TASK_FIELDS}
        if task_id in task_definitions and task_definitions[task_id] != task_definition:
            _error(here, f"task_id {task_id!r} has an inconsistent task definition")
        task_definitions[task_id] = task_definition
        native_id = (episode["suite"], episode["libero_task_id"])
        if native_id in native_task_ids and native_task_ids[native_id] != task_id:
            _error(here, f"native task mapping {native_id!r} has multiple task_id aliases")
        native_task_ids[native_id] = task_id

        group_key = (task_id, episode["source_id"], episode["pose_id"])
        group_definition = {field: episode[field] for field in _GROUP_FIELDS}
        if group_key not in groups:
            groups[group_key] = (group_definition, set())
        first, seen_masks = groups[group_key]
        if first != group_definition:
            _error(here, f"paired group {group_key!r} has inconsistent task, budget, index, or split")
        mask_tuple = tuple(mask)
        if mask_tuple in seen_masks:
            _error(here, f"paired group {group_key!r} has a duplicate mask {mask_tuple!r}")
        seen_masks.add(mask_tuple)

        donors = episode.get("donor_source_ids", [])
        if not isinstance(donors, list):
            _error(f"{here}.donor_source_ids", "must be a list of source IDs")
        for donor in donors:
            _text(donor, f"{here}.donor_source_ids")
        if len(set(donors)) != len(donors):
            _error(f"{here}.donor_source_ids", "must not contain duplicate source IDs")
        for source_id in [episode["source_id"], *donors]:
            split = episode["split"]
            if source_id in source_splits and source_splits[source_id] != split:
                _error(here, f"source {source_id!r} is shared across splits (including donor provenance)")
            source_splits[source_id] = split
        if check_files:
            verify_state_file(episode, Path(base_dir))

    if require_complete_masks:
        for group_key, (definition, seen_masks) in groups.items():
            expected = set(itertools.product((False, True), repeat=len(definition["goal_specs"])))
            if seen_masks != expected:
                missing = sorted(expected - seen_masks)
                _error("episodes", f"paired group {group_key!r} lacks complete masks; missing {missing!r}")
    if "content_hash" in manifest:
        content_hash = manifest["content_hash"]
        if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
            _error("content_hash", "must be a lowercase SHA-256 hex digest")
        if content_hash != manifest_hash(manifest):
            _error("content_hash", "digest mismatch; manifest content has changed")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _error("manifest", f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def load_manifest(path: Path, *, check_files: bool = True) -> dict[str, Any]:
    """Load a complete manifest and optionally verify all referenced states."""
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    validate_manifest(manifest, base_dir=path.parent, check_files=check_files)
    return manifest


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write validated JSON with a fresh content hash, without mutating input.

    State bytes need not exist yet.  ``load_manifest`` checks them by default;
    path containment is still checked here relative to the destination folder.
    """
    path = Path(path)
    payload = dict(manifest)
    payload["content_hash"] = manifest_hash(manifest)
    validate_manifest(payload, base_dir=path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
