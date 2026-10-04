"""Independent replay orchestration, with fake adapter and real audit logic."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals import replay_candidates as replay
from benchmark.remaining_goals.schema import manifest_hash
from benchmark.remaining_goals.validation import compare_observations
from benchmark.remaining_goals.observation_artifact import save_observation_artifact, load_observation_artifact


def observation(state):
    return {"agentview_image": np.full((2, 2, 3), int(state[2] * 10 + state[3] * 20), dtype=np.uint8),
            "robot0_joint_pos": np.array([state[1]])}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def pack(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    components = [{"goal_index": i, "indices": [i + 2], "values": [1.],
                   "values_sha256": hashlib.sha256(np.array([1.], dtype="<f8").tobytes()).hexdigest()}
                  for i in range(2)]
    manifest = {"schema_version": "remaining-goals-v0.1",
                "environment": {"name": "libero", "fingerprint": "frozen-runtime", "lock": {"control_freq": 20}},
                "episodes": []}
    for index, mask in enumerate(([False, False], [True, False], [False, True], [True, True])):
        state = np.array([0., .4, float(mask[0]), float(mask[1])])
        identifier = f"episode_{index}"
        state_path = root / "states" / f"{identifier}.npy"
        state_path.parent.mkdir(exist_ok=True)
        np.save(state_path, state)
        episode = {"episode_id": identifier, "task_id": "task", "suite": "libero_10", "libero_task_id": 0,
                   "task_name": "task", "instruction": "complete a and b", "source_id": "official_0", "pose_id": "fixed",
                   "goal_specs": [{"id": name, "language": f"put {name} in the basket",
                                   "predicates": [["in", name, "basket"]]} for name in ("a", "b")],
                   "initial_mask": mask, "initial_state_index": 0, "seed": 0, "split": "test",
                   "horizon": 10, "retention_steps": 2, "bddl_sha256": "a" * 64, "model_xml_sha256": "b" * 64,
                   "reference_robot_qpos": [.4], "state_path": state_path.relative_to(root).as_posix(),
                   "state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                   "construction": {"legal": False, "method": "joint matched components", "reviewed_by": "pending",
                                    "components_exactly_matched": True, "selected_components": deepcopy(components),
                                    "technical_audit": f"validation/{identifier}/audit.json"}}
        audit = {"technical_acceptance": True, "trace": [{"step": 0, "state": state.tolist(), "goals": mask,
                  "observation_check": compare_observations(observation(state), observation(state))}]}
        episode["initial_observation"] = save_observation_artifact(root, f"observations/{identifier}.npz", observation(state))
        write_json(root / episode["construction"]["technical_audit"], audit)
        manifest["episodes"].append(episode)
    path = root / "manifest.candidates.json"
    manifest["content_hash"] = manifest_hash(manifest)
    write_json(path, manifest)
    record = SimpleNamespace(instances=[], resets=[], steps=[], closed=False, stale_image=False, rgb_rounding=False,
                             tiny_proprio=False, signed_zero_state=False,
                             bad_restore=False, fail_transition=False)

    class Adapter:
        def __init__(self, config):
            self.config = config
            self.state = np.zeros(4)
            self.previous = None
            self.current = None
            self.env = SimpleNamespace(sim=SimpleNamespace(get_state=lambda:
                                        SimpleNamespace(flatten=lambda: self.state.copy())), owner=self)
            record.instances.append(self)

        def reset(self, episode):
            bits = tuple(episode["initial_mask"])
            record.resets.append(bits)
            if record.fail_transition and self.previous == (True, True) and bits == (False, False):
                raise ValueError("missing/mismatched model_xml_sha256")
            self.previous, self.current = bits, bits
            self.state = np.load(root / episode["state_path"], allow_pickle=False)
            if record.bad_restore and bits == (True, False):
                self.state[1] += 1e-12
            if record.signed_zero_state and bits == (True, False):
                self.state[0] = -0.
            obs = observation(self.state)
            if record.stale_image and bits == (True, False):
                obs["agentview_image"][:] += 1
            if record.rgb_rounding and bits == (True, False):
                obs["agentview_image"][0, 0] += 1
            if record.tiny_proprio and bits == (True, False):
                obs["robot0_joint_pos"][0] += 1e-12
            return obs

        def goal_values(self):
            return [bool(bit) for bit in self.state[2:4] > .5]

        def step(self, action):
            record.steps.append(self.current)
            self.state[0] += .05
            return observation(self.state)

        def close(self):
            record.closed = True

    class NativeSnapshot:
        def __init__(self, env, state, goals):
            self.adapter = env.owner

        def validation_snapshot(self):
            state = self.adapter.state.copy()
            return {"state": state, "state_before_refresh": state.copy(), "qvel": [0.],
                    "robot_qpos": [state[1]], "object_positions": {"a": [state[2], 0., 0.], "b": [state[3], 0., 0.]},
                    "penetrations": [], "goals": self.adapter.goal_values(), "fresh_observation": observation(state)}

    monkeypatch.setattr(replay, "LiberoGoalEnv", Adapter)
    monkeypatch.setattr(replay, "CandidateAuditEnv", NativeSnapshot)
    monkeypatch.setattr(replay, "_image", lambda *args: None)
    monkeypatch.setattr(replay, "model_xml_hash", lambda env: "c" * 64 if env.owner.goal_values()[0] else "b" * 64)
    return path, tmp_path / "replay", manifest, record


def save_manifest(path, manifest):
    manifest["content_hash"] = manifest_hash(manifest)
    write_json(path, manifest)


def test_shared_formal_adapter_repeats_all_masks_without_changing_source(pack):
    path, output, _, record = pack
    original = {str(file): file.read_bytes() for file in path.parent.rglob("*") if file.is_file()}
    report = replay.replay(path, output, steps=2, repeats=2)
    expected = [(False, False), (True, False), (False, True), (True, True)] * 2
    assert record.resets == expected and len(record.instances) == 1
    assert len(record.steps) == 16 and record.closed
    assert report["technical_acceptance"] is True
    assert report["policy_called"] is False and report["release_authorized"] is False
    assert all(item["source_legal"] is False and all(item["reset_checks"].values()) for item in report["episodes"])
    assert original == {str(file): file.read_bytes() for file in path.parent.rglob("*") if file.is_file()}
    # Post-restore visuals may legitimately differ from reset XML; the formal
    # adapter checks reset identity, while replay records the restored identity.
    on_audit = json.loads((output / report["episodes"][1]["audit_path"]).read_text(encoding="utf-8"))
    assert on_audit["post_restore_model_xml_sha256"] == "c" * 64
    assert on_audit["expected_reset_model_xml_sha256"] == "b" * 64


@pytest.mark.parametrize("fault,failed_check", [("stale_image", "construction_observation_matches"),
                                                ("bad_restore", "saved_state_exact"),
                                                ("signed_zero_state", "saved_state_exact"),
                                                ("tiny_proprio", "initial_non_rgb_exact")])
def test_reset_image_and_state_mismatch_fail_before_stepping(pack, fault, failed_check):
    path, output, _, record = pack
    setattr(record, fault, True)
    report = replay.replay(path, output, steps=2, repeats=1)
    failed = report["episodes"][1]
    assert failed["technical_acceptance"] is False
    assert failed["reset_checks"][failed_check] is False
    assert failed["error"]["phase"] == "restore_candidate"
    assert (True, False) not in record.steps
    assert report["technical_acceptance"] is False


def test_raw_initial_pixels_are_compared_with_fixed_bound_without_replacing_policy_observation(pack):
    path, output, manifest, record = pack
    record.rgb_rounding = True
    report = replay.replay(path, output, steps=2, repeats=1)
    assert report["technical_acceptance"] is True
    row = report["episodes"][1]
    assert all(row["reset_checks"].values())
    audit = json.loads((output / row["audit_path"]).read_text())
    comparison = audit["reset_observation_comparison"]
    assert comparison["bit_exact"] is False and comparison["bounded_allowance_used"] is True
    assert comparison["non_rgb_bit_exact"] is True
    assert comparison["fresh_sha256"] == manifest["episodes"][1]["initial_observation"]["observation_sha256"]
    assert comparison["returned_sha256"] == audit["trace"][0]["observation_check"]["returned_sha256"]
    assert comparison["returned_sha256"] != comparison["fresh_sha256"]
    audit_path = output / row["audit_path"]
    actual = load_observation_artifact(audit_path.parent, audit["reset_initial_observation"],
                                       expected_digest=comparison["returned_sha256"])
    expected = load_observation_artifact(path.parent, manifest["episodes"][1]["initial_observation"])
    assert np.count_nonzero(np.any(actual["agentview_image"] != expected["agentview_image"], axis=-1)) == 1
    np.testing.assert_array_equal(actual["robot0_joint_pos"], expected["robot0_joint_pos"])


def test_missing_artifact_is_rejected_before_reset(pack):
    path, output, manifest, record = pack
    manifest["episodes"][0].pop("initial_observation")
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="initial observation artifact format"):
        replay.replay(path, output, steps=2)
    assert not record.instances


def test_same_instance_exposes_11_to_00_reset_xml_failure(pack):
    path, output, _, record = pack
    record.fail_transition = True
    report = replay.replay(path, output, steps=2, repeats=2)
    assert len(record.instances) == 1 and len(record.resets) == 8
    failure = report["episodes"][4]
    assert failure["initial_mask"] == [False, False]
    assert failure["technical_acceptance"] is False
    assert "model_xml_sha256" in failure["error"]["message"]
    assert failure["reset_checks"] == {}
    assert report["technical_acceptance"] is False


@pytest.mark.parametrize("fault,match", [("content_hash", "content_hash"), ("state_hash", "digest mismatch"),
                                         ("legal", "legal=False"), ("missing_mask", "complete masks"),
                                         ("duplicate_mask", "duplicate candidate mask")])
def test_invalid_candidate_pack_is_rejected_before_adapter_creation(pack, fault, match):
    path, output, manifest, record = pack
    if fault == "content_hash":
        manifest["content_hash"] = "0" * 64
        write_json(path, manifest)
    elif fault == "state_hash":
        state_file = path.parent / manifest["episodes"][0]["state_path"]
        np.save(state_file, np.zeros(4))
    else:
        if fault == "legal":
            manifest["episodes"][0]["construction"]["legal"] = True
        elif fault == "missing_mask":
            manifest["episodes"].pop()
        else:
            extra = deepcopy(manifest["episodes"][0])
            extra["episode_id"] = "different_id_same_mask"
            manifest["episodes"].append(extra)
        save_manifest(path, manifest)
    with pytest.raises(ValueError, match=match):
        replay.replay(path, output, steps=2)
    assert not record.instances and not output.exists()


def test_saved_states_must_match_components_even_when_all_file_hashes_are_updated(pack):
    path, output, manifest, record = pack
    episode = manifest["episodes"][1]
    state_file = path.parent / episode["state_path"]
    state = np.load(state_file)
    state[2] = 1.25
    np.save(state_file, state)
    episode["state_sha256"] = hashlib.sha256(state_file.read_bytes()).hexdigest()
    audit_file = path.parent / episode["construction"]["technical_audit"]
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    audit["trace"][0]["state"] = state.tolist()
    write_json(audit_file, audit)
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="exactly matched components"):
        replay.replay(path, output, steps=2)
    assert not record.instances


def test_source_audit_must_describe_the_saved_initial_state(pack):
    path, output, manifest, record = pack
    audit_file = path.parent / manifest["episodes"][0]["construction"]["technical_audit"]
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    audit["trace"][0]["state"][1] += .01
    write_json(audit_file, audit)
    with pytest.raises(ValueError, match="audit step 0 differs"):
        replay.replay(path, output, steps=2)
    assert not record.instances
