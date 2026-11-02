"""Task033 nine LIBERO-10 tasks. Only `run` starts model execution."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    from . import nine_planning as p
    from .workflow import write_json
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runtime = sub.add_parser("runtime-config", help="copy pinned SOG10 template with local paths; no loading")
    for flag in ("oft-repo", "checkpoint", "model-python"):
        runtime.add_argument("--" + flag, type=Path, required=True)
    runtime.add_argument("--cuda-visible-devices", default="0")
    runtime.add_argument("--out", type=Path, required=True)
    reuse = sub.add_parser("reuse-index", help="read-only 032 scoring of the historical six; never execute gaps")
    reuse.add_argument("--normal00-run", type=Path)
    reuse.add_argument("--mask10-rescore", type=Path)
    reuse.add_argument("--mask10-run", type=Path, help="original run or verified relocation of the rescore source")
    reuse.add_argument("--out", type=Path, required=True)
    for name in ("budget-plan", "sources-template", "configure"):
        command = sub.add_parser(name)
        command.add_argument("--protocol", choices=p.NINE_PROTOCOLS, required=True)
        command.add_argument("--out", type=Path, required=name != "budget-plan")
        if name == "configure":
            for flag in ("runtime-config", "sources", "reuse-manifest"):
                command.add_argument("--" + flag, type=Path, required=True)
    for name in ("dry-plan", "run"):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        if name == "run":
            command.add_argument("--allow-missing", action="store_true")
            command.add_argument("--continue", dest="continue_run", action="store_true")
    inspect = sub.add_parser("inspect", help="verify an existing new-three batch without native/model")
    inspect.add_argument("--run", type=Path, required=True)
    inspect.add_argument("--out", type=Path, help="optional new report directory")
    summary = sub.add_parser("summarize", help="read-only 90+90 table from old-six references and new-three runs")
    summary.add_argument("--runs", nargs="*", type=Path, default=[])
    summary.add_argument("--reuse-manifest", type=Path, required=True)
    summary.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "runtime-config":
        template = Path(__file__).resolve().parents[3] / "configs/remaining_goals/runtime/openvla_oft_sog10.json"
        result = p.read_json(template)
        result["adapter_options"].update(repo_path=str(args.oft_repo.resolve()), checkpoint=str(args.checkpoint.resolve()))
        # Preserve a venv/bin/python alias; resolving its symlink selects the
        # base interpreter and can silently discard the requested environment.
        result["runtime"].update(python_executable=str(args.model_python.expanduser().absolute()), cuda_visible_devices=args.cuda_visible_devices)
        result["notes"] = "Task033 new-three only; original SOG10 crop/proprio/full precision/seed7/chunk8. No weights loaded by configuration."
        write_json(args.out, result)
        p.load_runtime(args.out)
    elif args.command == "reuse-index":
        from .offline_scoring import collect_reuse
        from .nine_workflow import _check_output_isolation
        result = p.reuse_index(collect_reuse(normal00_run=args.normal00_run,
            mask10_rescore=args.mask10_rescore, mask10_run=args.mask10_run))
        _check_output_isolation(args.out.resolve(), {"reuse": result, "sources": []})
        write_json(args.out, result)
        # These are source-reference checks, not permission to rerun missing rows.
        p.read_reuse(args.out)
    elif args.command == "budget-plan":
        result = p.budget_plan(args.protocol)
        if args.out:
            write_json(args.out, result)
    elif args.command == "sources-template":
        result = p.sources_template(args.protocol)
        write_json(args.out, result)
    elif args.command == "configure":
        p.load_runtime(args.runtime_config)
        p.read_sources(args.sources, args.protocol)
        p.read_reuse(args.reuse_manifest)
        result = {"schema_version": p.CONFIG_SCHEMA, "protocol": args.protocol, "population": "new-three",
            "runtime_config": str(args.runtime_config.resolve()), "sources": str(args.sources.resolve()),
            "reuse_manifest": str(args.reuse_manifest.resolve())}
        write_json(args.out, result)
    elif args.command == "dry-plan":
        result = p.validate_plan(p.dry_plan(args.config))
        write_json(args.out, result)
    else:
        from . import nine_workflow as w
        if args.command == "run":
            result = w.run_batch(args.config, args.out, allow_missing=args.allow_missing, continue_run=args.continue_run)
        elif args.command == "summarize":
            result = w.summarize_runs(args.runs, args.reuse_manifest, args.out)
        else:
            result = w.inspect_batch(args.run)
            if args.out:
                target, source = args.out.resolve(), args.run.resolve()
                if target == source or target in source.parents or source in target.parents:
                    raise ValueError("inspect output must be outside the original run")
                w._check_output_isolation(target, {"reuse": {"episodes": result["episodes"]}, "sources": []})
                target.mkdir(parents=True, exist_ok=False)
                w.save_report(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "run":
        return 2 if any(row["status"] != "completed" for row in result["episodes"].values()) else 0
    if args.command in {"summarize", "inspect"}:
        return 2 if result.get("artifact_issues") or result.get("model_compatibility_issues") else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
