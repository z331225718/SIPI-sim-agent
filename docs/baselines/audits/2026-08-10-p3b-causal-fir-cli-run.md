# P3B-02b Causal-FIR Link CLI / Artifact Audit

- Candidate commit: `5656fc4` (`feat: add causal FIR link CLI artifacts`)
- Review request: `msg_ec1836f0b450`
- Reviewer conclusion: `msg_f0e87931124e`, 0 P1 / 0 P2
- Platform: Windows x86_64; no Linux/macOS certification claim.

## Evidence

The slice adds only the exact command
`sipi link run --stdin --artifact-root <external-root> --artifact-id <id>`.
Its strict product-owned `sipi.link.causal-fir-request.v1` request converts to
the existing direct-launch / bypass `LinkPlanV1`, then invokes exactly one
`convolve_causal_fir_v1` call. It records canonical request, received waveform,
and provenance in a sealed immutable artifact.

Validated locally before review:

```text
cargo fmt --all -- --check
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
verify_product_boundary.py
verify_clean_room_register.py
verify_release_license_preflight.py
verify_rust_candidate_source_map.py
```

All commands passed. The CLI test exercises `[1,2] * [3,4] = [3,10,8]`, full
linear tail publication, unknown-field rejection (exit 3), and duplicate
artifact failure without overwrite (exit 5).

## Audit Scope

The reviewer confirmed strict rejection of S2P/Touchstone, periodic kernels,
RFM/current data, termination/reflection inputs, non-bypass CTLE/FFE, receiver
stages, legacy DTOs, and file paths. Limits and numerical failures fail closed
before a success artifact, and provenance contains product digest identities
only. The required RFM receiver remains blocked by its pending owner semantic
charter; this slice does not implement or advertise DFE, CDR, decision, BER,
or selected-profile parity.

## Accepted Scope

P3B-02b is accepted as a product-owned causal-FIR Link CLI/artifact vertical
slice. It is not S2P-to-Link integration, general Channel/Link support,
equalization, receiver behavior, eye/BER parity, default routing, or release
readiness.
