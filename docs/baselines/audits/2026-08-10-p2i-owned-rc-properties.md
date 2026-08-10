# P2-05 Owned RC Analytical/Property Tests

Commit `f375b41607ceb815d1fbcba70185fe51f314b8cd` adds a product-authored,
test-only PWL RC case unrelated to the external `rc.cir` fixture. A closed-form
single-RC analytical oracle checks the shared backward-Euler core with a stated
40 mV discretization budget; offset and scale metamorphic tests verify linear
behavior. No fixture, parser, public API, CLI route, or second production
resolver is added.

Verification: `cargo fmt --all -- --check`, `cargo test --workspace --locked`,
and `cargo clippy --workspace --all-targets --locked -- -D warnings` passed.
OMP request `msg_4ca48f8f77cc`; conclusion `msg_ccbe1dd4c3ff`: **0 P1 / 0 P2**.
