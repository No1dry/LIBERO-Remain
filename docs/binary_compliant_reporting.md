# Binary compliant success reporting (Task034)

`binary-compliant-success-v1` is a presentation mapping of accepted completed
scores: `success` becomes `success=true, outcome="success"`; completed `failure`
and `unknown` become `success=false, outcome="unsuccessful"`. The entire original
record remains under each episode's `diagnostics`, including release uncertainty,
unknown reasons, physical events, path, endpoint and source references.

Technical, interrupted, missing, corrupt, duplicate and unplanned jobs are run
integrity problems. Their binary outcome is null. The report retains the fixed
planned population, shows completion and live completed SR, and emits formal SR
and equal-task macro SR only when every planned episode is valid and completed
and there are no integrity errors. Model/statistics/inference identities must
agree, including the method adapter identity. Differing models suppress live and
formal aggregate SR. Equal-task macro weights each task equally; total SR pools
episodes. For nine tasks with ten episodes each, both give 22/90 = 24.44%, with
68/90 = 75.56% unsuccessful.

## Read-only CLI

Main does not yet contain the accepted headless evaluator. This package does not
copy or merge that PR. Provide an existing checkout/archive with the exact
accepted `d8541ef4a4bb4cc2e34c95b10227ea5fcaddaff9` source (the full commit is recorded in
`libero_remain_reporting/accepted_core.json`). The loader verifies SHA-256 of all
97 Python source files under that commit's `benchmark/` and invokes the existing
file-only evidence readers in an isolated `python -I -B` subprocess. It does not
load models, create simulation, replay physics, render images, rebuild states or
write Python caches into that dependency.

Run from this Task034 checkout, with the same CPU Python environment used by the
accepted evaluator. No new third-party dependency is introduced.

```powershell
python -m libero_remain_reporting --core-root ../LIBERO-Remain-task033-r2 --condition 10 --mask10-rescore <old-six-support-rescore-directory> --mask10-run <original-old-six-run-directory> --runs <new-three-mask10-run-directory> --out reports/binary-mask10-001
```

`--mask10-run` also supports the accepted raw-only historical reader when no
`--mask10-rescore` is supplied. The rescore input is the existing accepted
table-support report directory, not a new rescore command. `--runs` accepts zero
or more Task033 batch directories. Repeated occurrences remain duplicate jobs;
the report never selects the best run. For the separate official capability
control, use `--condition 00 --normal00-run <historical-normal00-root> --runs
<new-three-normal00-root>`. Condition 00 remains capability-only and is not the
mask10 compliant main result.

The new output contains `summary.json` and `report.md`. Console output shows
binary counts, formal SR, live completed SR, completion and integrity-error count.
Exit status is 0 for a complete valid population and 2 for incomplete/integrity
results. No existing output may be overwritten, and output must be outside old
run/evidence directories. There is deliberately no standalone-summary input.
The existing accepted source/result readers bind summaries or raw fallback to
their frozen batch, plans, task metadata and file references at their original
evidence level. This report does not upgrade archived-summary evidence into a
claim that unread raw/video files were revalidated.

## Reusable API for method030

```python
from libero_remain_reporting import (
    load_verified_results, map_verified_results, render_report, write_report,
)

loaded = load_verified_results(
    accepted_core_root,
    condition="10",
    mask10_rescore=old_six_rescore,
    mask10_run=old_six_run,
    runs=[new_three_run],
)
report = map_verified_results(
    loaded["expected_episodes"], loaded["records"],
    artifact_issues=loaded["artifact_issues"],
)
report["source_roots"] = sorted(set(report["source_roots"] + loaded["source_roots"]))
write_report(report, new_output_directory)
```

Method evaluation may call `map_verified_results(expected_episodes, records,
artifact_issues=...)` directly **after its accepted source/result verification**.
The mapper accepts the existing record sequence or episode-id mapping with
`primary`, `legacy`, `condition`, and `source` fields. It requires the complete
planned source identity and checks `source.verified_files` hashes before mapping
completed rows. It is not an alternative evaluator, an arbitrary JSON validator,
or an authentication boundary against fabricated records. A caller cannot turn
a hand-filled summary into verified truth by setting a confidence flag: no such
flag/API exists. Keep the verifier's full `source.model_identity`, including
`policy_metadata.method_adapter`, so distinct adapters cannot be pooled.

CPU checks:

```powershell
$env:LIBERO_REMAIN_ACCEPTED_CORE = (Resolve-Path ../LIBERO-Remain-task033-r2).Path
python -m pytest tests/test_binary_compliant_reporting.py tests/test_binary_compliant_loader.py -q --basetemp reports/task034-tests-001
```

The environment variable enables the accepted external-core integration cases;
without it, those three tests skip explicitly. Use a fresh `--basetemp` with an
existing parent directory if the default Windows temp directory is inaccessible.
