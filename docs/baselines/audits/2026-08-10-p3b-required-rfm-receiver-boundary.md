# P3B-03b Required RFM Receiver Boundary Audit

## Slice

Commit `8a1fa20` records the user-required
`channel-rfm-block-2-current-drive-v1` profile while preserving the eight
explicitly missing receiver semantic decisions. It adds the product-owned
`sipi.receiver-input.v1` boundary for a finite single-ended receive-voltage
waveform only.

## Evidence

- Decision record: `docs/baselines/channel-rfm-receiver-required-decision.v1.yaml`.
- Receiver readiness record remains `oracle_only`, pins the existing Git-object
  and external-engine evidence, and reports `required_profile_count: 1` with
  eight semantic blockers.
- `sipi.receiver-input.v1` accepts exactly 1024 finite voltage samples,
  `t0=0`, `dt=1e-12 s`, and eight samples per UI. CTLE and FFE are identity
  bypass only.
- P0 boundary, clean-room register, release-license preflight, and Rust source
  map all verified as provisional/fail-closed.

## Independent Review

Orca reviewer response `msg_205c6f3decba` audited `8a1fa20` and found
**0 P1 / 0 P2**. It confirmed the decision/readiness/inventory consistency,
strict receiver input checks, rejection of RFM/current/DFE/CDR/BER fields, and
the absence of a second resolver.

## Verification

- `cargo fmt --all -- --check`
- `cargo clippy -p sipi-contracts --all-targets --locked -- -D warnings`
- `cargo test --workspace --all-targets --locked` (66 tests)
- `tools/test_acceptance_profiles.py`
- `tools/test_verify_channel_rfm_receiver_readiness.py`
- `tools/test_verify_channel_rfm_receiver_required_decision.py`
- P0 verifiers: product boundary, clean-room register, release-license
  preflight, and Rust candidate source map.

## Non-Claims

No RFM engine, current-drive transfer, periodic-kernel causalization, DFE,
CDR, decision, BER, Link parity, default route, or legacy adapter is enabled.
The required profile remains blocked until its independent receiver semantic
contracts are selected and accepted.
