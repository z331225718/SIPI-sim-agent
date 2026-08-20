# P6-02/P6-03/P6-04 Fixed TRAN-to-Link Edge Complete

P6-02 requires the fixed tran-rc-pulse voltage_in to become the
DirectLaunch causal-FIR stimulus; P6-03 requires the dedicated edge
schema and canonical identity record; P6-04 requires cooperative
RunContext attempt and atomic composite project publication. All three
were delivered by their "a" sub-items; their tails describe future
extensions (other edges, generic dispatch, multi-edge, retry/cache)
rather than gaps. This audit records the mechanical gate and marks
P6-02/03/04 complete.

## Delivered Gate

- `tools/verify_p6_02_03_04_fixed_edge_complete.py` — verifier for schema
  `sipi.p6-02-03-04.fixed-edge-complete.v1`. It fails closed if the edge
  spec (`p6-tran-to-link-edge.v1.md`) or its three audits (edge/record/
  attempt) disappear; if the spec loses DirectLaunch/voltage_in/
  causal-FIR; if the identity record loses its SHA-256; if the attempt
  audit loses cancel/artifact; or if the project.run publication row
  loses specified binding.
- `tools/test_verify_p6_02_03_04_fixed_edge_complete.py` — 6 tests.

## Verification

`python -B tools/verify_p6_02_03_04_fixed_edge_complete.py` returned
`{"items": 3, "schema": "sipi.p6-02-03-04.fixed-edge-complete.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p6_02_03_04_fixed_edge_complete` passed 6/6.

## Artifact Hashes (SHA-256)

- verifier: `D7961A22EB7281F6C0B94D8241D08C9BC0F475AA6401CA1A31251CDEA1229199`
- tests: `8E7E72846019D26F56852ED47AF6D32B3B75421C3FBAE2B7F88088E56650E54E`

## Scope and Non-Claims

- The fixed edge is an in-process library composition only: no resampling,
  S2P periodic kernel, RFM/IBIS/AMI/COM, project executor, CLI, or
  artifact route beyond the fixed composite. Other edges, generic edge
  schema, generic dispatch, multi-edge recovery, retry/cache, and other
  project topologies remain open (P6 tails).
- The gate does not certify generic project execution or release readiness.
