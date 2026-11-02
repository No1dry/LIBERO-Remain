# Task033 nine LIBERO-10 implementation plan

> **For agentic workers:** Use bounded implementation tasks with explicit file ownership and independent review. Keep CPU/fake verification task-scoped; do not start native or model jobs.

**Goal:** Deliver Plan6's nine compound LIBERO-10 tasks with 120 historical records reused and only 60 new evaluations executable, incorporating Task032 scoring.

**Architecture:** Preserve legacy task definitions/readers. Add explicit nine-task semantics and protocols, extend the existing selected-source producer/adapter pipeline, and reuse the existing evidence/video rollout machinery. A small offline scoring reader supplies provenance-bound historical rows to a nine-task plan/report, never to an execution queue.

**Tech stack:** Existing Python/NumPy/pytest, LIBERO adapters and OFT subprocess worker; no new model dependency.

**Spec:** `collaboration/tasks/033_libero10_nine_compound_tasks.md`, `033_nine_task_scope.json`, `032_official00_and_drop_diagnostic.md`, and `docs/experiment_plans/2026-11-02_libero10_nine_compound_tasks.md`.

## Global constraints

- Parent code is accepted Task031 `ac1301779cf6ae4c34ebc80c20936a4f7a4953be`; `7059092533b30573c3b219ec6454aa1ff342f580` synchronizes latest main requirements without production changes. New branch `x/task033-libero10-nine`; do not merge PRs.
- Official LIBERO-10 IDs exactly 0,1,2,3,4,6,7,8,9, full task names checked. New IDs exactly 3,8,9. Index0..9, seed7, H520, chunk8, original SOG10 revision638918f3d1c2e43a39a8a20772bdb8b91835e4b7 and libero_10_no_noops unchanged.
- Formal 00/10 denominators90 each; reuse60 each; new30 each, total60. No LIBERO-90 in new defaults, no id5, no retries of reused records. Preserve all historical files and cancelled legacy plans as history.
- Door tasks A=In, B=Close regardless BDDL ordering; Open is initial/preparation-only. Two-pots A=pot1 On, B=pot2 On, invariant=Turnon, complete official predicates retained.
- New00 terminates at first native official success or H. New10 retains all-goals+release five-observation confirmation and A/invariant preservation. Physical source thresholds and 150 construction + two independent150 replay checks unchanged.
- User alone starts native preparation/replay/model/training. Our commands run only CPU/fakes or file inspection. Required two-camera videos reuse existing observation frames.
- Task032 excludes only table_drop events/unknown contributions from new10 main compliance; other confirmed/unknown/release/preservation failure rules survive. Old scores and reasons remain visible. New00 mainSR is official success; mixed-endpoint whole-trajectory path lengths are not pooled as efficiency claims.

## Interfaces and ownership

1. Source/semantic task owns `nine_catalog.py`, `libero_env.py`, manifest schema/build/validation/selected_build/selected_replay, headless roles/environment/scoped_sources/selected_preparation, and corresponding source tests. It does not edit headless protocols/schema/runner/workflow/scoped_planning or the offline scoring module.
2. Offline-scoring task owns new `headless/offline_scoring.py` and its tests; does not edit runtime or source files.
3. Root owns headless protocols/schema/runner/evidence/workflow integration, new `nine_planning.py`, `nine_workflow.py`, `nine_cli.py`, scoped protocol dispatch, configs/runbook/README/export and their integration tests. Distinct file ownership permits source/scoring work to proceed independently.

New runtime protocol keys: `nine-normal00`, `nine-mask10`. New catalog exports `NINE_TASKS`, `NEW_TASKS`, `REUSE_TASKS`, `get_task(key)`. Task profiles retain `goals`=two active goal specs, plus `official_task_id`, `official_goal_predicates`, `invariant_predicates`, `required_open_predicates`. Episode `task_semantics` records explicit version and full official/active/invariant mapping. Source implementation documents its final pure validator/helper names before runtime integration.

