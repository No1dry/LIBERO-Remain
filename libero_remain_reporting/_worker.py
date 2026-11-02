"""Private read-only bridge, run with -I -B and a hash-pinned accepted core."""
import json
import sys


def main():
    options = json.load(sys.stdin)
    sys.path.insert(0, options["core_root"])
    from benchmark.remaining_goals.headless.offline_scoring import collect_reuse
    from benchmark.remaining_goals.headless.nine_planning import expected_episodes, NEW_TASKS
    from benchmark.remaining_goals.headless.nine_workflow import _collect, make_report
    condition = options["condition"]
    protocol = "nine-mask10" if condition == "10" else "nine-normal00"
    reuse = collect_reuse(normal00_run=options["normal00_run"] if condition == "00" else None,
                         mask10_rescore=options["mask10_rescore"] if condition == "10" else None,
                         mask10_run=options["mask10_run"] if condition == "10" else None)
    records = [record for record in reuse["episodes"].values() if record["condition"] == condition]
    issues = [issue for issue in reuse["issues"] if issue.get("condition") == condition]
    for directory in options["runs"]:
        try:
            batch, selected, failures = _collect(directory)
            if batch["protocol"] != protocol:
                continue
            records.extend(selected[e["episode_id"]] for e in batch["expected"] if e["task_id"] in NEW_TASKS)
            issues.extend(failures)
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"path": directory, "reason": f"{type(error).__name__}: {error}"})
    # Reuse the accepted model-identity and source-reference checks as well.
    selected = {record["primary"]["episode_id"]: record for record in records}
    checked = make_report(selected, protocols=[protocol])
    issues.extend({"reason": reason} for reason in checked["model_compatibility_issues"])
    # Keep duplicate occurrences for the mapping layer to report explicitly.
    result = {"expected_episodes": expected_episodes(protocol), "records": records,
              "artifact_issues": issues, "condition": condition,
              "simulation_created": False, "weights_loaded": False}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
