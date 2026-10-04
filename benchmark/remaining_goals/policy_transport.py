"""Bounded JSON/NumPy protocol between simulator and isolated model workers.

No pickle, sockets, ground-truth goals or simulator objects cross this boundary.
"""
from __future__ import annotations

import base64
import json
import math
import struct

import numpy as np

MAX_FRAME = 32 * 1024 * 1024


def encode(value, depth=0):
    if depth > 16:
        raise ValueError("protocol nesting limit exceeded")
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in "buif" or value.dtype.itemsize > 8 or not np.isfinite(value).all():
            raise ValueError("worker arrays must be finite real numeric arrays")
        contiguous = np.ascontiguousarray(value)
        return {"__ndarray__": True, "dtype": contiguous.dtype.str,
                "shape": list(contiguous.shape),
                "data": base64.b64encode(contiguous.tobytes()).decode("ascii")}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("protocol dictionary keys must be strings")
        return {key: encode(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item, depth + 1) for item in value]
    if isinstance(value, np.generic):
        return encode(value.item(), depth)
    if value is None or type(value) in (bool, str, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError(f"unsupported protocol value: {type(value).__name__}")


def decode(value, depth=0):
    if depth > 16:
        raise ValueError("protocol nesting limit exceeded")
    if isinstance(value, dict) and value.get("__ndarray__") is True:
        if set(value) != {"__ndarray__", "dtype", "shape", "data"}:
            raise ValueError("malformed protocol array")
        dtype = np.dtype(value["dtype"])
        shape = value["shape"]
        if (dtype.kind not in "buif" or dtype.itemsize > 8 or not isinstance(shape, list)
                or len(shape) > 8 or any(type(x) is not int or x < 0 for x in shape)):
            raise ValueError("unsafe protocol array dtype/shape")
        size = math.prod(shape) * dtype.itemsize
        if size > MAX_FRAME:
            raise ValueError("protocol array too large")
        raw = base64.b64decode(value["data"], validate=True)
        if len(raw) != size:
            raise ValueError("protocol array byte count mismatch")
        array = np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
        if not np.isfinite(array).all():
            raise ValueError("nonfinite protocol array")
        return array
    if isinstance(value, dict):
        return {key: decode(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item, depth + 1) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("invalid protocol scalar")


def _write_all(stream, data):
    view = memoryview(data)
    while view:
        written = stream.write(view)
        if not isinstance(written, int) or written <= 0 or written > len(view):
            raise OSError("model worker pipe did not accept a complete frame")
        view = view[written:]


def write_frame(stream, value):
    body = json.dumps(encode(value), separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise ValueError("worker frame exceeds size limit")
    _write_all(stream, struct.pack("!I", len(body)))
    _write_all(stream, body)
    stream.flush()


def _read_exact(stream, length):
    result = bytearray()
    while len(result) < length:
        part = stream.read(length - len(result))
        if not part:
            raise EOFError("model worker pipe closed")
        result.extend(part)
    return bytes(result)


def read_frame(stream):
    length = struct.unpack("!I", _read_exact(stream, 4))[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError("invalid worker frame length")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate protocol JSON key")
            result[key] = value
        return result
    return decode(json.loads(_read_exact(stream, length), object_pairs_hook=unique))
