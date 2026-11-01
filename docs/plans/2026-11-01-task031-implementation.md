# Task031 implementation plan

Authority: `collaboration/tasks/031_normal00_control_and_missing_two_tasks.md` and its known-source JSON. Baseline: `c6dc98de0c54517c976057598b60f4cedf7fa3e5`; branch `x/task031-normal00` merges main documentation at `3c4daf7` without changing approved code.

## Global constraints

- Only CPU/file/fake checks. No real simulator/reset/restore/replay/model/train/eval or dataset jobs.
- Preserve original artifacts, failed audits, old80 mask10 outputs and historical PRs. No merge. Independent PR to LIBERO-Remain.
- Normal00 has explicit protocol/source/result identity and initial-only acceptance. Actual initial00, finite state, initial observation correspondence and physical checks remain mandatory; no extra150 hold or all-mask gate. Preserve original aggregate diagnostics.
- Selected10 is limited to frypan_stove9 and cabinet_close_top_bowl, sources0..9, construction150 and independent replay2x150; fixed physical/RGB limits and hold unchanged. No replacement indices or model-conditioned selection.
- Seed7, chunk8, horizon520, five endpoint observations, original full instruction/SOG10 input/checkpoint and videos unchanged. Initial preservation is N/A only for00. Existing10 semantics remain strict by default.
- Every composite source retains its own original manifest raw/content hash, audit/replay dependencies and hashes. Per-source missing/failed is technical, never model failure. No invented original whole-bank pass.
- First80 normal00 is independent of two missing tasks; then20 normal00 and20 selected10. New model budget120. Preparation never chains evaluation.

## Shared interface

New file-only `headless/scoped_sources.py` exports `resolve_source(protocol, task, index, origin)` and `validate_snapshot(directory, plan)`, `archive_source(directory, plan)`. Protocol names: `normal00-control` and `selected-mask10`. A ready plan uses existing source-plan shape with a single `episodes` entry, `source_plan_sha256`, explicit `protocol`, original `manifest`, immutable `source`, `source_acceptance`, `environment_config`; selected artifact copies live in `source/manifest_files` and optional `source/replay_files`. All archived paths are relative and contained. `archive_source` returns the archived manifest root; validation never consults live origins.

An origin is `{manifest, manifest_sha256, content_hash, candidate_replay?, replay_sha256?, initialization?, initialization_sha256?}`. Normal00 requires recorded initialization provenance (original/new construction report) rather than guessed wait steps. Paths are resolved by config loader. State/audit/observation hashes live in accepted evidence, revalidated from original bytes. A selected candidate-only validator is available to preparation as `inspect_candidate(task,index,manifest_path)`; no replay means missing replay, not missing candidate. Exact function return shapes are documented in implementation report before dependent integration.

## Tasks

1. **Sources**: per-index strict selected10 acceptance retaining old all10 wrapper; separate initial-only00 acceptance; immutable portable snapshots; candidate inspection. Own source_acceptance.py/scoped_sources.py and dedicated source tests. Validate t0 independently, do not forge shortened passing old audit. Fixed threshold pinning for new path.
2. **Runtime**: explicit normal protocol/schema/runner/environment/evidence/metrics support using shared internals with legacy strict defaults. Expose protocol-aware validation/analysis dispatch for new workflow. Preservation null/applicability explicit. Native wrong initial mask classified technical invalid. Own existing runner/schema/environment/evidence/metrics and runtime tests; no source/workflow edits.
3. **Preparation**: separate versioned selected10 and normal00 native producers plus bounded per-source orchestration/ledger. File-only inspect default; exact fixed tasks/indices; reuse validated candidates, replay only missing evidence, preserve failed evidence, explicit continuation/new outputs. Own new selected_preparation.py/selected_build.py/selected_replay.py and preparation tests; no existing build/replay semantics changed.
4. **Integration**: new composite config/plan/batch/CLI with frozen denominators, scope populations80/20/100, per-source archive/run/read and explicit continuation. Reuse existing policy/evidence/video/scoring helpers. Parent owns integration, docs/examples and handoff. File-only/fake round trip, per-source isolation, hash rejection, no duplicate runs, whitelist.
5. **Review and delivery**: scoped source/runtime/preparation task reviews, integration/final strongest-model review, fix concrete findings, relevant regression tests, implementation commit,031 reply/status, independent PR and remote tree verification.

## Review rulings

Use parallel implementers for disjoint files with the shared interface above; serialize integration into their public interfaces. Preserve local review records instead of deleting history. The task's bounded CPU/fake scope overrides generic full-suite requests. User already authorized implementation and GitHub handoff; no additional approval gate is needed. Native readiness and physical fault diagnosis remain for user-run artifacts and external Codex review.
