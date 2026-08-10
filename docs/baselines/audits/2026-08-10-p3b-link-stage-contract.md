# P3B-01 Link Stage Contract

Commit `a9c1f4c` adds `sipi.link-plan.v1` as a product-owned typed Link-stage
boundary in `sipi-contracts`. The sole TX stage is `direct_launch`; CTLE and
FFE are both explicit `bypass` stages. All three are identities and introduce
no source impedance, gain, sign change, delay, resampling, or hidden state.

The plan accepts only a zero-origin uniform timebase, finite positive matching
sample intervals, a nonempty finite launched-voltage sequence with exact
timebase length, and a nonempty finite dimensionless causal FIR. It records
the future linear-convolution rule and checked full output length without
implementing convolution or any executor. The finite-band P3A matched S21 DFT
kernel is explicitly rejected as `periodic_kernel`; no causalization is
performed here.

Verification: `cargo fmt --all -- --check`, `cargo test -p sipi-contracts
--all-targets --locked` (14 tests), `cargo clippy -p sipi-contracts
--all-targets --locked -- -D warnings`, `cargo test --workspace --all-targets
--locked` (62 tests), schema baseline/hash checks, and all four P0 verifiers
passed. The product boundary remains provisional; the new product schema and
independent spec remain quarantine/planned clean-room material.

OpenCode audit request `msg_db9fa2c82b66`; conclusion `msg_120cd46bd95d`:
**0 P1 / 0 P2**.

## Non-Claims

This is not a Link executor, convolution implementation, equalizer, receiver,
public CLI route, Touchstone/S2P parser, P3A-to-Link causal conversion, legacy
adapter, Link parity result, or certified runtime.
