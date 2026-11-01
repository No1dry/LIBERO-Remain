"""Explicit Task031 controls. Only run/preparation commands create native jobs."""
import argparse
import json
from pathlib import Path


def sources_template(legacy_config, protocol):
    from .planning import resolve, file_sha
    from .source_acceptance import _json
    from .scoped_planning import SOURCES_SCHEMA, expected_episodes
    path = Path(legacy_config).resolve()
    config = _json(path.read_bytes())
    entries = []
    for episode in expected_episodes(protocol):
        task = episode["task_id"]
        source = config.get("sources", {}).get(task)
        origin, reason = None, "no legacy source"
        if source:
            manifest = resolve(path.parent, source["manifest"])
            if manifest.is_file():
                value = _json(manifest.read_bytes())
                origin = {"manifest": str(manifest), "manifest_sha256": file_sha(manifest),
                          "content_hash": value.get("content_hash")}
                if protocol == "selected-mask10":
                    report = resolve(path.parent, source["candidate_replay"])
                    if report.is_file():
                        origin.update(candidate_replay=str(report), replay_sha256=file_sha(report))
                else:
                    report = manifest.parent / "construction_report.json"
                    if report.is_file():
                        origin.update(initialization=str(report), initialization_sha256=file_sha(report))
                reason = "paths inventoried only; dry-plan must verify each selected source"
            else:
                reason = f"legacy manifest missing: {manifest}"
        entries.append({"task_id": task, "initial_state_index": episode["initial_state_index"],
                        "origin": origin, "inventory_note": reason})
    return {"schema_version": SOURCES_SCHEMA, "protocol": protocol,
            "expected": expected_episodes(protocol), "entries": entries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    budget = sub.add_parser("budget-plan", help="file-only fixed population/budget")
    template = sub.add_parser("sources-template", help="inventory original paths/hashes; no readiness claim")
    for p in (budget, template):
        p.add_argument("--protocol", required=True, choices=("normal00-control", "selected-mask10"))
    budget.add_argument("--population", required=True, choices=("existing-eight", "missing-two", "all"))
    template.add_argument("--legacy-config", type=Path, required=True)
    template.add_argument("--out", type=Path, required=True)
    plan = sub.add_parser("dry-plan", help="file-only per-source validation; creates no native/model")
    run = sub.add_parser("run", help="USER-STARTED model execution; preparation is separate")
    for p in (plan, run):
        p.add_argument("--config", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
    run.add_argument("--allow-missing", action="store_true")
    run.add_argument("--continue", dest="continue_run", action="store_true")
    run.add_argument("--prior-run", type=Path)
    for name in ("inspect", "summarize"):
        p = sub.add_parser(name, help="offline verify archived evidence and fixed denominators")
        p.add_argument("--run", type=Path, required=True)
        if name == "summarize":
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    from . import scoped_planning as planning
    from .workflow import write_json
    if args.command == "budget-plan":
        result = planning.budget_plan(args.protocol, args.population)
    elif args.command == "sources-template":
        result = sources_template(args.legacy_config, args.protocol)
        write_json(args.out, result)
    elif args.command == "dry-plan":
        result = planning.validate_plan(planning.dry_plan(args.config))
        args.out.mkdir(parents=True, exist_ok=False)
        write_json(args.out / "plan.json", result)
    else:
        from . import scoped_workflow
        if args.command == "run":
            result = scoped_workflow.run_batch(args.config, args.out, allow_missing=args.allow_missing,
                continue_run=args.continue_run, prior_run=args.prior_run)
        else:
            result = scoped_workflow.inspect_batch(args.run, getattr(args, "out", None))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "run":
        return 2 if any(r["status"] in {"technical_error", "technical_pause", "artifact_error", "missing", "failed"}
                        for r in result["episodes"].values()) else 0
    if args.command in {"inspect", "summarize"}:
        return 2 if result["unverified_task_artifacts"] else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
