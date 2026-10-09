"""Pure selection tests over complete synthetic banks; no simulator/model calls."""
from copy import deepcopy
import hashlib
import itertools

import pytest

from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.selection import build_selection, selected_episodes, validate_selection


def make_manifest(*, sources=2, goals=2):
    specs = [{"id": f"goal{index}", "language": f"put object {index} in the basket",
              "predicates": [["In", f"object{index}", "basket"]]} for index in range(goals)]
    episodes = []
    for source in range(sources):
        for initial in itertools.product((False, True), repeat=goals):
            mask = "".join("1" if value else "0" for value in initial)
            identifier = f"basket_s{source:03d}_{mask}"
            episodes.append({"episode_id": identifier, "task_id": "basket", "suite": "toy",
                             "libero_task_id": 0, "task_name": "synthetic_basket", "seed": 7,
                             "initial_state_index": source, "source_id": f"source{source}", "pose_id": "base",
                             "instruction": "  Put both objects in the basket. 保留原文。  ",
                             "goal_specs": deepcopy(specs), "initial_mask": list(initial),
                             "horizon": 2, "retention_steps": 2, "split": "val",
                             "state_path": f"states/{identifier}.npy", "state_sha256": "a" * 64,
                             "construction": {"legal": False, "method": "synthetic", "reviewed_by": "test fixture only"}})
    manifest = {"schema_version": "remaining-goals-v0.1", "environment": {"name": "toy", "fingerprint": "synthetic"},
                "episodes": episodes}
    manifest["content_hash"] = manifest_hash(manifest)
    return manifest


def test_subset_preserves_whole_bank_and_source_order_without_policy_filtering():
    manifest = make_manifest()
    before = deepcopy(manifest)
    selection = build_selection(manifest, masks=["11", "10", "01"])
    expected = [episode for episode in manifest["episodes"] if any(episode["initial_mask"])]
    assert selection["expected"] == 6 and selection["source_expected"] == 8
    assert selection["selected_ids"] == [episode["episode_id"] for episode in expected]
    assert selection["not_selected_ids"] == ["basket_s000_00", "basket_s001_00"]
    assert selection["manifest_hash"] == manifest_hash(manifest)
    assert selection["instruction_mode"] == "original"
    assert selection["purpose"] == "remaining-goals-subset-pilot"
    assert manifest == before and all(episode["construction"]["legal"] is False for episode in manifest["episodes"])
    for row, episode in zip(selection["episodes"], expected):
        assert row["original_instruction"] == row["effective_instruction"] == episode["instruction"]
        digest = hashlib.sha256(episode["instruction"].encode("utf-8")).hexdigest()
        assert row["original_instruction_sha256"] == row["effective_instruction_sha256"] == digest
    assert validate_selection(manifest, selection) == selection


def test_all_aliases_are_deterministic_and_legacy_extraction_is_independent():
    manifest = make_manifest()
    implicit = build_selection(manifest)
    assert implicit == build_selection(manifest, masks="all")
    assert implicit["masks"] == "all" and implicit["expected"] == 8
    assert implicit["not_selected_ids"] == []
    episodes = selected_episodes(manifest, {})
    assert episodes == manifest["episodes"]
    episodes[0]["instruction"] = "mutated caller copy"
    assert manifest["episodes"][0]["instruction"] != "mutated caller copy"


def test_oracle_uses_only_initially_remaining_catalog_goal_without_mutating_source():
    manifest = make_manifest()
    before = deepcopy(manifest)
    selection = build_selection(manifest, masks=["10", "01"], instruction_mode="oracle-remaining-initial")
    chosen = selected_episodes(manifest, {"execution_selection": selection})
    assert selection["purpose"] == "oracle-remaining-initial-diagnostic" and selection["expected"] == 4
    for row, episode in zip(selection["episodes"], chosen):
        remaining = episode["initial_mask"].index(False)
        assert row["effective_instruction"] == episode["goal_specs"][remaining]["language"]
        assert episode["instruction"] == row["original_instruction"]
        assert len(episode["goal_specs"]) == 2
        assert row["effective_instruction_sha256"] == hashlib.sha256(row["effective_instruction"].encode()).hexdigest()
    chosen[0]["goal_specs"][0]["language"] = "caller mutation"
    assert manifest == before


