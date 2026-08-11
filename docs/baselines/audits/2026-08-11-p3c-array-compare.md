# P3C-02a Strict Array Comparison Substrate

This slice adds the product-owned `sipi-compare` crate. It accepts only
caller-aligned finite arrays with exact shape, canonical unit tag, and opaque
semantic-binding identity. The sole numeric rule is directional
reference-to-candidate absolute-plus-relative tolerance with both terms
explicit and finite.

Construction and comparison reject missing inputs, malformed shape/unit/binding,
non-finite values, identity mismatches, and overflowing comparison arithmetic
without producing a normal mismatch report. Reports retain only aggregate
metadata and canonical SHA-256 input identities. In particular, `-0.0` and
`+0.0` intentionally compare equal while retaining distinct identities.

Product-owned tests cover exact and boundary tolerance behavior, zero
reference, negative values, structural mismatch, non-finite inputs, malformed
tokens, arithmetic overflow, deterministic reports, and the signed-zero
identity distinction. No external profile, golden array, CLI route, artifact,
or resolver is involved.

One Orca reviewer (`term_ac58e303-f0a2-4fd5-b5b7-b8e7c119e832`) audited the
staged slice and reported **0 P1 / 0 P2**. It independently confirmed the
directional rule, explicit tolerance admission, signed-zero identity behavior,
the absence of I/O/oracle/domain paths, the five focused tests, workspace
clippy, and all P0 verifiers.

## Non-Claims

This is P3C-02a only. Eye, jitter, bathtub, channel execution, profile parity,
external comparison, and `sipi compare` remain unavailable.
