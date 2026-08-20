# P4B-04 Owner Decision: DLL/Dependency Closure Not Committed — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-04 main item decision-closure
- Status: decision-closed (NOT implemented-complete)

## Decision

The owner, via interactive session instruction ("2、不承诺"), decided NOT to
commit the DLL/dependency-closure surface of P4B-04. The main item is closed
by owner decision (decision-closed), not by implementation completion.

## Delivered surface (unchanged)

- P4B-04a: Windows x64 one-job private worker + test-only supervisor —
  hash-pinned, job-root-contained inputs; atomic artifact publication;
  parent-timeout recovery only (no sandbox, no Close-on-kill, no full dynamic
  dependency closure, no real vendor runtime claims). Audit:
  `docs/baselines/audits/2026-08-11-p4b-ami-private-worker.md`.
- P4B-04b: worker partial-state gate `sipi.p4b-04.worker-partial-state.v1`
  (`tools/verify_p4b_04_worker_partial_state.py`) mechanically fixing the
  delivered three elements: hash-pinned execution, parent-timeout recovery,
  atomic artifact publication. Audit:
  `docs/baselines/audits/2026-08-16-p4b-04-worker-partial-state.md`.

## Explicitly NOT committed

sandbox isolation; Close-on-kill; full dynamic dependency closure; real
vendor runtime. Any future claim of these requires a fresh owner decision and
new evidence.

## Bookkeeping

- PLAN.md P4B-04 row: `- [x]` with `**P4B-04c 已完成（owner decision:
  DLL/dependency closure not committed）**` note.
- `docs/baselines/plan-remaining-items-ledger.v1.yaml`: P4B-04 entry removed,
  `total_open` 34 → 33 (verifier `tools/verify_plan_remaining_items_ledger.py`
  asserts 33; ledger test updated).
- Gate coverage `tools/verify_plan_open_items_gate_coverage.py` keeps P4B-04
  mapped (49 items / 66 gates unchanged) so the partial-state gate stays
  covered against regression, matching the completed-item convention.
- Gate verifier for P4B-04 ledger entry removed with the entry; the gate file
  itself remains tracked and covered.

## Verification

`python tools/verify_plan_remaining_items_ledger.py` → valid, 33 items.
`python tools/verify_plan_open_items_gate_coverage.py` → valid, 49 items /
66 gates. unittest suites for both verifiers: 9 tests, all passed.
