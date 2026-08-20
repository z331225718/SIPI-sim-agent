# P3B-05c Deterministic PRBS9 Sequence Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-05 sub-slice 05c (deterministic PRBS9 sequence core)
- Status: delivered and cross-checked against an independent ITU-T O.150
  PRBS9 reference; seed-replay deterministic; injection / time-warp units /
  observables / tolerance remain out of scope (fail-closed).

## Method

Implement the PRBS9 x^9+x^5+1 LFSR (ITU-T O.150 / IEEE 802.3 family) in
sipi-link prbs9_v1.rs: 9-stage register, output bit 8, feedback bit8^bit4
into bit 0, seed 0b000000001 (owner A4 decision). Expose next_bit,
next_bytes (LSB-first packing), state()/restore() for seed replay and
checkpointing, and emitted_bits(). An independent Python LFSR written from
the standard definition cross-checks the product stream.

## Result

- seed 0x001, 1000 bits: product first_16 [0,0,0,0,0,0,0,0,1,0,0,0,0,1,0,0]
  matches the independent reference; stream sha256 dc956adf... matches.
- sipi-link unit suite 17 tests green (7 new PRBS9 tests).
- Deterministic regeneration and checkpoint-restore verified by Rust tests.

## Binding

- Verifier verify_p3b_05c_prbs9_sequence.py + 6 tests; crosscheck evidence
  docs/baselines/p3b-05c-prbs9-crosscheck-evidence.v1.yaml.
- Charter p3b-05c-prbs9-sequence-stage.v1.yaml; source map
  p3b-05c-prbs9-mit-source-map.v1.yaml.
- PLAN **P3B-05c**; ledger note/gate P3B-05; coverage gates 90 -> 91.
