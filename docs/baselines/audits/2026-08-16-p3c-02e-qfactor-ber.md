# P3C-02e Q-factor / BER Estimator Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02e (Q-factor / BER estimator core)
- Status: delivered and cross-checked against scipy. Implements the owner
  A5 decision (Q-factor estimator, 0.1 dB tolerance policy).

## Method

Implement IEEE 802.3 Q-factor<->BER relations in sipi-com qfactor_ber_v1.rs
using the existing P5-04h erfc/erfcinv cores: ber = 0.5*erfc(q/sqrt2) and
q = sqrt2*erfcinv(2*ber). Add estimate_q_factor_v1 for amplitude/noise. A
cross-check compares the product against scipy.special Erfc/erfcinv.

## Result

- 10 Q<->BER points matched scipy (q in 3.5..7.5, ber in 1e-3..1e-15).
- sipi-com unit suite 158 tests green (8 new qfactor_ber tests).
- Tolerance 0.1 dB recorded as OWNER_TOLERANCE_POLICY_V1 (not an evaluator).

## Binding

- Verifier verify_p3c_02e_qfactor_ber.py + 6 tests; crosscheck evidence
  docs/baselines/p3c-02e-qfactor-ber-crosscheck-evidence.v1.yaml.
- Charter p3c-02e-qfactor-ber-stage.v1.yaml; source map
  p3c-02e-mit-source-map.v1.yaml.
- PLAN **P3C-02e**; ledger note/gate P3C-02; coverage gates 93 -> 94.
