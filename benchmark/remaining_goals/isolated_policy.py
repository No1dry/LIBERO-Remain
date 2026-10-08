"""Synchronous policy proxy with bounded waits and an independently installed Python."""
from __future__ import annotations

import os
import math
from pathlib import Path
import queue
import subprocess
import threading

from .policy_transport import read_frame, write_frame
from .runner import _observation


class SubprocessPolicy:
    def __init__(self, config):
        runtime = config["runtime"]
        # Preserve venv/bin/python symlinks; resolving one selects the base
        # interpreter and loses the model environment's installed packages.
        executable = Path(os.path.abspath(Path(runtime["python_executable"]).expanduser()))
        if not executable.is_file():
            raise ValueError(f"model Python does not exist: {executable}")
        self.timeout = float(runtime.get("predict_timeout_seconds", 180))
        startup = float(runtime.get("startup_timeout_seconds", 1200))
        if not math.isfinite(self.timeout) or not math.isfinite(startup) or self.timeout <= 0 or startup <= 0:
            raise ValueError("worker timeouts must be finite and positive")
        seed = config.get("execution", {}).get("random_seed", 0)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("random_seed must be an integer in [0, 2**32)")
        root = Path(__file__).resolve().parents[2]
        environment = os.environ.copy()
        # Do not inherit another activated environment's import paths.
        environment.pop("PYTHONHOME", None)
        environment["PYTHONPATH"] = str(root)
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONHASHSEED"] = str(seed)
        if runtime.get("cuda_visible_devices") is not None:
            environment["CUDA_VISIBLE_DEVICES"] = str(runtime["cuda_visible_devices"])
        self.process = subprocess.Popen([str(executable), "-m", "benchmark.remaining_goals.policy_worker"],
                                        cwd=root, env=environment, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=None, bufsize=0)
        self.responses = queue.Queue()
        self.requests = queue.Queue()
        self._call_lock = threading.Lock()
        self.closed = False
        def reader():
            try:
                while True:
                    self.responses.put(read_frame(self.process.stdout))
            except Exception as error:
                self.responses.put(error)
        self.reader = threading.Thread(target=reader, name="remaining-policy-reader", daemon=True)
        def writer():
            try:
                while True:
                    request = self.requests.get()
                    if request is None:
                        return
                    write_frame(self.process.stdin, request)
            except Exception as error:
                self.responses.put(error)
        self.writer = threading.Thread(target=writer, name="remaining-policy-writer", daemon=True)
        self.reader.start()
        self.writer.start()
        try:
            response = self._call({"command": "initialize", "config": config}, timeout=startup)
            self.provenance = response["provenance"]
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _call(self, payload, timeout=None):
        if self.closed:
            raise RuntimeError("model worker is closed")
        if not self._call_lock.acquire(blocking=False):
            raise RuntimeError("model worker does not support concurrent calls")
        try:
            # Queueing the complete write bounds pipe stalls as well as inference.
            self.requests.put(payload)
            response = self.responses.get(timeout=timeout or self.timeout)
            if isinstance(response, Exception):
                raise RuntimeError(f"model worker disconnected: {response}") from response
            if not isinstance(response, dict) or response.get("ok") is not True:
                if not isinstance(response, dict):
                    raise RuntimeError("model worker returned a malformed response")
                raise RuntimeError(f"model worker failed: {response.get('error')}")
            return response
        except queue.Empty as error:
            try:
                self.close()
            except Exception:
                pass
            raise TimeoutError("model worker timed out; inspect stderr and runtime.*_timeout_seconds") from error
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise
        finally:
            self._call_lock.release()

    def reset(self):
        self._call({"command": "reset"})

    def predict(self, observation, instruction):
        # Defense in depth: runner also applies this whitelist before calling us.
        return self._call({"command": "predict", "observation": _observation(observation),
                           "instruction": instruction})["result"]

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.process.poll() is None:
                self.requests.put({"command": "close"})
                self.process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.requests.put(None)
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
            self.reader.join(timeout=1)
            self.writer.join(timeout=1)
        if self.process.returncode not in (None, 0):
            raise RuntimeError(f"model worker exited with code {self.process.returncode}")


def make_policy(config):
    return SubprocessPolicy(config)
