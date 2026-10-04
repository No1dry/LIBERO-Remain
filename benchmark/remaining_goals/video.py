"""Optional, evaluator-only MP4 recording of observations already acquired.

Recording never renders, steps, or changes policy inputs. Frames are streamed
to a temporary MP4 and published only after the encoder closes successfully.
The requested FPS is the playback rate; stride > 1 produces a time-lapse.
``frame_steps`` preserves the exact physical step associated with every frame.
"""
from __future__ import annotations

from copy import deepcopy
import math
from numbers import Real
from pathlib import Path

import numpy as np


def normalize_video_config(config=None) -> dict:
    """Validate explicit recording options without importing encoder packages."""
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("video config must be a JSON object")
    unknown = set(config) - {"enabled", "fps", "camera", "stride"}
    if unknown:
        raise ValueError(f"unknown video options: {sorted(unknown, key=str)}")
    value = {"enabled": False, "fps": 20.0, "camera": "agentview", "stride": 1}
    value.update(config)
    if type(value["enabled"]) is not bool:
        raise ValueError("video.enabled must be boolean")
    fps = value["fps"]
    if isinstance(fps, bool) or not isinstance(fps, Real) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("video.fps must be a finite positive number")
    if value["camera"] not in ("agentview", "wrist", "both"):
        raise ValueError("video.camera must be agentview, wrist, or both")
    if type(value["stride"]) is not int or value["stride"] < 1:
        raise ValueError("video.stride must be a positive integer")
    value["fps"] = float(fps)
    return value


def _open_writer(path: Path, fps: float):
    try:
        import imageio.v2 as imageio
        import imageio_ffmpeg  # noqa: F401: give a useful missing-dependency error
    except ImportError as exc:
        raise RuntimeError("MP4 recording requires imageio and imageio-ffmpeg; from the checkout run python -m pip install -e '.[video]'") from exc
    return imageio.get_writer(str(path), format="FFMPEG", mode="I", fps=fps,
                              codec="libx264", pixelformat="yuv420p", macro_block_size=1)


def _camera(observation: dict, name: str) -> np.ndarray:
    if not isinstance(observation, dict):
        raise ValueError("video observation must be a dictionary")
    keys = (("agentview_image", "image") if name == "agentview"
            else ("robot0_eye_in_hand_image", "wrist_image"))
    pixels = next((observation[key] for key in keys if key in observation), None)
    if pixels is None:
        cameras = observation.get("images", {})
        if isinstance(cameras, dict):
            aliases = (("agentview", "front") if name == "agentview" else ("wrist", "eye_in_hand"))
            pixels = next((cameras[key] for key in aliases if key in cameras), None)
    if not isinstance(pixels, np.ndarray):
        raise ValueError(f"video camera {name!r} is unavailable")
    if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3 or not all(pixels.shape):
        raise ValueError(f"video camera {name!r} must be nonempty HWC RGB uint8")
    return pixels


