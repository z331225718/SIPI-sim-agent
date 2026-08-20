# P3C-02f Bathtub Opening-Width Estimator Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02f (bathtub opening-width estimator core)
- Status: delivered and cross-checked against an independent reference.
  Builds on the P3C-02e Q-factor/BER core (owner A5 decision).

## Method

Implement bathtub_opening_width_v1 in sipi-com bathtub_v1.rs: from a
strictly-ascending V-shaped BER-vs-time set, find the contiguous span where
BER <= target and interpolate the left/right target-BER crossings linearly
in log10(BER). Cross-check against an independent Python reference on 3
cases (symmetric, asymmetric, no-opening).

## Result

- 3/3 matched_hash_bound: widths 0.833333... and 0.79 exact; error set
  includes NoOpening (compared by presence, not Rust/Python spelling).
- sipi-com unit suite 172 tests green (7 new bathtub tests).

## Binding

- Verifier verify_p3c_02f_bathtub.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-02f-bathtub-crosscheck-evidence.v1.yaml.
- Charter p3c-02f-bathtub-opening-stage.v1.yaml; source map
  p3c-02f-mit-source-map.v1.yaml.
- PLAN **P3C-02f**; ledger note/gate P3C-02; coverage gates 97 -> 98.
