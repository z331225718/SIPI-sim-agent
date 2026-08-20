# P3C-03d dB-Domain 0.1dB Tolerance Pass/Fail Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-03 sub-slice 03d (dB-domain tolerance pass/fail core)
- Status: delivered and cross-checked against an independent reference.
  Binds the owner A5 0.1 dB tolerance decision as a product constant.

## Method

Implement db_tolerance_check_v1 in sipi-com db_tolerance_v1.rs: absolute
difference in the dB domain |candidate - reference| <= tolerance, with a
relative epsilon to keep the boundary inclusive against float error. A
cross-check compares product passes against an independent Python reference
across 6 (ref, candidate, tolerance) triples including the float boundary.

## Result

- 6/6 matched_hash_bound (incl. 1.1-1.0 boundary and 0.0 ref).
- sipi-com unit suite 185 tests green (7 new db_tolerance tests).
- OWNER_DB_TOLERANCE_V1 = 0.1 binds the owner A5 decision.

## Binding

- Verifier verify_p3c_03d_db_tolerance.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-03d-db-tolerance-crosscheck-evidence.v1.yaml.
- Charter p3c-03d-db-tolerance-stage.v1.yaml; source map
  p3c-03d-mit-source-map.v1.yaml.
- PLAN **P3C-03d**; ledger note/gate P3C-03; coverage gates 99 -> 100.
