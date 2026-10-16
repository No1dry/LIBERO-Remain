"""Synthetic file/CPU evidence, never native replay, model or video validation."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from benchmark.remaining_goals.finish import release_audit_plan as p
from benchmark.remaining_goals.finish import workflow as w
from benchmark.remaining_goals.finish.evidence import FinishEvidence
from benchmark.remaining_goals.finish.runner import run_finish_episode
from tests.test_finish_runner import inputs, observation
from tests.test_finish_workflow import actual_plan_files, FakeEnv, FakePolicy, tree_bytes


def _rehash(value, field):
    value.pop(field, None)
    value[field] = w.canonical_hash(value)


def _rewrite_plan(output, plan):
    _rehash(plan, "plan_sha256")
    w.write_json(output / "plan.json", plan, update=True)
    w.write_json(output / "manifest.json", {
        "schema_version": p.FILE_MANIFEST_SCHEMA,
        "files": [{"path": name, "sha256": w.file_sha(output / name),
                   "bytes": (output / name).stat().st_size} for name in ("plan.json", "actions.npz")]}, update=True)


def authorize_fixture(monkeypatch, run):
    """Only tests replace the immutable reviewed-source constants, never validators."""
    metadata = w.read_json(run / "run.json")
    bank_path = Path(metadata["plan"]["source_path"])
    episode = metadata["episodes"][0]
    monkeypatch.setattr(p, "SOURCE_SHA256", {
        "run": w.file_sha(run / "run.json"), "raw": w.file_sha(run / "raw/0000.json"),
        "bank": w.file_sha(bank_path), "state": w.file_sha(bank_path.parent / episode["state_path"]),
        "model_xml": episode["model_xml_sha256"], "bddl": episode["bddl_sha256"],
    })


def make_source(tmp_path, monkeypatch, *, two_domains=False):
    """Synthetic full H520/W150 sources using real historical file validators.

    Geometry/state and MP4 bytes are explicitly fake. No validator, model loader,
    or simulator is patched; only the reviewed-source SHA constants are replaced.
    This common helper is also used by the independent diagnostic-loop tests.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    if two_domains:
        from tests.test_finish_workflow_domains import fixture
        config, _, _ = fixture(tmp_path)
        bank_dir = Path(config["source"]["manifest"]).parent
    else:
        config, bank_dir = actual_plan_files(tmp_path)
    bank_path = bank_dir / "normal_bank.json"
    bank = w.read_json(bank_path)
    preparation_path = bank_dir / bank["preparations"][0]["path"]
    preparation = w.read_json(preparation_path)
    old = preparation_path.parent / preparation["episode"]["state_path"]
    renamed = preparation_path.parent / "states/basket_s035_00.npy"
    old.rename(renamed)
    preparation["episode"].update(suite="libero_10", state_path="states/basket_s035_00.npy")
    w.write_json(preparation_path, preparation, update=True)
    bank["preparations"][0]["sha256"] = w.file_sha(preparation_path)
    bank["episodes"][0].update(suite="libero_10", state_path=p.STATE_PATH)
    _rehash(bank, "content_hash")
    w.write_json(bank_path, bank, update=True)
    frozen = w.dry_plan(config)
    metadata = {"schema_version": w.RUN_SCHEMA, "protocol_version": frozen["protocol_version"],
                "run_id": p.RUN_ID, "run_config_sha256": frozen["plan_sha256"],
                **{key: deepcopy(frozen[key]) for key in w._identity_fields(frozen)},
                "plan": frozen, "status": "completed", "results": [], "missing": [],
                "error": None, "synthetic": True}
    if two_domains:
        metadata["schema_version"] = w.RUN_SCHEMA_V2
    class Policy(FakePolicy):
        def predict(self, obs, instruction):
            value = super().predict(obs, instruction)
            value["head_identity"]["artifact_sha256"] = frozen["head_sha256"]
            # Preserve a distinguishing signed zero through JSON/NPZ.
            value["candidate_actions"][0, 6] = -0.0
            return value
    run = tmp_path / "source_run"
    run.mkdir()
    for number, episode in enumerate(frozen["episodes"]):
        key = f"{number:04d}"
        result = run_finish_episode(FakeEnv(), Policy(), episode, mode="shadow", **frozen["configuration"])
        assert result["status"] == "completed", result.get("error")
        evidence = FinishEvidence(run / "evidence" / key, w.evidence_identity(metadata, episode))
        evidence.begin_episode(episode, mode="shadow", configuration=frozen["configuration"])
        evidence.capture_initial(observation(0))
        for query in result["queries"]:
            query["input_evidence"] = evidence.capture_query(query["sequence"], inputs(query["observation_step"]), query["head_identity"])
        result["finish_evidence"] = evidence.finish(result)
        video = run / "videos" / (key + ".mp4")
        video.parent.mkdir(exist_ok=True)
        video.write_bytes(b"SYNTHETIC-NOT-MP4: file hash fixture only")
        result["video"] = {"status": "saved", "path": f"videos/{key}.mp4", "sha256": w.file_sha(video), "synthetic": True}
        relative = f"raw/{key}.json"
        w.write_json(run / relative, result)
        metadata["results"].append({"episode_id": episode["episode_id"], "path": relative,
                                    "sha256": w.file_sha(run / relative), "validation": {"status": "checked"}})
    w.write_json(run / "run.json", metadata)
    authorize_fixture(monkeypatch, run)
    return run


