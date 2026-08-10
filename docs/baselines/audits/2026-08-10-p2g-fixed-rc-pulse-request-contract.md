# P2-08a Fixed RC/PULSE Request Contract Audit

Commit `88d0d8f0925a9bac20cf30939029bb5aa26f865d` adds the product-owned
`sipi.tran.rc-pulse-request.v1` input contract. The request has explicit
resistance, capacitance, initial condition, output grid, and pulse fields, but
accepts only the already certified `tran-rc-pulse-v1` values. Unknown fields,
netlist/path aliases, and any other parameter set are rejected.

The slice introduces no legacy input, oracle access, parser, runtime routing,
or general TRAN claim. It is a strict input boundary for the later `sipi tran
run` vertical slice.

Verification passed:

- `cargo fmt --all -- --check`
- `cargo clippy -p sipi-contracts --all-targets --locked -- -D warnings`
- `cargo test --workspace --locked`
- P0 boundary, clean-room, release-preflight, and Rust source-map verifiers

OMP request `msg_662b72ce4d11`; conclusion `msg_a36bee6411d0`: **0 P1 / 0
P2**.
