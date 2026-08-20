# P6-09 Cross-Crate Negative Integration Gate Complete

P6-09 requires the fixed TRAN→causal-FIR attempt→artifact/report topology
to fail closed on wrong cross-domain edges, record policy drift,
cancel/resource, unstaged staging, and tampered published content, while
keeping positive control verifiable. P6-09a delivered exactly this (Orca
0 P1/0 P2). This audit records the mechanical gate confirming the negative
integration gate is complete and marks P6-09 complete.

## Delivered Gate

- `tools/verify_p6_09_negative_integration_gate.py` — verifier for schema
  `sipi.p6-09.negative-integration-gate.v1`. It fails closed if the audit
  (`2026-08-11-p6-current-topology-negative-gate.md`) or the Rust
  integration test (`crates/sipi-cli/tests/p6_current_topology.rs`)
  disappears, or if the audit loses any of its six fail-closed coverage
  tokens (edge rejection, record policy, pre-cancel, under-budget,
  staging, published payload).
- `tools/test_verify_p6_09_negative_integration_gate.py` — 4 tests.

## Verification

`python -B tools/verify_p6_09_negative_integration_gate.py` returned
`{"fail_closed_surfaces": 6, "schema": "sipi.p6-09.negative-integration-gate.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p6_09_negative_integration_gate` passed 4/4.

## Artifact Hashes (SHA-256)

- verifier: `CB0410F1206833D16F28A7320B0DD1D1C398845AF3D523D87F440299DC5703D6`
- tests: `625762ED0B5A9D056AC9D4A4D66CBBEBB09D08893B179371358C63B21239D286`

## Scope and Non-Claims

- Worker crash remains outside the current P6 topology (P4B mock-worker
  tests cover it separately). Project execution, multi-edge recovery,
  retry/cache, AMI/COM integration, external comparison, and a generic
  fault framework remain open (audit non-claims).
- The gate does not certify project execution or release readiness.
