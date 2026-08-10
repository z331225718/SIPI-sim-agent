# P3B-03 Fixed Receiver Library Audit

- Candidate commit: `4e10781` (`feat: add fixed data-aided receiver`)
- Review request: `msg_97598976ee85`
- Updated audit anchor: `msg_872c2e789c91`
- Reviewer conclusion: `msg_1a1ff968e093`, 0 P1 / 0 P2

## Accepted Scope

`sipi-link` now provides the single approved, product-owned fixed receiver
primitive. It consumes the already validated `ReceiverInputV1` plus exactly
128 caller-supplied reference bits. The implementation fixes all profile
constants: 8 phase candidates, 32 training symbols, five postcursor taps,
step `0.25`, and a 96-symbol BER window.

The reviewer verified exact phase scoring and margin rejection, normalization,
reference-seeded training, frozen measurement taps, and fail-closed finite
arithmetic. An exact-zero measurement is recorded as an error and erasure,
feeds back `0.0`, and processing continues without changing the denominator.

Validated locally before review:

```text
cargo fmt --all -- --check
cargo test -p sipi-link -p sipi-contracts
cargo clippy -p sipi-link --all-targets -- -D warnings
verify_product_boundary.py
verify_clean_room_register.py
verify_release_license_preflight.py
verify_rust_candidate_source_map.py
```

## Boundaries

The library has no RFM, Python, external engine, CLI, artifact, or default
route. It neither selects nor creates reference bits. The required external
RFM profile remains `required_blocked_missing_authorized_reference_bit_source`;
therefore this acceptance is receiver self-conformance only, not RFM receiver,
Link, DFE/CDR/BER generalization, or release parity.
