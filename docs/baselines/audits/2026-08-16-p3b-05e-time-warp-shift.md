# P3B-05e Deterministic Time-Warp Shift Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-05 sub-slice 05e (deterministic per-sample time-warp shift core)
- Status: delivered and cross-checked against an independent reference.
  Builds on the P3B-05d injection waveform basis; the jitter/time-warp model
  that generates shifts, the units model, observables, and tolerance remain
  owner-decided and are NOT implemented (fail-closed; P3B-05a rejection
  surface in force).

## Method

Implement time_warp_v1.rs on top of P3B-05d/05c: time_warp_shift_v1 applies a
caller-supplied per-sample shift vector (sample units) to a sampled waveform
by linear interpolation on the same sample grid. For output sample n the
source position is p = n + shift[n]; the output is the linear blend of the
two nearest input samples (identity when integral). Fail-closed: empty input,
length mismatch, non-finite sample/shift, or an interpolation stencil leaving
[0, len-1] are hard errors; there is no zero-padding, wraparound, or
extrapolation guess. Cross-check compares the product path (runner binary)
against an independent Python reference with identical rules across 10
scenarios, matching ok/error/output-samples exactly.

## Result

- 10/10 matched_hash_bound (zero-identity; half-midpoint; quarter-ramp; PRBS9
  waveform with small shifts; backward 0.5 shift; out-of-domain forward and
  backward; length mismatch; non-finite shift; empty waveform).
- sipi-link unit suite 29 tests green (7 new time_warp tests).
- Deterministic linear-interpolation only; no jitter/noise/tolerance/
  observables semantics.

## Binding

- Verifier verify_p3b_05e_time_warp.py + 6 tests; crosscheck evidence
  docs/baselines/p3b-05e-time-warp-crosscheck-evidence.v1.yaml.
- Charter p3b-05e-time-warp-stage.v1.yaml; source map
  p3b-05e-time-warp-mit-source-map.v1.yaml.
- PLAN **P3B-05e**; ledger note/gate P3B-05; coverage gates 107 -> 108.
