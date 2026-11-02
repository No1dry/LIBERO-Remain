# Task033 R5 microwave construction plan

> Execute the approved R5 work order with disjoint geometry/builder work and a parent-owned narrow queue; independent review before delivery.

**Goal:** Improve physical candidate seeds for the ten failed microwave sources while reusing the twenty accepted sources.
**Spec:** `collaboration/tasks/033_round5_microwave_candidate_construction.md` and its R5 review/findings JSON.
**Architecture:** A pure geometry module computes actual collision support and gravity-aligned yaw candidates; an explicit microwave-only method reuses R2 settling/auditing unchanged. A small sequential CLI wraps existing selected_preparation, gating all remaining work on source0 readiness.
**Tech stack:** Existing Python/NumPy/pytest; no dependencies or native experiments.

## Constraints

- New method `microwave_gravity_support_pose_transplant_v3`: only nine-mask10/mug_microwave_close, official indices0..9, explicitv6.
- Actual floor and mug collision boxes, margins/contact parameters unchanged. Recompute geometry after every orientation; only A free-joint position/quaternion seed may change, all seed qvel retained.
- Keep base80, candidate80..400, continuous20, qvel0.01,24 candidates,150 construction and paired300. Preserve measured final quaternion/qvel.
- Reuse old20 and certificates; old00/old six/model/score untouched. New output only; no native experiment, no automatic merge.
- Source0 is the first real source, not an extra probe. If not truly ready, stop indices1..9, retain failure/not-attempted distinction. No partial20 eval.
- Frozen06817e61 v6 reader must accept new valid artifacts; no reader changes without a demonstrated compatibility need.

## Tasks

1. Geometry owner: inspect pinned XML, write RED CPU geometry tests, add `microwave_candidates(base,model,data,*,max_candidates=24)`, GREEN. Own new module and geometry tests; leave accepted generic construction unchanged.
2. Builder owner: add explicitmethod dispatch and metadata with no settle relaxation, RED/GREEN fake producer tests and frozen-reader compatibility. Own selected_build and builder tests.
3. Parent: bind newmethod scope in selected_preparation, add narrow `repair033_microwave prepare --inventory --preparation-report --out [--continue]`; hash-pin real report/sources, reuse20, first-source gate, immutable attempts, complete combined inventory. RED/GREEN queue tests.
4. Independent review of geometry transforms/support/contact-margin treatment, whitelist/quat/qvel retention, first-source gate, frozenreader compatibility. Only affected CPU/fake, not53/234/280 groups.
5. Commit code, `responses/033_round5.md` and complete command runbook; push existingPR14 and verify. Physical efficacy remains pending user execution.

## Evidence boundary

R5 recorded evidence proves persistent velocity/nonconvergence, not a complete contact root cause. Gravity support and posture diversity are a testable geometric improvement, not proven physical success. Do not claim all server raw was read locally or that ten sources are ready.