@pytest.mark.parametrize("masks", [[], ["10", "10"], ["2"], [""], [10], [True], ["101"], "10", 10, {}])
def test_bad_mask_requests_are_rejected(masks):
    with pytest.raises(ValueError):
        build_selection(make_manifest(), masks=masks)


@pytest.mark.parametrize("masks", ["all", ["00"], ["11"], ["10", "11"]])
def test_oracle_rejects_normal_or_all_finished_cases(masks):
    with pytest.raises(ValueError, match="exactly one remaining"):
        build_selection(make_manifest(), masks=masks, instruction_mode="oracle-remaining-initial")


def test_three_goal_oracle_requires_exactly_one_remaining_goal():
    manifest = make_manifest(goals=3, sources=1)
    selection = build_selection(manifest, masks=["110"], instruction_mode="oracle-remaining-initial")
    assert selection["episodes"][0]["effective_instruction"] == "put object 2 in the basket"
    with pytest.raises(ValueError, match="exactly one remaining"):
        build_selection(manifest, masks=["100"], instruction_mode="oracle-remaining-initial")


def test_selection_still_validates_unselected_00_and_complete_source_pairing():
    manifest = make_manifest(sources=1)
    manifest["episodes"] = [row for row in manifest["episodes"] if any(row["initial_mask"])]
    manifest.pop("content_hash")
    with pytest.raises(ValueError, match="complete masks"):
        build_selection(manifest, masks=["10", "01", "11"])
    manifest = make_manifest(sources=1)
    manifest["episodes"][0]["state_sha256"] = "invalid"
    manifest.pop("content_hash")
    with pytest.raises(ValueError, match="state_sha256"):
        build_selection(manifest, masks=["10"])


@pytest.mark.parametrize("tamper", ["expected_type", "duplicate_id", "omit_not_selected", "instruction",
                                    "manifest_hash", "selection_hash", "extra_field"])
def test_selection_rebuild_rejects_every_changed_declaration(tamper):
    manifest = make_manifest(sources=1)
    selection = build_selection(manifest, masks=["10"])
    if tamper == "expected_type":
        selection["expected"] = True  # Python equality alone would confuse True with 1.
    elif tamper == "duplicate_id":
        selection["selected_ids"].append(selection["selected_ids"][0])
    elif tamper == "omit_not_selected":
        selection["not_selected_ids"].pop()
    elif tamper == "instruction":
        selection["episodes"][0]["effective_instruction"] = "skip the completed object"
    elif tamper == "manifest_hash":
        selection["manifest_hash"] = "b" * 64
    elif tamper == "selection_hash":
        selection["selection_sha256"] = "c" * 64
    elif tamper == "extra_field":
        selection["helpful_mask_hint"] = [True, False]
    with pytest.raises(ValueError):
        validate_selection(manifest, selection)
    with pytest.raises(ValueError):
        selected_episodes(manifest, {"execution_selection": selection})


def test_selection_cannot_bind_same_ids_from_changed_source_bank():
    manifest = make_manifest()
    selection = build_selection(manifest, masks=["10"])
    other = deepcopy(manifest)
    for episode in other["episodes"]:
        episode["instruction"] = "different complete original instruction"
    other["content_hash"] = manifest_hash(other)
    with pytest.raises(ValueError):
        validate_selection(other, selection)


def test_unknown_mode_explicit_null_and_mixed_suite_are_rejected():
    manifest = make_manifest()
    with pytest.raises(ValueError):
        build_selection(manifest, instruction_mode="oracle-every-step")
    with pytest.raises(ValueError):
        selected_episodes(manifest, {"execution_selection": None})
    other = make_manifest(sources=1)
    for episode in other["episodes"]:
        episode.update(episode_id="other_" + episode["episode_id"], task_id="other-task", suite="libero_90")
    manifest["episodes"].extend(other["episodes"])
    manifest["content_hash"] = manifest_hash(manifest)
    with pytest.raises(ValueError, match="one suite"):
        build_selection(manifest, masks=["10"])
