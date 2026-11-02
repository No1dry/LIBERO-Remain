"""Profile propagation at real construction/reset boundaries with native doubles."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from benchmark.remaining_goals import build, replay_candidates, selected_build, selected_replay
from benchmark.remaining_goals.observation_artifact import save_observation_artifact
from benchmark.remaining_goals.validation import validate_candidate
from tests.test_remaining_validation import CandidateEnv, snapshot
from tests.test_task033_r3_profile import V6, obs


def test_construction_static_dynamic_and_typed_initial_share_v6(monkeypatch, tmp_path):
    class Audit(CandidateEnv):
        def __init__(self):
            rows = [snapshot(i) for i in range(151)]
            for row in rows: row["fresh_observation"] = obs(1)
            super().__init__(rows, returned=obs())
            self.initial_observation = obs()
    monkeypatch.setattr(build, "CandidateAuditEnv", lambda *a, **k: Audit())
    episode = {"episode_id": "sample", "goal_specs": [], "initial_mask": [True, False]}
    result = build._audit_state(None, None, episode, tmp_path, Path("validation"),
        validation_steps=150, velocity_tolerance=.01, robot_tolerance=.002, observation_profile=V6)
    assert result["technical_acceptance"] is True
    for name in ("static_audit.json", "audit.json"):
        audit = json.loads((tmp_path / "validation" / name).read_text())
        assert audit["observation_profile"] == V6
    assert len(json.loads((tmp_path / "validation/audit.json").read_text())["trace"]) == 151
    assert episode["initial_observation"]["sha256"]


@pytest.mark.parametrize("state_exact,nonrgb_exact,passes", [(True, True, True), (False, True, False), (True, False, False)])
def test_formal_reset_v6_keeps_exact_saved_state_and_nonrgb(monkeypatch, tmp_path, state_exact, nonrgb_exact, passes):
    expected = obs()
    reference = save_observation_artifact(tmp_path, "construction.npz", expected)
    actual = obs(1)
    if not nonrgb_exact: actual["proprio"][0] = 1e-9
    state = np.array([0., 0.])
    adapter = SimpleNamespace(reset=lambda e: deepcopy(actual), goal_values=lambda: [True, False], env=object())
    monkeypatch.setattr(replay_candidates, "_state", lambda env: state.copy() if state_exact else state + 1.)
    monkeypatch.setattr(replay_candidates, "model_xml_hash", lambda env: "b" * 64)
    monkeypatch.setattr(replay_candidates, "_image", lambda *args: None)
    monkeypatch.setattr(replay_candidates, "CandidateAuditEnv", lambda *a, **k: None)
    wrapper = replay_candidates.ReplayAuditEnv(adapter, state, reference["observation_sha256"],
        frames_dir=tmp_path / "reset", manifest_dir=tmp_path, observation_profile=V6)
    episode = {"initial_observation": reference, "initial_mask": [True, False], "goal_specs": []}
    if passes:
        wrapper.restore_candidate(episode)
        assert all(wrapper.reset_checks.values())
    else:
        with pytest.raises(ValueError): wrapper.restore_candidate(episode)
    assert wrapper.reset_observation_comparison["observation_profile"] == V6


def test_selected_replay_propagates_profile_and_certificate_without_rebuilding(monkeypatch, tmp_path):
    state = np.array([0., .4, 1., 0.])
    state_path = tmp_path / "state.npy"
    np.save(state_path, state)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"original":true}')
    cert = tmp_path / "certificate.json"; cert.write_text('{"immutable":true}')
    episode = {"episode_id": "two_pots_s007_10", "initial_mask": [True, False], "model_xml_sha256": "b" * 64,
        "state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(), "construction": {"legal": False},
        "initial_observation": {"observation_sha256": "a" * 64}}
    def candidate(task, index, path, **options):
        assert options == {"protocol": "nine-mask10", "rgb_certificate": cert}
        return {"episode": episode, "manifest": {"environment": {}}, "source_content_hash": "c" * 64,
                "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    monkeypatch.setattr(selected_replay, "_candidate", candidate)
    received = []
    class Wrapper:
        def __init__(self, *args, **kwargs):
            assert kwargs["observation_profile"] == V6
            self.reset_checks = {}; self.reset_observation_comparison = {}; self.reset_initial_observation = {}
            self.post_restore_xml_sha256 = "b" * 64
    def validate(env, e, **kwargs):
        received.append(kwargs)
        return {"technical_acceptance": True, "checks": {}, "error": None}
    backend = SimpleNamespace(verify_state_file=lambda *a: state_path, HOLD=build.HOLD,
        LiberoGoalEnv=lambda config: SimpleNamespace(close=lambda: None), ReplayAuditEnv=Wrapper,
        validate_candidate=validate, _write=build._write)
    monkeypatch.setattr(selected_replay, "_backend", lambda: backend)
    report = selected_replay.replay(manifest_path, tmp_path / "replay", task="two_pots", index=7,
        protocol="nine-mask10", observation_profile=V6, rgb_certificate=cert)
    assert report["technical_acceptance"] is True
    assert len(received) == 2 and [kw["steps"] for kw in received] == [150, 150]
    assert all(kw["observation_profile"] == V6 for kw in received)
    assert report["observation_profile"] == V6
    assert report["rgb_certificate_sha256"] == hashlib.sha256(cert.read_bytes()).hexdigest()
    assert json.loads(manifest_path.read_text()) == {"original": True}


def test_selected_builder_passes_profile_and_records_manifest_identity(monkeypatch, tmp_path):
    from tests.test_selected_producers import fake_builder
    from benchmark.remaining_goals.nine_catalog import get_task
    profile = get_task("two_pots")
    backend, calls = fake_builder(monkeypatch, selected_build, tmp_path)
    old_scene = backend.create_scene
    def create(*args, **kwargs):
        env, _, bddl = old_scene(*args, **kwargs)
        env.env.parsed_problem["goal_state"] = profile["official_goal_predicates"]
        env.env._eval_predicate = lambda p: p[0] == "turnon"
        env.check_success = lambda: False
        return env, SimpleNamespace(name=profile["name"], language="official"), bddl
    backend.create_scene = create
    backend._audit_state = lambda env, state, episode, output, relative, **options: (
        calls["audits"].append(options) or episode.update(initial_observation={"sha256": "b" * 64, "observation_sha256": "c" * 64})
        or {"technical_acceptance": True})
    monkeypatch.setattr(selected_build, "_suite", lambda p: SimpleNamespace(n_tasks=10,
        get_task=lambda i: SimpleNamespace(name=p["name"] if i == 8 else "other")))
    report = selected_build.build(tmp_path / "built", task="two_pots", index=0,
        protocol="nine-mask10", observation_profile=V6)
    manifest = json.loads((tmp_path / "built/manifest.candidates.json").read_text())
    assert report["complete"] is True
    assert calls["audits"][0]["observation_profile"] == V6
    assert report["observation_profile"] == manifest["observation_profile"] == V6
    assert manifest["episodes"][0]["observation_profile"] == V6


@pytest.mark.parametrize("operation", ["build", "replay"])
def test_v6_native_entry_rejects_legacy_scope_before_output_or_backend(monkeypatch, tmp_path, operation):
    module = selected_build if operation == "build" else selected_replay
    monkeypatch.setattr(module, "_backend", lambda: pytest.fail("out-of-scope native backend"))
    with pytest.raises(ValueError, match="nine"):
        if operation == "build":
            module.build(tmp_path / "out", task="frypan_stove9", index=0, observation_profile=V6)
        else:
            module.replay(tmp_path / "missing.json", tmp_path / "out", task="frypan_stove9", index=0,
                          observation_profile=V6)
    assert not (tmp_path / "out").exists()
