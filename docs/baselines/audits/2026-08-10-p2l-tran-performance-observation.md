# P2-09a Fixed TRAN Performance Observation

Commit `1864aca` adds a Windows-only, external measurement gate for the
accepted `tran-rc-pulse-v1` CLI request. It builds on P1-11's installed Rust
binary rather than the source tree, uses an empty external working directory
and fresh artifact root for every invocation, and records only report hashes
and metrics outside the workspace.

The executed observation used the P1-11 binary for `f1272d34b33dfafc16c42bfa0ab6e492a01a5878`,
with Cargo lock SHA-256 `d32292646f3c36d10197db89828b4a4a952083316813bad151f5fffe7bac2a70` and executable SHA-256
`741f89d95e2ea452c1597e6f13a268b4c1d9614c10c2dc69ce4eb5578106adb6`.
It completed three warmups and ten measured runs. The external report bound
one request hash and identical success/result/provenance hashes across every
measured sample. Its observed median wall time was `17,179,700 ns`; observed
median `PeakWorkingSetSize` was `4,190,208 bytes`.

`performance-budget.v1` remains `pending`: ordinary preflight accepted the
complete observation report, while `--release` rejected it with
`owner_budget_pending`. No performance threshold or RSS budget was inferred.

Verification: new Python contract tests (3/3), P1-11 locked build/install
gate, the actual 3+10 external observation, Rust workspace tests (48),
format/clippy, and all four P0 verifiers passed.

OMP request `msg_3f65283f646e`; conclusion `msg_589a3cdbcd54`: **0 P1 / 0 P2**.

## Non-Claims

This is one host's fixed-profile observation, not an owner-approved budget,
performance pass, generic TRAN benchmark, RSS limit or enforcement result,
hard resource guarantee, or Windows certification.
