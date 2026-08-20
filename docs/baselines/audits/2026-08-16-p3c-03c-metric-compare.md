# P3C-03c Profile-Agnostic Metric-Compare Engine - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-03 sub-slice 03c (profile-agnostic metric-compare engine)
- Status: delivered and cross-checked against an independent reference.
  The engine is deliberately profile-agnostic: the specific metric profile
  (P3C-03 C4 owner decision) remains out of scope and unresolved.

## Method

Implement a named-metric compare engine in sipi-compare metric_compare_v1.rs
reusing ToleranceV1/UnitTagV1 from P3C-03a. compile() builds a BTreeMap of
MetricSpecV1 (reference, units, abs/rel tolerance); compare_metric_profile_v1
checks each candidate metric against the absolute-OR-relative tolerance rule,
rejects missing candidates, and reports per-metric allowed error and pass.

## Result

- 4 cross-check points matched an independent reference (allowed-error and
  overall pass/veo/er11 abs-rel combinations).
- sipi-compare unit suite 27 tests green (8 new metric-compare tests).
- Profile-agnostic: no specific metric profile selected (C4 unresolved).

## Binding

- Verifier verify_p3c_03c_metric_compare.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-03c-metric-compare-crosscheck-evidence.v1.yaml.
- Charter p3c-03c-metric-compare-stage.v1.yaml; source map
  p3c-03c-mit-source-map.v1.yaml.
- PLAN **P3C-03c**; ledger note/gate P3C-03; coverage gates 94 -> 95.
