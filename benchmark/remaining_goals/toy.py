"""Deterministic CPU fixtures, explicitly NOT LIBERO research results."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .schema import write_manifest


def build_toy_manifest(directory: Path, *, scenes: int = 2) -> Path:
    """Create a two-goal, four-mask fixture in a new directory."""
    if scenes < 1:
        raise ValueError("scenes must be positive")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "states").mkdir()
    episodes = []
    goals = [
        {"id": "a", "language": "complete A", "predicates": [["complete", "a"]]},
        {"id": "b", "language": "complete B", "predicates": [["complete", "b"]]},
    ]
    for scene in range(scenes):
        for bits in ("00", "10", "01", "11"):
            episode_id = f"toy_s{scene:03d}_{bits}"
            state_path = f"states/{episode_id}.npy"
            mask = [b == "1" for b in bits]
            np.save(directory / state_path, np.array(mask, dtype=np.float64))
            episodes.append({
                "episode_id": episode_id, "task_id": "toy_two_goals",
                "suite": "toy", "libero_task_id": 0, "task_name": "toy_two_goals",
                "instruction": "complete A and B", "goal_specs": goals,
                "initial_mask": mask, "state_path": state_path,
                "state_sha256": hashlib.sha256((directory / state_path).read_bytes()).hexdigest(),
                "source_id": f"toy_source_{scene}", "split": "test",
                "initial_state_index": scene, "seed": scene, "pose_id": "toy_neutral",
                "horizon": 4, "retention_steps": 3,
                "construction": {"method": "synthetic_test_fixture", "legal": True,
                                 "reviewed_by": "toy_contract_only_not_physics"},
            })
    manifest = {"schema_version": "remaining-goals-v0.1",
                "environment": {"name": "toy", "fingerprint": "toy-contract-v1"},
                "episodes": episodes}
    path = directory / "manifest.json"
    write_manifest(manifest, path)
    return path


class ToyGoalEnv:
    """Two slots whose brightness represents completion; actions set a slot.

    The toy policy sees rendered pixels, not evaluator masks or source IDs.
    This deliberately simple world tests bookkeeping, not perception.
    """

    def __init__(self, config: dict):
        self.base_dir = Path(config["manifest_dir"])
        self.values = np.zeros(2, dtype=np.float64)

    def reset(self, episode: dict) -> dict:
        self.values = np.load(self.base_dir / episode["state_path"], allow_pickle=False).copy()
        if self.values.shape != (2,):
            raise ValueError("ToyGoalEnv requires exactly two goals")
        return self._observation()

    def _observation(self) -> dict:
        pixels = np.zeros((8, 16, 3), dtype=np.uint8)
        for i in range(2):
            pixels[:, i * 8:(i + 1) * 8] = 255 if self.values[i] >= 0.5 else 0
        return {"images": {"front": pixels}, "proprio": np.zeros(8)}

    def goal_values(self) -> list[bool]:
        return [bool(x >= 0.5) for x in self.values]

    def step(self, action) -> dict:
        action = np.asarray(action)
        for i in range(2):
            if action[i] > 0.5:
                self.values[i] = 1.0
            elif action[i] < -0.5:
                self.values[i] = 0.0
        return self._observation()

    def hold_action(self):
        return np.zeros(7)

    def close(self):
        pass


class ToyPolicy:
    """Known-answer fixtures: reactive succeeds, idle misses unfinished goals."""

    def __init__(self, config: dict):
        self.mode = config.get("mode", "reactive")
        if self.mode not in ("reactive", "idle", "destructive"):
            raise ValueError("toy mode must be reactive, idle or destructive")

    def reset(self):
        pass

    def predict(self, observation, instruction):
        action = np.zeros(7)
        if self.mode == "idle":
            return action
        if self.mode == "destructive":
            action[:2] = -1
            return action
        pixels = observation["images"]["front"]
        for i in range(2):
            if pixels[:, i * 8:(i + 1) * 8].mean() < 128:
                action[i] = 1
                return action
        return None


def make_policy(config: dict):
    return ToyPolicy(config)
