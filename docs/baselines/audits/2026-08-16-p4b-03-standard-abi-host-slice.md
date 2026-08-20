# P4B-03 Standard ABI Host Slice Complete

P4B-03 requires the clean-room Windows x64 standard `long` ABI host:
AMI_Init/AMI_GetWave/AMI_Close exports, bounded buffers, strict status == 1,
and clock sentinel contract. P4B-03a delivered and accepted exactly this
slice (Orca 0 P1/0 P2). This audit records the mechanical gate confirming
the slice stays complete and honest, and marks P4B-03 complete in PLAN.

## Delivered Gate

- `tools/verify_p4b_03_standard_abi_host_slice.py` — verifier for schema
  `sipi.p4b-03.standard-abi-host-slice.v1`. It fails closed if:
  `crates/sipi-ami-host/src/lib.rs` or the acceptance audit disappears;
  any of the three exports (AMI_Init/AMI_GetWave/AMI_Close) is missing
  from the host library; the audit loses its clock-sentinel, status==1,
  or bounds contract tokens; or the audit promotes a vendor
  interoperability claim (it must keep "not a claim of vendor").
- `tools/test_verify_p4b_03_standard_abi_host_slice.py` — 5 tests: live
  validity, exports, audit tokens, no-vendor-claim, and tracking.

## Verification

`python -B tools/verify_p4b_03_standard_abi_host_slice.py` returned
`{"exports": 3, "schema": "sipi.p4b-03.standard-abi-host-slice.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p4b_03_standard_abi_host_slice` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `40D9A116141F0BBC6051E6B2143C260225DFF86AAF5B46D5371C597CD4017B15`
- tests: `4BFAE3417BB9749137BC54291800BBC16EEE30D4B86111C115FA07483ED17D5C`

## Scope and Non-Claims

- P4B-03 covers the ABI host mechanics and mock-DLL conformance only. It
  does not claim vendor DLL interoperability, AMI parameter semantics,
  IBIS+AMI composition, numeric parity, worker isolation, or a default
  CLI route (P4B-07/08/09 remain open).
- The gate does not certify AMI behavior or release readiness.
