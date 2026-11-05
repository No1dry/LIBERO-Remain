# Task033 R2 source repairs

**Goal:** Address the 25 failed mask10 sources without changing the frozen aedfe169 checkout, the accepted30 normal00 sources, five accepted two-pots10 sources, or historical six-task evidence.

**Architecture:** Extend only explicit R2 construction paths; retain legacy source acceptance, physical limits and rollout/scoring. Add file-only repair planning that selects the reviewed failed indices and preserves original provenance. RGB numerical-policy changes remain proposals until Codex decides them; no failed source is promoted by this delivery.

**Specification:** `collaboration/tasks/033_round2_source_construction_fixes.md`, `collaboration/reviews/033_round2.md`, `033_preparation_findings.json`; R1 interpreter-path repro included. Base aedfe169, fetched main6e43f01, synchronized3cc6d9c in separate worktree/branch `x/task033-r2-sources`.

## Global constraints

- Only drawer0..9, microwave0..9 and two-pots0/2/7/8/9 are repair targets; two-pots1/3/4/5/6 are read-only reuse. Normal00 continues on frozen code and does not wait.
- Never zero velocity, loosen .01 velocity/.005 position/5degree support/150 construction/2x150 replay criteria, alter XML/BDDL, or rewrite historical failure booleans.
- No native simulation/replay/model/extra probe or automatic merge. Use existing saved evidence and bounded CPU/fakes only.
- Keep v4 RGB acceptance unchanged. Investigate sync first; absent a demonstrated sync bug, provide a read-only quantization certificate and explicit minimal v5 proposal, not an activated acceptance policy.

## Tasks and ownership

1. **Drawer geometry:** `construction.py` + `tests/test_task033_r2_drawer.py`. RED90degree In fixture; explicit `placement_candidates(..., in_volume=False)` uses true oriented volume and world gravity, parent collision floor/footprint, rejects walls/unsupported geometry. Default On/legacy behavior unchanged. Parent wires `build._per_goal` to explicit profile flag.
2. **Settling:** `selected_build.py` + `tests/test_task033_r2_settle.py`. Explicit `construction_method` v2, unchanged v1/default/00. Microwave min80/max400 actual HOLD steps, bounded consecutive physical convergence, retain real pose/velocity. Exhaustion preserves failure/trace/step ledger without exporting. R2 seeds retain base qvel, never zero. Drawer R2 profile enables oriented volume.
3. **RGB review:** new read-only diagnostic module/test and `docs/task033_r2_rgb_proposal.md`. Trace snapshot/fresh/reset paths, preserve exact recorded results, check proposal conditions with explicit source hashes/evidence limits. No default threshold mutation, readiness promotion or physical retries. Proposal covers initial/dynamic/reset with consistent certificates and old-reader compatibility.
4. **Bounded handoff (root):** integrate method selector into selected preparation; add repair-plan/prepare CLI targeting only reviewed failures, reuse old five, keep RGB-five review-blocked. Runtime-config interpreter uses non-dereferencing absolute path. Tests prove fixed indices, no old-ready/00 calls, original hashes unchanged, failures/interruptions not silently retried, and venv alias retained.
5. **Delivery:** focused combined tests and independent review; full source-only repair commands, precise RGB decision boundary and limitations in `033_round2.md`; commit/push PR, verify remote head/tree, no merge.

## Review focus

- A vertical wall's upper AABB is not a load-bearing floor; use actual horizontal collision face and adequate footprint.
- Stop conditions inspect actual nonzero qvel; elapsed step80 alone does not authorize transplant.
- GL quantization is an inference from representative saved comparisons, not established for unread frames; certificates cannot promote old failures.
- Readiness loss of a previously accepted source remains missing/failed with old history, never a repair queue entry.
- The new method selector must be bound in continuation identity; no same-directory retries using different construction settings.
