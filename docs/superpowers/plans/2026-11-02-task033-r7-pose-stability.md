# Task033 R7 Pose Stability Implementation Plan

> Execute the user-approved R7 work order with disjoint implementation owners and an independent final review; do not request the same design approval again.

**Goal:** Add explicit A-mug pose-stability source admission while preserving R5 geometry, old evidence and twenty accepted origins.
**Architecture:** A pure stability module supplies compiled-joint binding and pose-window calculations to the live auditor, bounded settling and offline reader. Optional `stability_profile` travels independently of RGB v6 through the existing producer/preparation/replay path. A narrow R7 CLI reuses the R5 queue and binds the reviewed R5 failure report.
**Tech stack:** Existing Python/NumPy/pytest; no dependency changes or native experiments.
**Spec:** `collaboration/tasks/033_round7_pose_stability_revision.md` and `collaboration/reviews/033_round7.md`.
**Baseline:** `9f70255` after fetching main `28aed1d` and merging its docs; historical STATUS entries retained.

## Global constraints

- Explicit `stability_profile=active-free-object-pose-stability-v7`; `observation_profile=named-uint8-rgb-one-level-v6` remains separate.
- Only nine-mask10/mug_microwave_close/official indices0..9, active white_yellow_mug_1.
- Full150 control steps/151 observations: A bbox-diagonal span<=.005m and maximum pairwise quaternion shortest angle<=1degree; normalized q/-q equivalent. A qvel raw and exceedance/peak diagnostics retained, non-A qvel<=.01.
- Keep all prior predicates/Open, whole-scene position, robot/reference, penetration<=.002m, RGB/non-RGB/state/hash checks; construction150 and independent paired150+150.
- No qvel edits, candidate-count/wait increase, geometry changes, hidden old-reader acceptance, native work, model/score changes or auto merge.
- Preserve old20/old six/00 and historical failed/raw. First0 gates1..9. Only complete30 permits a later user-started single30 model batch.

## Shared interfaces

`stability.PROFILE`, `AUDIT_SCHEMA=remaining-goals-validation-v2-active-pose`;
`binding_from_model(model, model_xml_sha256)`, `validate_binding(binding, model_xml_sha256=None)`,
`validate_scope(episode)`, `sample(state,qvel,binding)`, `pose_window(samples)`.
Live snapshots carry `stability_binding` recomputed from the compiled model; episode/audit bind the same mapping and XML hash. Raw state/qvel and derived A pose must agree. Unknown/missing metadata fails closed.

## Tasks and review focus

- [x] Core owner: write RED then GREEN `tests/test_task033_r7_stability.py`; add `stability.py`, opt-in `validation.py` branch. Test q/-q, zero/malformed quaternion, full-window pairwise angle/position, A high velocity versus non-A, mapping/layout/state mismatch, missing151 evidence and other physical/observation failures. Legacy profile stays unchanged.
- [x] Producer owner: RED/GREEN `tests/test_task033_r7_producer.py`; modify `selected_build.py`, `build.py`, `selected_replay.py`, `replay_candidates.py`. Resolve actual compiled mapping at construction and each formal restore, pass independent profile, preserve all raw evidence, use same pose calculation for20-observation convergence, keep budgets. Exercise actual file production/audits with fake physics, not mock-only metadata assertions.
- [x] Reader owner: RED/GREEN `tests/test_task033_r7_reader.py`; update `headless/source_acceptance.py`, `rgb_revalidation.py`, `scoped_sources.py` only as needed. Recompute source checks from raw151+151+151 windows. Reject unknown/downgraded profile, missing/changed mapping and incomplete replay; oldv6 and old certificates retain old interpretations. New audit schema prevents frozen06817 from mistakingv7 forv6.
- [x] Parent: RED/GREEN `tests/test_task033_r7_queue.py`; opt-in profile in `selected_preparation.py`, reuse `repair033_microwave.py` with a narrow `repair033_pose_stability.py` CLI. Keep pinnedR3 inputs/20 origins and bind immutableR5 failure report hash. New output/version/continuation identity, first-source stop, old output overlap and no native dispatch to old20.
- [x] Review final diff and run only new/affected CPU/fake checks. Independent reviewer checks cross-file profile propagation, actual mapping, no old reinterpretation, complete evidence and continuation. Do not rerun historical full suites or expand geometry tests.
- [ ] Commit implementation, `collaboration/responses/033_round7.md`, STATUS and complete isolated-deployment/user-command runbook; push PR14 and verify remote commit/tree, leave unmerged. Report physical readiness as pending user execution.

## Evidence boundary

The R5 recorded tail contains150 samples/149 control intervals, not a formal150-step audit, and lacks full states/contacts. It justifies the approved post-preparation measurement revision, not retroactive readiness. The new profile must be disclosed and frozen before the30 model episodes, without selecting sources by VLA outcomes.

## Execution record

Final new R7 aggregation: 95 passed in17.10s. Affected old validation71, producer/replay50, reader/certificate24 and R5 queue8 passed in the component checks; no full repository run. Root caught a new settle comparator stricter than v6 dynamic1e-8 and a signed-zero refresh gap; three RED/GREEN cases fixed them without changing step0 or physical limits. Independent delta review has no unresolved findings. Physical source readiness remains unproven pending user execution.
