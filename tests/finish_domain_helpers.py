"""Synthetic fifty-group files and a fake provider, never real scientific data."""
from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np

from benchmark.remaining_goals.finish import data
from benchmark.remaining_goals.finish.data_profiles import DEFAULT_PROFILE


def make_assets(tmp_path, frames=2):
    import h5py
    root = Path(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    np.save(root / "initials.npy", np.array([[-100-i, 0, 0] for i in range(50)], dtype=np.float64))
    with h5py.File(root / "demonstrations.hdf5", "w") as source:
        group = source.create_group("data")
        for index in range(50):
            trajectory = group.create_group(f"demo_{index}")
            trajectory.create_dataset("states", data=np.array(
                [[1000+index, step / (frames-1), step] for step in range(frames)], dtype=np.float64))
            trajectory.attrs["model_file"] = "<mujoco model='synthetic-cpu-fixture'/>"
    (root / "task.bddl").write_text("synthetic CPU fixture; not a physical BDDL task", encoding="utf-8")
    config = {"data_profile": deepcopy(DEFAULT_PROFILE), "hdf5_path": str(root / "demonstrations.hdf5"),
        "init_states_path": str(root / "initials.npy"), "bddl_path": str(root / "task.bddl"),
        "original_instruction": "put both objects in the basket", "state_stride": 8}
    config["expected_assets"] = {target: hashlib.sha256(Path(config[key]).read_bytes()).hexdigest()
        for key, target in (("hdf5_path", "hdf5_sha256"), ("init_states_path", "init_states_sha256"),
                            ("bddl_path", "bddl_sha256"))}
    return config


def fake_truth(complete=True):
    return {"goals": [bool(complete), bool(complete)], "released": True,
            "release_evidence": {"method": "synthetic-contact-evidence", "test_only": True}}


class FakeProvider:
    metadata = {"test_only": True, "physics_validated": False}
    def __init__(self):
        self.restore_calls, self.hold_calls, self.closed = [], [], False

    def restore_demonstration(self, state, model_xml=None):
        self.restore_calls.append((state.copy(), model_xml))
        value = int(state[0] - 1000)
        return {"observation": {
            "agentview_image": np.full((2, 2, 3), value, np.uint8),
            "robot0_eye_in_hand_image": np.full((2, 2, 3), value+1, np.uint8),
            "robot0_eef_pos": state.copy(), "robot0_eef_quat": np.array([0., 0, 0, 1]),
            "robot0_gripper_qpos": np.zeros(2)}, **fake_truth(state[1] == 1)}

    def capture_hold_label(self, state, steps, model_xml=None):
        assert steps == 4
        self.hold_calls.append((state.copy(), model_xml))
        return {"source_state_sha256": data.state_sha256(state), "hold_contract": {"test_only": True},
                "trace": [{"step": index, **fake_truth()} for index in range(steps+1)]}

    def close(self):
        self.closed = True


def make_audit(tmp_path, frames=2):
    root = Path(tmp_path)
    config = make_assets(root / "assets", frames=frames)
    provider = FakeProvider()
    out = root / "audit"
    audit = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert audit["status"] == "ready_for_feature_export", audit["issues"]
    return out, audit, provider