def rewrite_raw(run, change):
    raw = w.read_json(run / "raw/0000.json")
    change(raw)
    w.write_json(run / "raw/0000.json", raw, update=True)
    metadata = w.read_json(run / "run.json")
    metadata["results"][0]["sha256"] = w.file_sha(run / "raw/0000.json")
    w.write_json(run / "run.json", metadata, update=True)


@pytest.fixture
def source(tmp_path, monkeypatch):
    return make_source(tmp_path / "inputs", monkeypatch)


def test_plan_roundtrip_exact_float64_prefix_and_actual_query_boundaries(source, tmp_path):
    before = tree_bytes(source.parent)
    output = tmp_path / "plan"
    plan = p.create_plan(source, p.EPISODE_ID, 292, output)
    loaded = p.load_plan(output / "plan.json")
    assert loaded["plan"] == plan and plan["status"] == "plan_ready"
    assert loaded["actions"].shape == (292, 7) and loaded["actions"].dtype == np.float64
    assert not loaded["actions"].flags.writeable and not loaded["state"].flags.writeable
    assert np.signbit(loaded["actions"][0, 6])
    assert set(loaded["query_by_step"]) == set(range(0, 289, 8)) and 292 not in loaded["query_by_step"]
    assert loaded["trace"][-1]["query_sequence"] == 37
    assert loaded["trace"][-1]["chunk_index"] == 3
    assert len(loaded["trace"]) == 293 and loaded["trace"][-1]["step"] == 292
    assert plan["maximum_snapshots"] == 293 and plan["begin_hold_allowed"] is False
    assert plan["source_bank"].endswith("normal_bank.json")
    manifest = w.read_json(output / "manifest.json")
    assert {entry["path"] for entry in manifest["files"]} == {"plan.json", "actions.npz"}
    assert plan["protected_roots"] == [str(source.resolve()), str(Path(plan["source_bank"]).parent), str(output.resolve())]
    assert loaded["initial_observation_sha256"] == loaded["query_by_step"][0]["observation_sha256"]
    assert tree_bytes(source.parent) == before
    roles = {role for ref in plan["source_files"] for role in ref["roles"]}
    assert roles == {"source_run", "raw_result", "execution_evidence", "live_initial_observation", "actual_query_inputs",
                     "actual_query_crop", "original_video", "normal_bank", "normal_preparation", "settled_state",
                     "construction_initial_observation", "normal_technical_audit"}


def test_actual_two_domain_registry_bank_and_run_roundtrip(tmp_path, monkeypatch):
    source = make_source(tmp_path / "v2_inputs", monkeypatch, two_domains=True)
    before = tree_bytes(source.parent)
    output = tmp_path / "plan"
    plan = p.create_plan(source, p.EPISODE_ID, 292, output)
    context = p.load_plan(output / "plan.json")
    metadata, episode = context["metadata"], context["episode"]
    bank = w.read_json(plan["source_bank"])
    assert metadata["schema_version"] == w.RUN_SCHEMA_V2
    assert bank["schema_version"] == w.BANK_SCHEMA_V2
    assert len(metadata["episodes"]) == len(metadata["results"]) == 5
    assert [ep["initial_state_index"] for ep in metadata["episodes"]] == list(range(35, 40))
    assert metadata["source_identity"] == bank["source_identity"]
    assert metadata["plan"]["source_registry"] == bank["source_registry"]
    assert episode["eval_source"] == metadata["eval_members"][0]
    assert episode["eval_source"]["initial_state_index"] == 35
    assert episode["eval_source"]["role"] == "normal_calibration"
    assert episode["eval_source"]["source_key"].startswith("init:")
    assert "eval_source" not in bank["episodes"][0]
    assert {key: value for key, value in episode.items() if key != "eval_source"} == bank["episodes"][0]
    assert sum("settled_state" in ref["roles"] for ref in plan["source_files"]) == 15
    assert sum("original_video" in ref["roles"] for ref in plan["source_files"]) == 5
    assert sum("actual_query_inputs" in ref["roles"] for ref in plan["source_files"]) == 330
    assert context["actions"].shape == (292, 7) and 292 not in context["query_by_step"]
    assert tree_bytes(source.parent) == before


