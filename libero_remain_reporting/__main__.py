"""Read old evidence and write a new binary report; never starts execution."""
import argparse
from pathlib import Path

from . import load_verified_results, map_verified_results, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, required=True, help="accepted d8541ef4 source checkout")
    parser.add_argument("--condition", choices=("00", "10"), default="10")
    for flag in ("normal00-run", "mask10-rescore", "mask10-run"):
        parser.add_argument("--" + flag, type=Path)
    parser.add_argument("--runs", nargs="*", type=Path, default=[], help="Task033 new-three batch directories")
    parser.add_argument("--out", type=Path, required=True, help="new directory outside source runs")
    args = parser.parse_args(argv)
    loaded = load_verified_results(args.core_root, condition=args.condition, normal00_run=args.normal00_run,
                                   mask10_rescore=args.mask10_rescore, mask10_run=args.mask10_run, runs=args.runs)
    report = map_verified_results(loaded["expected_episodes"], loaded["records"], artifact_issues=loaded["artifact_issues"])
    report.update(condition=args.condition, accepted_core_commit=loaded["accepted_core_commit"])
    report["source_roots"] = sorted(set(report["source_roots"] + loaded["source_roots"]))
    write_report(report, args.out)
    def display(value):
        return f"{value['percent']:.2f}% ({value['numerator']}/{value['denominator']})" if value and value["percent"] is not None else "N/A"
    counts = report["counts"]
    print(f"Success: {counts['successes']}; unsuccessful: {counts['unsuccessful']}; unresolved jobs: {counts['unresolved_jobs']}")
    print("Formal SR: " + display(counts["formal_SR"]))
    print("Live completed SR: " + display(counts["live_completed_SR"]))
    print("Completion: " + display(counts["completion"]))
    print(f"Run integrity errors: {len(report['integrity_errors'])}")
    return 2 if report["integrity_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
