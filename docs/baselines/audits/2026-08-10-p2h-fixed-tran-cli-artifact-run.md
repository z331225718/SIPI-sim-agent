# P2-08 Fixed TRAN CLI Artifact Run Audit

Commit `e67691ae5e7a65e413b6d2b14cef82dbe8369f94` adds the first product CLI
vertical slice:

```text
sipi tran run --stdin --artifact-root <external-root> --artifact-id <id>
```

It accepts only `sipi.tran.rc-pulse-request.v1` with the already accepted
fixed-profile values. The command uses the typed `sipi-tran` library under a
fixed cooperative policy, then publishes `result.json` and `provenance.json`
through the immutable artifact primitive. Only a success manifest is
consumable. The top-level `sipi run` stays unsupported.

The product command has no netlist parser, external fixture/oracle access,
legacy route, Python route, or fallback. Capability discovery reports TRAN as
`limited` for this single profile; it does not claim general TRAN/SPICE.

Verification passed:

- `cargo fmt --all -- --check`
- `cargo test --workspace --locked`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- P0 boundary, clean-room, release-preflight, and Rust source-map verifiers

OMP request `msg_2da06a0efd38`; conclusion `msg_6b914f899c3f`: **0 P1 / 0
P2**.