class EpisodeVideoRecorder:
    """Fail-safe recorder. ``close().path`` is a basename, not a run-relative path.

    The evaluator supplies the run-relative path when serializing the report.
    Camera aliases are explicit: LIBERO agentview/eye-in-hand, or toy front.
    Both views are concatenated agentview-left, wrist-right without resizing.
    """
    def __init__(self, output_path: Path, config: dict, *, environment_name: str, episode: dict):
        self.config = normalize_video_config(config)
        self.output_path = Path(output_path)
        self.partial_path = self.output_path.with_name(self.output_path.stem + ".partial.mp4")
        self.environment_name = environment_name
        self.episode_id = episode.get("episode_id")
        self._writer = None
        self._owns_partial = False
        self._pending = None
        self._frame_steps = []
        self._errors = []
        self._shape = None
        self._last_seen = None
        self._report = None

    def _fail(self, exc):
        self._errors.append(f"{type(exc).__name__}: {exc}")

    def _frame(self, observation):
        if self.environment_name not in ("libero", "toy"):
            raise ValueError(f"unsupported video environment: {self.environment_name!r}")
        cameras = ("agentview", "wrist") if self.config["camera"] == "both" else (self.config["camera"],)
        images = []
        for camera in cameras:
            pixels = _camera(observation, camera)
            if self.environment_name == "libero":
                pixels = pixels[::-1, ::-1]
            images.append(pixels)
        if len(images) == 2 and images[0].shape[0] != images[1].shape[0]:
            raise ValueError("both video cameras must have equal height")
        frame = np.concatenate(images, axis=1) if len(images) == 2 else images[0].copy()
        # H.264 yuv420p requires even dimensions; do not resize source pixels.
        if frame.shape[0] % 2 or frame.shape[1] % 2:
            frame = np.pad(frame, ((0, frame.shape[0] % 2), (0, frame.shape[1] % 2), (0, 0)), mode="edge")
        frame = np.ascontiguousarray(frame)
        if self._shape is not None and frame.shape != self._shape:
            raise ValueError("video frame dimensions changed within an episode")
        self._shape = frame.shape
        return frame

    def _append(self, step, frame):
        if self._writer is None:
            if self.output_path.suffix.lower() != ".mp4":
                raise ValueError("video output must use the .mp4 suffix")
            if self.output_path.exists():
                raise FileExistsError(f"video output already exists: {self.output_path.name}")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            # Reserve our own temporary path; never truncate someone else's file.
            with self.partial_path.open("xb"):
                pass
            self._owns_partial = True
            self._writer = _open_writer(self.partial_path, self.config["fps"])
        self._writer.append_data(frame)
        self._frame_steps.append(step)

    def capture(self, observation, *, step: int):
        if self._report is not None:
            raise RuntimeError("video recorder is already closed")
        if not self.config["enabled"] or self._errors:
            return
        try:
            if type(step) is not int or step < 0:
                raise ValueError("video step must be a nonnegative integer")
            if (self._last_seen is None and step != 0) or (self._last_seen is not None and step <= self._last_seen):
                raise ValueError("video steps must start at zero and strictly increase")
            frame = self._frame(observation)
            self._last_seen = step
            self._pending = (step, frame)
            if step % self.config["stride"] == 0:
                self._append(step, frame)
        except Exception as exc:
            self._fail(exc)

    def close(self) -> dict:
        if self._report is not None:
            return deepcopy(self._report)
        if not self._errors and self._pending is not None:
            step, frame = self._pending
            if not self._frame_steps or step != self._frame_steps[-1]:
                try:
                    self._append(step, frame)
                except Exception as exc:
                    self._fail(exc)
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception as exc:
                self._fail(exc)
            self._writer = None
        path = None
        if not self._errors and self._frame_steps:
            try:
                if not self.partial_path.is_file() or self.partial_path.stat().st_size == 0:
                    raise RuntimeError("video encoder produced no MP4 bytes")
                if self.output_path.exists():
                    raise FileExistsError(f"video output already exists: {self.output_path.name}")
                self.partial_path.replace(self.output_path)
                self._owns_partial = False
                path = self.output_path.name
            except Exception as exc:
                self._fail(exc)
        if self._owns_partial:
            try:
                self.partial_path.unlink(missing_ok=True)
            except Exception as exc:
                self._fail(exc)
        self._pending = None
        status = ("video_error" if self._errors else "saved" if path else
                  "empty" if self.config["enabled"] else "disabled")
        self._report = {
            "status": status, "path": path, "frames": len(self._frame_steps),
            "frame_steps": list(self._frame_steps), **self.config,
            "environment": self.environment_name, "episode_id": self.episode_id,
            "orientation": "rotate_180" if self.environment_name == "libero" else "identity",
            "encoded_size": list(self._shape[:2]) if self._shape else None,
            "timebase": "frame_steps are physical steps; fps is playback rate; stride>1 is time-lapse",
            "error": "; ".join(self._errors) if self._errors else None,
        }
        return deepcopy(self._report)
