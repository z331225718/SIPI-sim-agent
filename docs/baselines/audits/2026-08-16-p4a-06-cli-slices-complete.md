# P4A-06 IBIS CLI Slices Complete

P4A-06 wires the accepted IBIS electrical slices as strict stdin CLI
routes. This audit records the mechanical gate confirming all six slices
are complete and bound, and marks the P4A-06 main item complete in PLAN.

## Delivered Gate

- `tools/verify_p4a_06_cli_slices_complete.py` — verifier for schema
  `sipi.p4a-06.cli-slices-complete.v1`. It fails closed if: any of the 6
  CLI routes (`ibis.dc-evaluate`, `ibis.quasi-static-evaluate`,
  `ibis.quasi-static-evaluate-artifact`,
  `ibis.quasi-static-evaluate-artifact-batch`,
  `rx-load.differential-rc-evaluate`, `ibis.inspect`) loses its
  release-publication row binding (available/specified); any of the 5
  conformance-matrix route entries loses its
  `implemented_self_tested` status; or the matrix status drifts from
  `boundary_recorded`.
- `tools/test_verify_p4a_06_cli_slices_complete.py` — 5 tests: live
  validity, publication row shapes, matrix route statuses, matrix
  boundary status, and route-unbinding rejection.

## Verification

`python -B tools/verify_p4a_06_cli_slices_complete.py` returned
`{"routes": 6, "schema": "sipi.p4a-06.cli-slices-complete.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p4a_06_cli_slices_complete` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `596D3C9EAD7F9F74618ADCC8288B33E66AA088967331AAE27368071F48ABC384`
- tests: `94959EBD0E0A6083798623EBA762CB7A91B3E57CC7F84A0A9D61ECF8219B9C9D`

## Scope and Non-Claims

- P4A-06 covers the CLI wiring of the accepted DC/quasi-static/differential
  R-C slices only. It does not implement or claim I-V/V-T/ramp/package
  semantics, general IBIS electrical evaluation, or external caller-input
  acceptance (those remain open as P4A-04 and P4A-06 tail notes).
- The gate does not certify IBIS behavior, transient parity, general IBIS
  compatibility, or release readiness; routes remain specified/non-oracle.
