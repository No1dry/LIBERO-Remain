"""Pure execution selection over a complete, unchanged source manifest.

This layer validates the complete paired structure but neither reads state files
nor grants semantic/release approval. Runtime callers must still perform the
original source-file and replay checks. Oracle instructions are explicit
diagnostic metadata; source instructions and full goal specifications stay intact.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .schema import manifest_hash, validate_manifest


SCHEMA_VERSION = "remaining-goals-execution-selection-v1"
ORACLE_MODE = "oracle-remaining-initial"


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("execution selection must contain finite JSON values") from exc


def _text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_selection(manifest, *, masks=None, instruction_mode="original") -> dict:
    """Build a deterministic selection without changing or shortening the bank.

    ``masks`` is None/"all" or a nonempty list of unique binary strings present
    in this bank. Selected episodes retain source order, independent of mask
    argument order. The explicit oracle mode accepts only episodes with exactly
    one initially unfinished goal and at least one initially finished goal. Its
    effective instruction is that goal's existing catalog language, verbatim.
    Full-mask pairing is always validated, including unselected source episodes.
    ``legal=false`` is allowed for planning; it remains unchanged and unapproved.
    """
    validate_manifest(manifest, require_complete_masks=True, allow_unreviewed=True)
    episodes = manifest["episodes"]
    if len({episode["suite"] for episode in episodes}) != 1:
        raise ValueError("execution selection requires one suite; do not pool LIBERO suites")
    if instruction_mode not in ("original", ORACLE_MODE):
        raise ValueError("instruction_mode must be original or oracle-remaining-initial")
    available = {"".join("1" if value else "0" for value in episode["initial_mask"]) for episode in episodes}
    if masks is None or masks == "all":
        normalized_masks, wanted = "all", available
    else:
        if not isinstance(masks, list) or not masks:
            raise ValueError("masks must be 'all' or a nonempty list of binary mask strings")
        if any(not isinstance(mask, str) or not mask or set(mask) - {"0", "1"} for mask in masks):
            raise ValueError("masks must contain binary strings")
        if len(set(masks)) != len(masks):
            raise ValueError("duplicate requested masks are not allowed")
        if not set(masks) <= available:
            raise ValueError("requested masks are absent from the complete source bank")
        normalized_masks, wanted = list(masks), set(masks)
    selected, not_selected, instructions = [], [], []
    for episode in episodes:
        identifier = episode["episode_id"]
        initial = episode["initial_mask"]
        mask = "".join("1" if value else "0" for value in initial)
        if mask not in wanted:
            not_selected.append(identifier)
            continue
        original = episode["instruction"]
        effective = original
        if instruction_mode == ORACLE_MODE:
            remaining = [index for index, value in enumerate(initial) if not value]
            if len(remaining) != 1 or not any(initial):
                raise ValueError("oracle-remaining-initial requires exactly one remaining goal; no normal/all-complete cases")
            effective = episode["goal_specs"][remaining[0]]["language"]
        selected.append(identifier)
        instructions.append({"episode_id": identifier, "original_instruction": original,
                             "original_instruction_sha256": _text_hash(original),
                             "effective_instruction": effective,
                             "effective_instruction_sha256": _text_hash(effective)})
    selection = {"schema_version": SCHEMA_VERSION,
                 "purpose": "oracle-remaining-initial-diagnostic" if instruction_mode == ORACLE_MODE else "remaining-goals-subset-pilot",
                 "manifest_hash": manifest_hash(manifest), "masks": normalized_masks,
                 "instruction_mode": instruction_mode, "source_expected": len(episodes),
                 "selected_ids": selected, "not_selected_ids": not_selected,
                 "expected": len(selected), "episodes": instructions}
    selection["selection_sha256"] = _text_hash(_canonical(selection))
    return selection


def validate_selection(manifest, selection) -> dict:
    """Rebuild and strictly compare every declaration, type and digest.

    Returns an independent canonical copy. No unknown metadata or alternate
    instruction may be smuggled in under a previously valid selection digest.
    """
    if not isinstance(selection, dict):
        raise ValueError("execution_selection must be an object")
    supplied = _canonical(selection)
    expected = build_selection(manifest, masks=selection.get("masks"),
                               instruction_mode=selection.get("instruction_mode"))
    if supplied != _canonical(expected):
        raise ValueError("execution selection differs from its complete source manifest or canonical plan")
    return expected


def selected_episodes(manifest, metadata=None) -> list[dict]:
    """Return untouched source episode copies selected by run metadata.

    An absent execution_selection preserves the legacy all-episode interface;
    its caller remains responsible for the existing manifest validation. An
    explicitly present selection is always rebuilt against the full bank.
    """
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("run metadata must be an object")
    if metadata is None or "execution_selection" not in metadata:
        if not isinstance(manifest, dict) or not isinstance(manifest.get("episodes"), list):
            raise ValueError("manifest episodes must be a list")
        return deepcopy(manifest["episodes"])
    selection = validate_selection(manifest, metadata["execution_selection"])
    wanted = set(selection["selected_ids"])
    return [deepcopy(episode) for episode in manifest["episodes"] if episode["episode_id"] in wanted]
