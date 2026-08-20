# PLAN Remaining-Items Ledger

After 30 rounds of evaluation, 14 of 49 PLAN open items have been
verified complete (each bound by a mechanical gate). The remaining 34
items all depend on owner decisions, external assets/oracles,
not-yet-implemented semantics, or are P7 release-gate items unchecked by
design. This audit records the machine-checked ledger that classifies
each remaining item so owner decisions can be targeted precisely.

## Blocker Classification (34 items)

- **owner_decision (8):** P1-04B, P3B-02 (equalizer/Link profile),
  P3B-04, P3B-05, P3C-01, P4A-01, P4B-04 (closure), P7-08
  (retirement approval).
- **external_asset_oracle (6):** P4B-07, P4B-08, P4B-09 (DLL fixture),
  P5-02, P5-06, P5-07 (MATLAB/agent-com material).
- **semantics_not_implemented (12):** P2-06 (generalized compare), P3C-02,
  P3C-03, P4A-02, P4A-03, P4A-04, P4B-02, P5-03, P5-04, P5-05, P5-08,
  P5-09.
- **release_gate (8):** P7-01 through P7-07, P7-09 (unchecked by design
  until release; P7-06 additionally requires candidate rebind).

## Delivered Gate

- `docs/baselines/plan-remaining-items-ledger.v1.yaml` — ledger with all
  35 items, blocker class, state-keeping gate(s), and a note.
- `tools/verify_plan_remaining_items_ledger.py` — verifier for schema
  `sipi.plan-remaining-items.ledger.v1`. It fails closed if the ledger
  item set drifts from the PLAN file unchecked items, any blocker class
  is invalid, or any bound gate file disappears.
- `tools/test_verify_plan_remaining_items_ledger.py` — 5 tests.

## Verification

`python -B tools/verify_plan_remaining_items_ledger.py` returned
`{"items": 34, "schema": "sipi.plan-remaining-items.ledger.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_plan_remaining_items_ledger` passed 5/5.

## Artifact Hashes (SHA-256)

- ledger: `277495E87CC3D7C4E506C5F51B2B9CF9B05CCEA67010B3E980B13E55E3D89C97`
- verifier: `9CBBCFBF55BA6D8B5BF720181BA95BB91068979130741555EEEA846E7E2E589E`
- tests: `6284CD2B3A84AE0B076BC8BCDFF503CE1B65CC56F950F196CD1D63D2068683D4`

## Scope and Non-Claims

- The ledger classifies blockers; it does not complete items, accept
  profiles, or substitute for owner decisions or external assets.
- The gate does not certify any capability or release readiness.