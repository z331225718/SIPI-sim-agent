# P4A-05 Conformance Matrix and Unsupported Boundary Complete

P4A-05 requires the public/product fixture set, the malformed/unsupported
matrix, and the oracle compare. This audit records the mechanical gate
confirming all three are in place and marks P4A-05 complete.

## Delivered Facts

- `docs/baselines/p4a-ibis-conformance-matrix.v1.yaml` is
  `boundary_recorded` with 19 entries: 1 external-profile-accepted DC
  scope, 12 implemented_self_tested product-owned slices, 5 unsupported
  surfaces (non-input models, non-typical corners/PVT, package/pin/VT/
  ramp/network, AMI/algorithmic model, file/URL/default route), and 1
  not_assessed (generic IBIS certification).
- The matrix verifier (`verify_p4a_ibis_conformance_matrix.py`) rejects
  promotion, external paths, and unsupported-route exposure (fail-closed).
- Oracle compare: P4A-04d two-fresh-custody external compare evidence is
  recorded in
  `docs/baselines/audits/2026-08-11-p4a-ibis-input-typ-static-compare.md`.

## Delivered Gate

- `tools/verify_p4a_05_conformance_matrix_complete.py` — verifier for
  schema `sipi.p4a-05.conformance-matrix-complete.v1`. It fails closed
  if the matrix schema/status drifts from boundary_recorded, the accepted
  profile disappears, any of the 5 required unsupported entries is
  missing or misclassified, or the oracle-compare audit disappears.
- `tools/test_verify_p4a_05_conformance_matrix_complete.py` — 6 tests.

## Verification

`python -B tools/verify_p4a_05_conformance_matrix_complete.py` returned
`{"entries": 19, "schema": "sipi.p4a-05.conformance-matrix-complete.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p4a_05_conformance_matrix_complete` passed 6/6.

## Artifact Hashes (SHA-256)

- verifier: `5B1959CB44B8B3CF5435B32EAB2DAC0A2F49A70E412ED3672A00D066064D2FF1`
- tests: `F9F9B5724197122551E1BDA3C069D566F6060ABD0BD2262AB2B98F2CE1537CB3`

## Scope and Non-Claims

- This completion covers the current IBIS Input/TYP DC surface. V-T/ramp/
  package semantics, AMI behavior, transient parity, generic IBIS
  certification, and external caller-input acceptance remain unsupported
  or not-assessed per the matrix (P4A-04 and general IBIS work stay open).
- The gate does not certify IBIS behavior, compatibility, or release
  readiness.
