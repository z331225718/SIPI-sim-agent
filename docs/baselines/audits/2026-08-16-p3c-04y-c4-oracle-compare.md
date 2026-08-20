# P3C-04y C4 Profile vs MATLAB Oracle Reference Compare - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-03 sub-slice 04y (C4 profile vs MATLAB oracle reference compare)
- Status: delivered and cross-checked against an independent reference.
  First end-to-end P3C-03 profile compare with bound oracle references.

## Method

The owner C4 profile (COM_dB / ICN_mV / ERL, 1% relative tolerance) is bound
to the authoritative MATLAB oracle aggregate reference (P5-06e). The per-case
oracle metric values from the P5-06a evidence (case_metrics) are compared as
candidates using the P3C-03c compare engine (runner binary). An independent
Python reference recomputes the same per-metric allowed error and pass/fail.
The cross-check compares per-metric maps (order-insensitive), failing closed
on any drift.

## Result

- 2/2 matched_hash_bound.
- case_1 and case_2 each compare against their own per-case oracle references; all three metrics pass for both cases.
- Product and independent reference agree on pass and per-metric allowed error.

## Binding

- Verifier verify_p3c_04y_c4_oracle_compare.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-04y-c4-oracle-compare-crosscheck-evidence.v1.yaml.
- Note: compare is now case-level with per-case references; both case_1 and case_2 pass 1% tolerance in this step.
- Charter p3c-04y-c4-oracle-compare-stage.v1.yaml; source map
  p3c-04y-mit-source-map.v1.yaml.
- Oracle reference docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml.
- PLAN **P3C-04y**; ledger/gate under P3C-03; coverage gates 114 -> 115.