@pytest.mark.parametrize("steps", [1, 8, 291])
def test_shorter_authorized_prefix_keeps_exact_boundary(source, tmp_path, steps):
    plan = p.create_plan(source, p.EPISODE_ID, steps, tmp_path / "plan")
    assert plan["max_action_steps"] == steps and plan["maximum_snapshots"] == steps + 1
    assert plan["original_query_steps"] == list(range(0, steps + 1, 8))


@pytest.mark.parametrize("steps", [0, -1, 293, 296, 520, True, 292.0, "292"])
def test_budget_rejected_before_source_access(tmp_path, steps):
    with pytest.raises(ValueError, match="1..292"):
        p.create_plan(tmp_path / "absent", p.EPISODE_ID, steps, tmp_path / "plan")
    assert not (tmp_path / "plan").exists()


@pytest.mark.parametrize("episode", ["basket_s036_00", "basket_s035_11", "basket_s037_00", 35, None])
def test_only_exact_authorized_episode(tmp_path, episode):
    with pytest.raises(ValueError, match="only basket_s035_00"):
        p.create_plan(tmp_path / "absent", episode, 292, tmp_path / "plan")


@pytest.mark.parametrize("target", ["run.json", "raw/0000.json", "evidence/0000/query_0001.npz", "videos/0000.mp4"])
def test_source_file_mutation_rejected_before_and_after_plan(source, tmp_path, target):
    p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")
    file = source / target
    file.write_bytes(file.read_bytes() + b"altered")
    with pytest.raises(ValueError):
        p.load_plan(tmp_path / "plan/plan.json")
    with pytest.raises(ValueError):
        p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "second")
    assert not (tmp_path / "second").exists()


@pytest.mark.parametrize("relative", ["normal_bank.json", "sources/035/preparation.json", p.STATE_PATH,
                                      "sources/035/initial.npz", "sources/035/audit.json"])
def test_bank_closure_is_frozen(source, tmp_path, relative):
    plan = p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")
    file = Path(plan["source_bank"]).parent / relative
    file.write_bytes(file.read_bytes() + b"mutation")
    with pytest.raises(ValueError, match="source file bytes changed"):
        p.load_plan(tmp_path / "plan/plan.json")


@pytest.mark.parametrize("kind", ["float32", "signed_zero", "nan", "extra_array", "reordered"])
def test_rehashed_action_archive_cannot_change_original_bits(source, tmp_path, kind):
    output = tmp_path / "plan"
    plan = p.create_plan(source, p.EPISODE_ID, 292, output)
    with np.load(output / "actions.npz", allow_pickle=False) as archive:
        actions = archive["actions"]
    extra = {}
    if kind == "float32":
        actions = actions.astype(np.float32)
    elif kind == "signed_zero":
        actions[0, 6] = 0.0
    elif kind == "nan":
        actions[0, 1] = np.nan
    elif kind == "extra_array":
        extra["unapproved"] = np.zeros(1)
    else:
        actions[[0, 1]] = actions[[1, 0]]
    np.savez_compressed(output / "actions.npz", actions=actions, **extra)
    plan["actions_artifact"]["sha256"] = w.file_sha(output / "actions.npz")
    _rewrite_plan(output, plan)
    with pytest.raises(ValueError):
        p.load_plan(output / "plan.json")


def test_signed_zero_difference_in_original_query_ledger_rejected(source, tmp_path, monkeypatch):
    rewrite_raw(source, lambda raw: raw["queries"][0]["candidate_actions"][0].__setitem__(6, 0.0))
    authorize_fixture(monkeypatch, source)
    # Reuse the historical ledger's bit comparison, not Python's -0.0 == 0.0.
    with pytest.raises(ValueError, match="unmodified candidate prefix"):
        p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")


@pytest.mark.parametrize("kind", ["phase", "query_step", "action_order"])
def test_bad_source_execution_ledger_rejected_even_with_test_sha_authorization(source, tmp_path, monkeypatch, kind):
    def change(raw):
        if kind == "phase":
            raw["executed_actions"][0]["action_kind"] = "hold"
        elif kind == "query_step":
            raw["queries"][36]["observation_step"] = 292
        else:
            raw["executed_actions"][0], raw["executed_actions"][1] = raw["executed_actions"][1], raw["executed_actions"][0]
    rewrite_raw(source, change)
    authorize_fixture(monkeypatch, source)
    with pytest.raises(ValueError):
        p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")


