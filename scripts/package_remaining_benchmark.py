"""Create or independently verify a candidate-only Remaining Goals delivery ZIP.

Examples (from the project root):
  python scripts/package_remaining_benchmark.py create --state-pack data/PACK --replay reports/REPLAY/replay_report.json --out reports/candidate_delivery.zip
  python scripts/package_remaining_benchmark.py verify --zip reports/candidate_delivery.zip
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# Do not dirty an extracted archive with __pycache__ before strict verification.
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from benchmark.remaining_goals.package_audit import create_bundle, verify_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="bundle explicitly selected unreviewed candidates and evidence")
    create.add_argument("--state-pack", type=Path, required=True, action="append",
                        help="candidate pack; repeat for separate suites, paired with --replay by order")
    create.add_argument("--replay", type=Path, required=True, action="append",
                        help="matching replay report; repeat in the same order as --state-pack")
    create.add_argument("--out", type=Path, required=True)
    create.add_argument("--evidence", type=Path, action="append", default=[], help="additional explicit JSON/PNG/Markdown/CSV/HTML file or directory; repeatable")
    create.add_argument("--include-upstream", action=argparse.BooleanOptionalAction, default=True,
                        help="include verified official simulation source/assets (default true); --no-include-upstream keeps provenance and the downloader")
    verify = commands.add_parser("verify", help="offline checksum check; no simulator, NumPy, extraction or release promotion")
    target = verify.add_mutually_exclusive_group(required=True)
    target.add_argument("--zip", type=Path)
    target.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    try:
        report = (create_bundle(ROOT, args.state_pack, args.replay, args.out, evidence=args.evidence,
                                include_upstream=args.include_upstream)
                  if args.command == "create" else verify_bundle(args.zip or args.directory))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"package_remaining_benchmark: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
