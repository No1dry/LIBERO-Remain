# Task034 round1 — binary compliant success presentation

Implementation submitted on `x/task034-binary-report`, based on main `3bf2c79`.
Code commit: `d2afce4eb074b777364daddea2c08bd70731865f`.
PR: https://github.com/No1dry/LIBERO-Remain/pull/15 ; no automatic merge.

Added standalone package `libero_remain_reporting` and the report-only CLI
documented in `docs/binary_compliant_reporting.md`. Public exports are
`map_verified_results(expected_episodes, records, *, artifact_issues=())`,
`load_verified_results(core_root, *, condition="10", normal00_run=None,
mask10_rescore=None, mask10_run=None, runs=())`, `render_report(report)` and
`write_report(report, output)`.

Completed accepted success maps to 1; completed accepted failure/unknown maps to
0. Technical/missing/corrupt/interrupted/duplicate/unplanned records retain null
model outcome and explicit run-integrity errors. Formal total SR and equal-task
macro SR require the complete fixed population. Incomplete reports show live
completed SR and completion. Original records, physical facts, release unknowns,
endpoints, paths and source references survive unchanged inside diagnostics.
Distinct model/statistics/inference/method-adapter identities cannot aggregate.

Dependency: main lacks accepted headless code. The loader requires the external
accepted `d8541ef4` implementation, verifies a source SHA manifest, and invokes its
existing historical/new-three source/result readers in `python -I -B`. Only the
97-entry SHA manifest is included here; no accepted PR source is copied or merged.
There is no standalone-summary or handwritten-success input. Existing archived
summary evidence retains its accepted evidence level; no raw/video evidence is
claimed beyond the files actually checked by the accepted reader.

Verification: final root run 12 targeted CPU/fake checks passed in 0.94s (0 skipped); independent review also passed 12 in 0.98s using Python from the
existing CPU environment and the accepted local checkout. Tests cover binary
mapping, original-object preservation, unknown-release preservation, 22/90 and
per-task counts, unequal-size equal-task macro, missing/technical/running jobs,
duplicates/unplanned rows, source hash changes, output isolation (including
duplicate records), adapter identity mismatch, accepted-core pin rejection,
arbitrary summary rejection, and isolated file-only CLI with 90 missing jobs.
Command: `python -m pytest tests/test_binary_compliant_reporting.py
tests/test_binary_compliant_loader.py -q --basetemp reports/task034-final-tests`,
with `LIBERO_REMAIN_ACCEPTED_CORE` pointing to the accepted checkout. The wheel
also built with `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir
reports/task034-wheel`. The user requested targeted CPU/fake only; no full-suite
run.

No real derived baseline report was generated in this implementation worktree:
the original baseline result files were not supplied here. The 22/90 reference
comes from the user's accepted result, and the executable 22/90 verification is
synthetic. The accepted-core CLI integration exercises missing-input and rejected
summary paths, not the real 90-episode baseline artifact chain. Codex can derive
that separate report when the original evidence paths are available.

Next operation and owner: Codex reviews PR15, deploys the separate reporting package,
and runs the file-only CLI in `docs/binary_compliant_reporting.md` against original
baseline evidence. The accepted reported total is22/90=24.44%; an actual derived
file report still requires those source/result roots. User need not restart the baseline.

No model, GPU, native simulator, replay, new baseline, physics change, source-data
overwrite, training job, or automatic PR merge was performed. No hard blocker.
