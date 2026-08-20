# P3C-02g Horizontal Time-Margin Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02g (horizontal time-margin estimator core)
- Status: delivered and cross-checked against an independent reference.
  Composes the P3C-02f bathtub opening with a sampling-point offset.

## Method

Implement compute_horizontal_margins_v1 and margins_from_bathtub_v1 in
sipi-com horizontal_margin_v1.rs. A cross-check runs sym/off-center/outside
bathtub cases and compares eye width, left/right margins, and the error set
against an independent Python reference.

## Result

- 3/3 matched_hash_bound: sym eye 0.833333..., left 0.5, right 0.333333;
  asymmetric 0.79 exact; outside reports NonPositiveEyeWidth (no opening).
- sipi-com unit suite 178 tests green (6 new horizontal_margin tests).

## Binding

- Verifier verify_p3c_02g_horizontal_margin.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-02g-horizontal-margin-crosscheck-evidence.v1.yaml.
- Charter p3c-02g-horizontal-margin-stage.v1.yaml; source map
  p3c-02g-mit-source-map.v1.yaml.
- PLAN **P3C-02g**; ledger note/gate P3C-02; coverage gates 98 -> 99.
