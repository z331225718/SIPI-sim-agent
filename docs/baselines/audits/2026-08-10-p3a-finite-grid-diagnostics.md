# P3A Finite-Grid Diagnostics

Commit `1c52f21` adds bounded, informational diagnostics to the clean-room
`sipi-channel` primitive. They report only the supplied finite S-parameter
grid: the largest two-port singular value for sampled passivity, `S12 - S21`
for sampled reciprocity, and the entrywise residual of `S^H S - I` for sampled
losslessness.

The diagnostics neither clip data nor alter the existing matched `S21`
resolver. Overflow or otherwise non-finite intermediate arithmetic is
`indeterminate`, never a passing result. Causality is always
`NotAssessedFiniteBandPeriodicDft`; no finite-grid output is described as a
causality, continuous-band passivity, or physical-realizability certificate.

Product-owned tests cover a matched through, attenuator, active network,
nonreciprocal network, overflow-indeterminate path, Parseval identity, and
resolver non-interference. No external fixture, Touchstone parser, Python,
Link route, or CLI route was added.

Verification passed:

- `cargo test --workspace --locked` (48 Rust tests)
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `tools/run_all_tests.py` (76/76)
- P0 boundary, clean-room register, release-license preflight, and Rust source
  map verifiers (all valid; release remains provisional/not ready)

OpenCode audit `msg_39f9b0967516`: **0 P1 / 0 P2**.

## Non-Claims

This does not certify continuous-frequency passivity, causality, physical
realizability, selected-profile parity, Touchstone support, general Channel or
Link support, or a release/MIT promotion.
