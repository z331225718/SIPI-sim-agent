# AS-01 `fit-sparam` additive v2 audit

This is an additive successor to the immutable `as-01-fit-sparam-direct-port.v1`
record; the historical v1 manifest and verifier are intentionally unchanged.
The current working tree uses the lane-local native vector-fitting metadata
and the hashes recorded in the v2 manifest. This remains a diagnostic,
non-promoted candidate and makes no numerical-parity claim.

The v2 verifier checks the current source/test/Cargo identities and the
`NativeVectorFitting` marker. It does not rewrite or reinterpret the v1
contract. Replay remains preparation-only until a later committed source
binding is available.
