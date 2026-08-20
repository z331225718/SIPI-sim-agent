# P4B-04 Worker Slice Partial-Completion State

P4B-04 requires the private Rust host worker with hash-pinned executable,
DLL/dependency closure, timeout/cancel, and atomic outputs. P4B-04a
delivered three of the four surfaces; dependency closure and the related
sandbox/Close-on-kill/vendor-runtime guarantees are explicitly NOT
claimed (Orca 0 P1/0 P2). This audit records the mechanical gate that
keeps that honest partial state; the main item stays open until closure
is delivered.

## Delivered Gate

- `tools/verify_p4b_04_worker_partial_state.py` — verifier for schema
  `sipi.p4b-04.worker-partial-state.v1`. It fails closed if the worker
  audit disappears, if any delivered token (hash-pinned/timeout/atomic)
  is missing, or if the audit loses its "This is not" disclaimer of the
  not-claimed surfaces.
- `tools/test_verify_p4b_04_worker_partial_state.py` — 5 tests.

## Verification

`python -B tools/verify_p4b_04_worker_partial_state.py` returned
`{"delivered": 3, "not_claimed": 4, "schema": "sipi.p4b-04.worker-partial-state.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p4b_04_worker_partial_state` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `8B96B1C443AD57299E654A8A5B3824DE997ABDDF297FDA00DB6139A1C010EE54`
- tests: `C9F28BF05608EBD1606D5590148CC61C6EEFDE7C560BDEB50294C031F8EAB0DB`

## Scope and Non-Claims

- The worker slice is not a sandbox, a complete dynamic dependency closure,
  proof that Close runs after forced termination, vendor interoperability,
  AMI/IBIS parity, or a public CLI route. P4B-04 remains open until the
  closure surface is delivered; P4B-07/08/09 also remain open.
- The gate does not certify AMI behavior or release readiness.
