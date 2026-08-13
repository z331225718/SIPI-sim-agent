# P3C Selected S4P Raw Impulse Diagnostic Audit

- Reviewer: Orca OpenCode read-only reviewer
- Commit reviewed: `2953e77`
- Date: 2026-08-13
- Scope: P3C-04n external exact-grid raw impulse diagnostic evidence; user-owned
  `uv.lock` excluded
- Result: no P1/P2 findings

## Confirmed

- The record preserves two fresh custody runs, distinct manifest identities,
  source/report/runner/product-source hashes, IEEE-754 metric bits, and no
  report retention.
- It explicitly retains unset thresholds and denies causal impulse, passivity,
  repair, direct-port implementation, waveform, P5, and release promotion.
- It describes the observed raw finite-band quadrature only, not a physical
  causality finding or a hindsight threshold gate.

## Follow-up

The review's two P3 hardening suggestions were applied before this audit note:
the evidence retains the full runner/product inventory binding, and it no
longer uses an undefined `material` threshold label. The residual risk is
external-custody trust: the repository preserves identity facts but cannot
recompute the external S4P diagnostic without an authorized source replay.
