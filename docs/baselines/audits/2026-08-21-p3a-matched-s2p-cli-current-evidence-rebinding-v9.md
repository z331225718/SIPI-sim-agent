# P3A Matched S2P CLI Current Evidence Rebinding V9

Date: 2026-08-21

## Preflight

The v8 verifier now returns `evidence_product_source_drift`: its clean-build
candidate (`c7aebc7`) no longer matches the committed current candidate
`805ebb6b`. The v8 record is retained unchanged as historical evidence.

The pinned external-only source remains available at the authorized Git object
`f6ba0311350fc67bd90fa13b8d578312f956d7e7`, tree
`ac7006ea26cf9e8d885c0e4f1b82797d2e9342a1`, blob
`e10bfb4a43731645984f1f5e24bd3fbf2268dedd`, with content SHA-256
`9d4cfeaad7c971fa45454f639b40e08c538855058f326fbdec64298b8933b5ad`.

## Observation

The existing CLI comparator materialized that exact Git object in two fresh
temporary custody directories, independently computed the standard DFT
observer twice, and built a clean archive of committed candidate
`805ebb6bbaf588dec08685be4eb78a8ce2fff563` with locked offline Cargo
resolution. The bounded `sipi channel run --stdin` response passed the frozen
absolute and relative gates:

- absolute tolerance: `1.0e-9` V/V
- relative tolerance: `1.0e-5`
- max absolute error: `9.792141327392284e-15`
- max relative error: `6.079017923026167e-9`
- max normalized error ratio: `7.789698985496182e-6`
- worst index: `365`

The external report remains outside the repository. The v9 record binds only
its SHA-256 and aggregate facts, plus the committed product trees, Cargo.lock,
and executable identity.

## Boundary

This rebind restores only selected matched-S21 periodic-kernel observed
evidence. Ordinary caller input remains unattested. It does not establish
general Touchstone behavior, reflection or termination, Link/eye/BER,
artifacts, external oracle behavior, or release readiness.
