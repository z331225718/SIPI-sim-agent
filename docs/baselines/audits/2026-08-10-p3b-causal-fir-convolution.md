# P3B-02a Causal FIR Convolution

Commit `cfddd4b` adds the std-only `sipi-link` crate. Its only operation
consumes the validated `LinkPlanV1` causal FIR boundary and calculates the
specified full linear convolution in deterministic output/kernel order. The
output is a zero-origin, same-interval voltage waveform of length
`Nx + L - 1`.

The primitive checks both output and multiply-accumulate limits before
allocation. Checked size arithmetic, finite product/sum checks, and no-partial
result errors fail closed. Tests cover identity, delay, complete tail,
integer convolution, scaling, output axis, invalid limits, resource limits,
and numeric overflow. No FFT, circular path, causalization, S-parameter
resolver, equalizer, CLI, oracle, or legacy route is present.

Verification: `cargo fmt --all -- --check`, `cargo clippy -p sipi-link
--all-targets --locked -- -D warnings`, `cargo test --workspace --all-targets
--locked` (66 tests), and all four P0 verifiers passed. The new crate is
quarantine/planned clean-room material, and the release boundary remains
provisional.

OpenCode audit request `msg_0ccc98b21801`; conclusion `msg_5dcca173e80a`:
**0 P1 / 0 P2**.

## Non-Claims

This completes only the P3B-02a causal FIR convolution primitive. CTLE and
FFE remain bypass-only and their semantics are not started pending an explicit
Link/equalizer profile. It does not establish P3A S2P-to-Link integration,
Link parity, eye/BER support, a public CLI route, or a certified runtime.
