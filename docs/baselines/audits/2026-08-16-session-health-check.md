# One-Command Session Health Check — Audit Record

- Date (UTC): 2026-08-16
- Scope: consolidated health gate `tools/verify_session_health.py`
- Status: delivered; 6/6 checks pass, exit 0

## Deliverable

`tools/verify_session_health.py` (schema `sipi.session-health.v1`) runs the
six top-level state-keeping gates in one invocation and reports a single
health verdict:

1. coverage-gate-sweep — `tools/sweep_coverage_gates.py` (52 gates,
   BAD=0 required; exit-only mode since the sweep reports totals without a
   `valid` key);
2. slice-reference-audit — 9 session slices / 35 files;
3. plan-reference-audit — 138 links, 0 missing;
4. owner-input-request — 13 entries bound to the ledger;
5. remaining-items-ledger — 32 items;
6. open-item-gate-coverage — 49 items / 73 gates.

Exit 0 iff all six pass. Tests `tools/test_verify_session_health.py`: 2
tests (check-list well-formedness; full health run reports valid).

## First-run fix

The initial run flagged coverage-gate-sweep as failed because the sweep
outputs totals and exits 0 only when BAD=0, with no `"valid": true` key;
the health runner now supports an `exit_only` mode per check. Verified:
6/6 checks pass, `failed: 0`, exit 0.

## Usage

`python tools/verify_session_health.py` — the single command that
certifies the whole session state for reviewers, the owner, or CI.
