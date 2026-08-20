# P3B-05d Deterministic PRBS9 TX-Injection Waveform Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-05 sub-slice 05d (deterministic PRBS9 TX-injection waveform)
- Status: delivered and cross-checked against an independent reference.
  Maps the P3B-05c PRBS9 bits to a DC-balanced +/- injection waveform.

## Method

Implement prbs9_inject_v1.rs on sipi-link: for each PRBS9 bit emit samples_per_ui
samples of +amplitude (bit 1) or -amplitude (bit 0). Cross-check the product
waveform length, first-16 samples, and sign-packed bytes against independent
Python reproduction across 3 seed/bit/spu/amp cases.

## Result

- 3/3 matched_hash_bound (seed 1/0x1FF, bits 4/20/16, spu 2/4/8).
- sipi-link unit suite 22 tests green (5 new prbs9_inject tests).
- Time-warp jitter/observables/tolerance stay out of scope (owner A4 partial).

## Binding

- Verifier verify_p3b_05d_prbs9_inject.py + 6 tests; crosscheck evidence
  docs/baselines/p3b-05d-inject-crosscheck-evidence.v1.yaml.
- Charter p3b-05d-prbs9-inject-stage.v1.yaml; source map
  p3b-05d-mit-source-map.v1.yaml.
- PLAN **P3B-05d**; ledger note/gate P3B-05; coverage gates 105 -> 106.
