"""Independent user-invoked FINISH stages. No command implicitly starts another."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def parser():
    root = argparse.ArgumentParser(description="LIBERO-Remain task007 FINISH-v1 explicit stages")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("budget-plan", help="No assets/imports: fixed Stage04 evaluation budget")
    p.add_argument("--include-remain-shadow", action="store_true")
    p = sub.add_parser("plan-data", help="Read configuration/files only; never construct simulator/model")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("audit-data", help="USER REAL: restore saved states and passive hold labels")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("prepare-normal", help="USER REAL: prepare precisely validation/test normal00 sources")
    p.add_argument("--indices", required=True, nargs="+", type=int)
    p.add_argument("--environment-config")
    p.add_argument("--out", required=True)
    p = sub.add_parser("preflight", help="USER REAL: restore source and inspect release/hold, no model")
    p.add_argument("--source-config", required=True)
    p.add_argument("--episode-id", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("export-features", help="USER REAL: same-forward frozen OFT feature export")
    p.add_argument("--audit", required=True)
    p.add_argument("--runtime-config", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("train", help="USER: train only FP32 finish head from audited feature cache")
    p.add_argument("--cache", required=True)
    p.add_argument("--training-config")
    p.add_argument("--out", required=True)
    p = sub.add_parser("parity", help="USER REAL: original/shadow actions on 32 fixed validation inputs")
    p.add_argument("--audit", required=True)
    p.add_argument("--runtime-config", required=True)
    p.add_argument("--head-artifact", required=True)
    p.add_argument("--atol", type=float, default=0.0)
    p.add_argument("--rtol", type=float, default=0.0)
    p.add_argument("--out", required=True)
    for name, description in (("dry-plan", "File-only source/head/config binding and budget"),
                              ("run", "USER REAL: one explicit validation/normal/Remain job")):
        p = sub.add_parser(name, help=description)
        p.add_argument("--config", required=True)
        p.add_argument("--out", required=True)
    p = sub.add_parser("calibrate", help="Read-only normal-validation shadow first-hit threshold selection")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("rescore", help="Read-only ledger/video verification and new scoring directory")
    p.add_argument("--run", required=True)
    p.add_argument("--stable-steps", type=int, choices=(1, 4, 8), default=4)
    p.add_argument("--out", required=True)
    p = sub.add_parser("inspect", help="Read-only original evidence verification; no file writes")
    p.add_argument("--run", required=True)
    return root


def _new_report(output, filename, value):
    from .workflow import write_json
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/filename, value)
    return value


def preflight(source_config, episode_id, output, *, env_factory=None):
    from copy import deepcopy
    from .workflow import load_source, write_json
    from .schema import validate_evaluator_state
    from ..observation_artifact import save_observation_artifact
    from ..runner import _observation
    source, path = load_source(source_config)
    episodes = [e for e in source["episodes"] if e["episode_id"] == episode_id]
    if len(episodes) != 1 or episodes[0]["task_id"] != "basket":
        raise ValueError("preflight needs one existing basket episode")
    if env_factory is None:
        from .environment import make_env
        env_factory = make_env
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema_version":"remaining-finish-environment-preflight-v1", "episode":deepcopy(episodes[0]),
              "status":"running", "trace":[], "error":None, "model_calls":0}
    env = None
    try:
        env = env_factory({"manifest_dir":str(path.parent), "environment":source["environment"], "image_size":256,"control_freq":20})
        obs = env.reset(episodes[0])
        report["initial_observation"] = save_observation_artifact(out, "initial.npz", _observation(obs))
        initial = validate_evaluator_state(env.evaluator_state(), len(episodes[0]["initial_mask"]))
        report["trace"].append({"step":0, **initial})
        if initial["goals"] != episodes[0]["initial_mask"]:
            raise ValueError("preflight restored initial goal mask differs from source")
        report["hold_contract"] = env.begin_hold()
        if not isinstance(report["hold_contract"], dict) or not report["hold_contract"]:
            raise ValueError("preflight requires an explicit physical hold contract")
        for step in range(1, 5):
            action = env.hold_action()
            env.step(action)
            truth = validate_evaluator_state(env.evaluator_state(), len(episodes[0]["initial_mask"]))
            report["trace"].append({"step":step, "action":action.tolist(), **truth})
        report["status"] = "recorded"
        report["unknown_target_release_states"] = sum(r["released"] is None for r in report["trace"])
        report["notice"] = "Physical preflight evidence only; inspect object contacts/geometry and release coverage. No model or scientific success claim."
    except BaseException as exc:
        report.update(status="technical_error", error=f"{type(exc).__name__}: {exc}")
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException as exc:
                report.update(status="technical_error", error=f"close: {exc}")
        write_json(out/"preflight.json", report)
    return report


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        from .data import read_json
        from . import workflow
        command = args.command
        if command == "budget-plan":
            extra = 15 if args.include_remain_shadow else 0
            result = {"schema_version":"remaining-finish-budget-v1", "protocol_version":"remaining-finish-v1",
                      "simulation_created":False,"weights_loaded":False,"validation_shadow":5,"normal_active":10,
                      "remain_active":15,"remain_shadow":extra,"rollouts":30+extra,
                      "horizon":520,"retention_steps":150,"chunk":8,"maximum_physical_steps":(30+extra)*670,
                      "notice":"Feature/audit/parity/preparation costs separate. Each real stage requires its own user command."}
        elif command in ("plan-data", "audit-data"):
            from .data import audit_plan, audit_demonstrations
            config = read_json(args.config)
            if command == "plan-data":
                result = _new_report(args.out, "data_plan.json", audit_plan(config))
            else:
                from .environment import make_audit_provider
                result = audit_demonstrations(config, provider_factory=make_audit_provider, out=args.out)
        elif command == "prepare-normal":
            result = workflow.prepare_normal_bank(args.indices, args.out,
                        environment_config=read_json(args.environment_config) if args.environment_config else None)
        elif command == "preflight":
            result = preflight(read_json(args.source_config), args.episode_id, args.out)
        elif command == "export-features":
            from .data_commands import feature_export_command
            result = feature_export_command(args.audit, args.runtime_config, args.out)
        elif command == "train":
            from .training import train_from_cache
            result = train_from_cache(args.cache, args.out, config=read_json(args.training_config) if args.training_config else None)
        elif command == "parity":
            from .data_commands import parity_command
            result = parity_command(args.audit, args.runtime_config, args.head_artifact, args.out, atol=args.atol, rtol=args.rtol)
        elif command == "dry-plan":
            result = _new_report(args.out, "plan.json", workflow.dry_plan(read_json(args.config)))
        elif command == "run":
            result = workflow.run(read_json(args.config), args.out)
        elif command == "calibrate":
            result = workflow.calibrate(args.run, args.out)
        elif command == "rescore":
            result = workflow.rescore(args.run, args.out, stable_steps=args.stable_steps)
        elif command == "inspect":
            metadata, rows = workflow.read_run(args.run)
            result = {"status":metadata["status"],"purpose":metadata["purpose"],"expected":len(metadata["episodes"]),
                      "results_verified":len(rows),"missing":metadata["missing"],"error":metadata["error"]}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        status = result.get("status")
        if status == "interrupted":
            return 130
        return 2 if status in {"technical_pause","technical_error","preparation_error","insufficient","audit_error", "error", "capability_not_established", "failed"} or result.get("passed") is False else 0
    except KeyboardInterrupt:
        print("Interrupted; inspect the new stage directory for partial evidence. No automatic resume.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
