# P3B-03c Receiver Semantics Preparation Audit

## Slice

Commit `48d3841` adds `sipi.receiver-semantics.v1` as a caller-supplied,
fail-closed preparation contract. It records required inputs for a future
receiver algorithm without selecting or executing an algorithm.

## Contract Scope

The contract requires explicit known bits and polarity, finite fixed DFE
coefficients with a cursor, strictly increasing explicit sample indices, and a
bounded BER window with finite threshold. It has no defaults and rejects empty,
non-finite, out-of-range, duplicate, overflow, and unknown-field inputs.

It does not evaluate feedback, recover a clock, make decisions, or compute BER.
The external RFM profile remains `required_blocked_missing_receiver_semantics`.

## Independent Review

Orca reviewer response `msg_90560bba3fa5` audited `48d3841` and found
**0 P1 / 0 P2**. It confirmed the caller-supplied/no-default boundary,
fail-closed validation, absence of a receiver implementation, preserved RFM
semantic blockers, and P0/schema lineage.

## Verification

- `cargo fmt --all -- --check`
- `cargo clippy -p sipi-contracts --all-targets --locked -- -D warnings`
- `cargo test --workspace --all-targets --locked` (70 tests)
- P0 verifiers: product boundary, clean-room register, release-license
  preflight, and Rust candidate source map.

## Non-Claims

This is not a DFE/CDR/BER semantic charter, receiver implementation, RFM
comparison, Link route, or default capability. The next receiver execution
slice requires a profile-specific charter approved by the owner.
