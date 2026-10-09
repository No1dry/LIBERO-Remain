"""Execute one declared case inside its protocol's selected Python environment."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    request = json.loads(args.request.read_text(encoding="utf-8"))
    from .regression_env import execute_case
    result = execute_case(request["config"], request["case"], args.out, video_config=request["video_config"])
    # Case ownership belongs to this process; the parent has not created this directory.
    for key in ("id", "plan_hash", "protocol", "task_key", "task_name", "suite", "initial_state_index", "policy_seed", "env_seed"):
        expected = request["case"][key]
        if key in result and (type(result[key]) is not type(expected) or result[key] != expected):
            raise ValueError(f"backend case identity mismatch: {key}")
        result.setdefault(key, expected)
    from .regression import _write
    _write(args.out / "episode.json", result)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
