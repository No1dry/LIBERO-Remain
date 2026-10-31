"""Native-shaped CPU integration; no simulator, trained model, or real video."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from benchmark.remaining_goals.headless import environment
from benchmark.remaining_goals.headless.evidence import HeadlessEvidence, validate_evidence
from benchmark.remaining_goals.headless.metrics import score_episode
from benchmark.remaining_goals.headless.runner import run_episode
from benchmark.remaining_goals.headless.schema import validate_result
from benchmark.remaining_goals.task_catalog import TASKS
from tests.test_headless_environment import FakeNative
from tests.test_headless_runner import Policy, Video, episode, observation


class GeometryEnv:
    def reset(self, source):
        self.native = FakeNative("basket")
        self.measurements = environment.HeadlessMeasurements(self.native, "basket",
            source_reset_model_xml_sha256=source["model_xml_sha256"])
        self.steps, self.actions = 0, []
        return observation(0)

    def measurement_static(self):
        return self.measurements.measurement_static()

    def evaluator_state(self):
        # Only official predicate observations are synthetic. Release, role,
        # geometry, event certificates, and offline validation are actual code.
        return self.measurements.evaluator_state([True, self.steps >= 2])

    def step(self, action):
        self.actions.append(action.copy())
        self.steps += 1
        self.native.steps += 1
        self.native.sim.data.site_xpos[0] = [self.steps / 100, 0, 0]
        return observation(self.steps)


def test_geometry_runner_typed_evidence_readback_and_score(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, "_callback_status", lambda: "absent")
    source = episode(task_name=TASKS["basket"]["name"],
        model_xml_sha256=hashlib.sha256(b"<mujoco model='headless_cpu_synthetic'/>").hexdigest())
    identity = {"episode_id": source["episode_id"], "state_sha256": source["state_sha256"],
                "model_identity": {"checkpoint_sha256": "d" * 64, "normalization_key": "synthetic"}}
    evidence = HeadlessEvidence(tmp_path / "evidence" / source["episode_id"], identity)
    env, policy, video = GeometryEnv(), Policy(), Video()
    result = run_episode(env, policy, source, horizon=16, evidence=evidence, recorder=video, identity=identity)
    assert result["status"] == "completed", result.get("error")
    assert result["goal_confirmed_step"] == result["n_steps"] == 6
    assert env.native.steps == 6 and env.native.resets == 0 and policy.calls == 1
    assert result["path_length_m"] == pytest.approx(.06)
    assert len(video.frames) == 7 and video.closed == 1
    assert env.native.sim.model.xml_reads == 1
    assert score_episode(source, result)["success"] is True
    assert validate_result(result, source, identity)["verified"] is True

    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    restored = json.loads(raw.read_text(encoding="utf-8"))
    assert validate_evidence(tmp_path, restored, source, identity)["verified"] is True
    for actual, recorded in zip(env.actions, restored["executed_actions"]):
        assert actual.dtype == np.float64
        assert actual.tobytes() == np.asarray(recorded["action"], dtype=np.float64).tobytes()
    # A self-consistent protocol field cannot override its geometry evidence.
    altered = deepcopy(restored)
    altered["trace"][0]["event_candidates"]["wrong_grasp"]["distractor_1"] = True
    with pytest.raises(ValueError):
        validate_result(altered, source, identity)
    altered = deepcopy(restored)
    altered["measurement_static"]["role_profile"]["task_key"] = "dual_mugs"
    with pytest.raises(ValueError):
        validate_result(altered, source, identity)
