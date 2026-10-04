"""Catalog selection and exact goal declarations, without importing LIBERO."""

from pathlib import Path
import re

import pytest

from benchmark.remaining_goals.task_catalog import TASKS, TASK_TRACKS, COMMON_TEN_TASKS, mask_order, select_tasks


def test_default_primary_suite_has_six_tasks_and_24_states_per_source():
    keys = select_tasks()
    assert len(keys) == 6
    assert {TASKS[key]["suite"] for key in keys} == {"libero_10"}
    assert sum(2 ** len(TASKS[key]["goals"]) for key in keys) == 24
    assert len(TASKS) == 11
    assert len(TASKS["two_pots"]["goals"]) == 3
    assert TASKS["two_pots"]["goals"][-1]["predicates"] == [["turnon", "flat_stove_1"]]
    assert TASKS["two_pots"]["requires_invariant_protocol"] is True
    assert TASKS["two_pots"]["invariant_predicates"] == [["turnon", "flat_stove_1"]]
    assert "two_pots" not in keys
    with pytest.raises(ValueError, match="requires invariant protocol"):
        select_tasks("two_pots")


def test_extensions_must_be_selected_explicitly_and_cannot_mix_suites():
    assert select_tasks("primary") == select_tasks("all")
    assert len(select_tasks("extension")) == 4
    assert set(select_tasks("extension")) == set(TASK_TRACKS["extension"]["tasks"])
    assert len(COMMON_TEN_TASKS) == len(set(COMMON_TEN_TASKS)) == 10
    assert set(COMMON_TEN_TASKS) == set(select_tasks("primary") + select_tasks("extension"))
    assert select_tasks("frypan_stove3,frypan_stove9") == ["frypan_stove3", "frypan_stove9"]
    assert select_tasks(["stove", "basket"]) == ["stove", "basket"]
    with pytest.raises(ValueError, match="mixed-suite"):
        select_tasks("basket,frypan_stove3")
    for invalid in ("", "unknown", "basket,basket", "all,stove", []):
        with pytest.raises(ValueError, match="distinct catalog keys"):
            select_tasks(invalid)


def test_mask_order_preserves_old_pairing_and_enumerates_three_goal_cube():
    assert mask_order(2) == ("00", "10", "01", "11")
    assert mask_order(3) == ("000", "100", "010", "110", "001", "101", "011", "111")
    for invalid in (True, 0, 1, 4, 2.5):
        with pytest.raises(ValueError, match="two or three"):
            mask_order(invalid)


@pytest.mark.parametrize("key", TASKS)
def test_catalog_edits_distinct_entities_and_keeps_object_supports_unchanged(key):
    profile = TASKS[key]
    predicates = [goal["predicates"][0] for goal in profile["goals"]]
    assert all(len(goal["predicates"]) == 1 for goal in profile["goals"])
    assert len({p[1] for p in predicates}) == len(predicates)
    assert not set(profile.get("object_supports", [])) & {p[1] for p in predicates}
    assert all(p[0] in ("in", "on", "turnon", "open", "close") for p in predicates)
    assert profile["selection_reason"]


@pytest.mark.parametrize("key", TASKS)
def test_goal_partition_matches_pinned_official_bddl_when_source_is_present(key):
    profile = TASKS[key]
    source = (Path(__file__).resolve().parents[1] / ".runtime" / "remaining_libero"
              / "LIBERO-8f1084e3132a39270c3a13ebe37270a43ece2a01" / "libero" / "libero" / "bddl_files")
    path = source / profile["suite"] / (profile["name"] + ".bddl")
    if not path.is_file():
        pytest.skip("optional pinned simulator sources are not installed")
    goal_text = path.read_text(encoding="utf-8").split("(:goal", 1)[1]
    official = []
    for flat in re.findall(r"\(([^()]+)\)", goal_text):
        words = flat.split()
        official.append((words[0].lower(), *words[1:]))
    declared = [tuple(p) for goal in profile["goals"] for p in goal["predicates"]]
    assert sorted(declared) == sorted(official)
