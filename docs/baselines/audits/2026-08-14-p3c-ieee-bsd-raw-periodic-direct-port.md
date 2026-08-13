# P3C IEEE BSD Raw Periodic Direct-Port Audit

- Reviewer: Orca OpenCode read-only reviewer, reused existing terminal
- Commit reviewed: `6ef89ae`
- Date: 2026-08-14
- Scope: P3C-04q BSD raw-periodic inverse-transform direct port; user-owned
  `uv.lock` excluded
- Result: 0 P1 / 0 P2

## Confirmed

- The direct port is restricted to the selected `s21_to_impulse_DC.m`
  Hermitian, inverse-transform, and time-base leaf; interpolation, causality,
  delay, truncation, pulse construction, and convolution remain excluded.
- Endpoint projection and inverse imaginary residual have fixed fail-closed
  absolute-plus-relative bounds. The positive-sign `1/N` inverse, unshifted
  full-period time axis, direct-value oracle, and Parseval behavior are covered
  by tests.
- The output remains explicitly `raw periodic`, not causal FIR, ADS/COM parity,
  or acceptance. Causality, delay, passivity, waveform, receiver, P4B, P5, and
  release gates remain false.
- SPDX, NOTICE, source map, source identity, clean-room scope, product boundary,
  and license preflight are consistent. The commit excludes `uv.lock` and all
  user-owned pending Rust edits.

## Residual Risk

This is core-only evidence. The selected external S4P has not yet been replayed
through the raw transform, and raw periodic output cannot enter a causal or
candidate waveform route without separate causality, delay, and convolution
policy/evidence.