def test_output_never_overwrites_or_enters_original_trees(source, tmp_path):
    plan = p.create_plan(source, p.EPISODE_ID, 1, tmp_path / "plan")
    with pytest.raises(FileExistsError):
        p.create_plan(source, p.EPISODE_ID, 1, tmp_path / "plan")
    for output in (source / "new_diagnostic", Path(plan["source_bank"]).parent / "new_diagnostic"):
        with pytest.raises(ValueError, match="outside"):
            p.create_plan(source, p.EPISODE_ID, 1, output)
        assert not output.exists()


def test_plan_rehash_cannot_replace_source_identity_or_budget(source, tmp_path):
    output = tmp_path / "plan"
    plan = p.create_plan(source, p.EPISODE_ID, 292, output)
    plan["source_sha256"]["state"] = "0" * 64
    _rewrite_plan(output, plan)
    with pytest.raises(ValueError, match="payload differs"):
        p.load_plan(output / "plan.json")


@pytest.mark.parametrize("kind", ["index", "xml", "bddl", "bank"])
def test_alternate_fixed_identity_is_rejected(source, tmp_path, monkeypatch, kind):
    if kind == "bank":
        fake = dict(p.SOURCE_SHA256, bank="0" * 64)
        monkeypatch.setattr(p, "SOURCE_SHA256", fake)
    else:
        metadata = w.read_json(source / "run.json")
        key, value = {"index": ("initial_state_index", 36), "xml": ("model_xml_sha256", "0"*64),
                      "bddl": ("bddl_sha256", "0"*64)}[kind]
        metadata["episodes"][0][key] = value
        metadata["plan"]["episodes"][0][key] = value
        _rehash(metadata["plan"], "plan_sha256")
        metadata["run_config_sha256"] = metadata["plan"]["plan_sha256"]
        w.write_json(source / "run.json", metadata, update=True)
        monkeypatch.setattr(p, "SOURCE_SHA256", dict(p.SOURCE_SHA256, run=w.file_sha(source / "run.json")))
    with pytest.raises(ValueError):
        p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")


def test_original_official_or_post_audit_state_cannot_replace_settled_base(source, tmp_path, monkeypatch):
    metadata = w.read_json(source / "run.json")
    bank_path = Path(metadata["plan"]["source_path"])
    bank = w.read_json(bank_path)
    state_path = bank_path.parent / p.STATE_PATH
    # A newly saved arbitrary state is not the original settled base, even if
    # its shape/dtype and index are identical and the caller rehashes the bank.
    np.save(state_path, np.array([2., -0., 35.]), allow_pickle=False)
    bank["episodes"][0]["state_sha256"] = w.file_sha(state_path)
    _rehash(bank, "content_hash")
    w.write_json(bank_path, bank, update=True)
    with pytest.raises(ValueError):
        p.create_plan(source, p.EPISODE_ID, 292, tmp_path / "plan")


def test_plan_file_manifest_is_required_and_checked(source, tmp_path):
    output = tmp_path / "plan"
    p.create_plan(source, p.EPISODE_ID, 1, output)
    manifest = w.read_json(output / "manifest.json")
    manifest["files"][0]["bytes"] += 1
    w.write_json(output / "manifest.json", manifest, update=True)
    with pytest.raises(ValueError, match="file manifest"):
        p.load_plan(output / "plan.json")


def test_uncalibrated_source_needs_no_current_head_or_model_assets(source, tmp_path):
    # Diagnosis consumes the frozen raw evidence, not current head/runtime paths
    # or calibration readiness. These deliberately invalid bytes are not read.
    for file in (source.parent / "head/head.json", source.parent / "head/head.npz", source.parent / "runtime.json"):
        file.write_bytes(b"removed model resource; diagnostics must not read this")
    w.write_json(source / "calibration.json", {"status": "capability_not_established", "calibrated": False})
    plan = p.create_plan(source, p.EPISODE_ID, 1, tmp_path / "plan")
    assert plan["vla_forward_calls"] == plan["head_inference_calls"] == plan["processor_calls"] == 0
    assert not any("head.json" in ref["path"] or "head.npz" in ref["path"] for ref in plan["source_files"])


def test_file_only_plan_and_load_forbid_native_model_imports(source, tmp_path):
    script = '''
import importlib.abc,json,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','libero','robosuite','mujoco','transformers'}:
            raise AssertionError('forbidden heavy import: '+fullname)
sys.meta_path.insert(0,Block())
from benchmark.remaining_goals.finish import release_audit_plan as p
p.SOURCE_SHA256=json.loads(sys.argv[3])  # explicitly synthetic test authorization
p.create_plan(sys.argv[1],p.EPISODE_ID,292,sys.argv[2])
context=p.load_plan(sys.argv[2]+'/plan.json')
print(context['actions'].shape)
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(source), str(tmp_path / "plan"), json.dumps(p.SOURCE_SHA256)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "(292, 7)" in result.stdout
