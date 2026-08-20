# P5-02m Deterministic Warning Detector Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02m (deterministic warning detector core)
- Status: delivered and cross-checked against an independent reference.
  Product-side mechanical warnings mirrored from the R480 warning classes
  (P5-02i) without requiring the MATLAB oracle.

## Method

Implement warning_detector_v1.rs: anti-causal detection via pre-cursor energy
fraction (peak_exclusion samples before the peak / total energy), and
high-frequency non-decay detection from the tail magnitude. Cross-check the
product against independent Python references on causal/anti-causal/non-decay
cases.

## Result

- 3/3 matched_hash_bound: fraction exact, anti_causal and non_decay triggers agree.
- sipi-com unit suite 197 tests green (7 new warning_detector tests).
- Explicitly the deterministic subset; the full warning contract (MLSE/DER/CDR)
  remains pending the oracle golden / runtime state.

## Binding

- Verifier verify_p5_02m_warning_detector.py + 6 tests; crosscheck evidence
  docs/baselines/p5-02m-warning-detector-crosscheck-evidence.v1.yaml.
- Charter p5-02m-warning-detector-stage.v1.yaml; source map
  p5-02m-mit-source-map.v1.yaml.
- PLAN **P5-02m**; ledger note/gate P5-02; coverage gates 102 -> 103.
