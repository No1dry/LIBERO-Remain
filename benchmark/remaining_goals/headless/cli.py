"""Task011 explicit CLI; file-only plan/inspect never initialize native/models."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("budget-plan", help="print the fixed 100 sources; no files, native or model")
    plan = sub.add_parser("dry-plan", help="file-only readiness; preserve all 100 planned entries")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)
    prep = sub.add_parser("prepare", help="USER-STARTED real state build/replay; never model inference")
    prep.add_argument("--data", type=Path, required=True)
    prep.add_argument("--reports", type=Path, required=True)
    prep.add_argument("--track", choices=("all", "primary", "extension"), default="all")
    run = sub.add_parser("run", help="USER-STARTED real model batch; verified existing tasks are skipped")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--track", choices=("all", "primary", "extension"), default="all")
    for name in ("inspect", "summarize"):
        cmd = sub.add_parser(name, help="offline evidence verification and fixed-denominator report")
        cmd.add_argument("--run", type=Path, required=True)
        if name == "summarize":
            cmd.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    from .planning import budget_plan, dry_plan
    from .workflow import write_json, run_batch, inspect_batch
    if args.command == "budget-plan":
        result = budget_plan()
    elif args.command == "dry-plan":
        result = dry_plan(args.config)
        args.out.mkdir(parents=True, exist_ok=False)
        write_json(args.out / "plan.json", result)
    elif args.command == "prepare":
        from .preparation import prepare
        result = prepare(args.data, args.reports, track=args.track)
    elif args.command == "run":
        result = run_batch(args.config, args.out, track=args.track)
    else:
        result = inspect_batch(args.run, getattr(args, "out", None))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "prepare":
        return 2 if any(row["status"] != "ready" for row in result["tasks"].values()) else 0
    if args.command == "run":
        return 2 if any(row["status"] != "completed" for row in result["tasks"].values()) else 0
    if args.command in {"inspect", "summarize"}:
        return 2 if result.get("unverified_task_artifacts") else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