New evaluator facts retain six legacy fields and add `invariant_values`, `official_goal_values`, `official_success`, `required_open_values`. All are evaluation-only. Full predicate mapping and native check_success must agree; Open is checked at t0 and source audit, never preserved after policy closure. New10 preservation includes A and all invariants. Legacy frames keep their exact existing schema.

Offline interfaces:

- `derive_row(legacy_row, *, condition, confirmed_events=None, event_unknown=None)` returns the new main row with old classification/reasons retained.
- `score_verified_result(episode, result, *, condition, source=None, legacy_row=None)` returns `{condition, legacy, primary, source}`; callers validate new runtime evidence first, and scorer verifies raw official signal consistency.
- `collect_reuse(*, normal00_run=None, mask10_rescore=None, mask10_run=None, task_ids=REUSE_TASKS)` returns `{episodes: {episode_id: record}, source_files: [...], issues: [...]}`. mask10_run with rescore only relocates/verifies its original evidence, never selects an alternate result. Each source distinguishes recorded hashes from files actually revalidated.

## Review focus

- Wrong predicate ordering or missing Turnon must fail source/rollout validation; close can complete door tasks without Open being treated as invariant.
- Reuse gaps or changed source files remain missing/technical; they never queue model work or change historical hashes.
- A shared harness update must not invalidate unchanged old model evidence; actual checkpoint/normalization mismatches must still be reported.
- Unknown table_drop mixed with unknown wrong placement stays unknown; definite failure has priority.
- Interruptions preserve attempts and output hashes; new commands never overwrite or traverse into frozen run directories.

## Task1: nine-task semantics and source pipeline

- [x] Add failing CPU fixtures for exact catalog, full-name binding, A/B order, active/invariant values, door-open constraint, moving container region placement and pot reservation slots.
- [x] Implement explicit catalog and source/adapter extensions with versioned metadata, native predicate crosschecks and unchanged physical audit rules.
- [x] Adapt selected preparation to new-three/00/10 while retaining R2 invalidated-ready protection and independent ledgers.
- [x] Run affected source/catalog/adapter fakes; record red/green commands and review diff.

## Task2: Task032 offline scoring and historical input readers

- [x] Add failing fixtures for official00 versus release/drop unknown, event-specific table_drop removal, mixed unknown/failure priority, absent/technical inputs and prior-stage union.
- [x] Implement provenance-bound readers for 03100 and01310, retaining legacy rows, identity and evidence level; no native/model import or output mutation.
- [x] Test relocation/hash rejection, model/source identity retention and source-only reuse records. Record exact results.

## Task3: explicit protocols, nine-task execution and reports

- [x] Add protocol/runtime tests for full official success, invariant preservation, Open-only t0, native00 stopping, retained10 endpoint and policy observation whitelist.
- [x] Add nine planning with fixed90 per condition, new-three30 executable, six60 reuse-only, primary runtime/no90 transfer. Reuse index generated from input roots; no hand-entered hashes.
- [x] Reuse existing `_run_task`, policy/video/evidence and source archive pipeline. Add no-implicit-retry batch/inspect paths with source-level isolation and immutable invocation identities.
- [x] Build report with official00/official10/compliant10 separately; 90 plan vs selected30 vs observed counts, legacy scores/changes and endpoint-specific path coverage.
- [x] Targeted fake integration verifies 120 reuse causes zero native/model calls and only fixed60 new episodes may run, preserving original source identities and outputs.

## Task4: documentation, export and publication

- [x] README/default examples point to nine-task CLI; legacy90 future commands carry cancellation notices. Write full inventory, source preparation, new00/new10 execution, inspect and summarize commands using real flags.
- [x] Provide source-version export manifest/script for future Eval sync after acceptance; do not update Eval now or duplicate method implementation.
- [x] Run focused combined CPU/fake checks and final independent review. No full-suite/GPU/native gate.
- [ ] Commit implementation; write `033_round1.md`, linked `032_round1.md`, STATUS, test evidence and limitations. Push independent PR, verify remote HEAD/tree and reply with link. Do not merge.
