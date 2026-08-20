# P7-08 Retirement Approval Record Template

P7-08 requires owner retirement approval before any legacy path can be
deleted. The replacement map (P7-08a) and the drift-gate retirement
strategy (P7-08b) are prepared and mechanically verified. This audit
records the final owner decision artifact: a signed record that, once
filled by the owner, satisfies the `owner_retirement_approval` gate.

## Delivered Artifacts

- `docs/baselines/p7-08-retirement-approval-record.v1.yaml` — TEMPLATE
  (`approval_state: pending_owner_signature`, approved_by/at null). It
  binds the exact replacement-map SHA-256
  (`CB1E60FD...`) and drift-gate strategy SHA-256
  (`0B0FE37D...`) and records which gates it satisfies
  (`owner_retirement_approval`, `per_path_replacement_mapping`) and
  which remain pending (required profile, drift-gate removal,
  release/license/fresh-machine).
- `tools/verify_p7_08_retirement_approval_record.py` — verifier for
  schema `sipi.p7-08.retirement-approval-record.v1`. It fails closed if
  the record stops being a template (approval prefilled), or if either
  evidence binding drifts from the on-disk SHA-256.
- `tools/test_verify_p7_08_retirement_approval_record.py` — 5 tests.

## Verification

`python -B tools/verify_p7_08_retirement_approval_record.py` returned
`{"template": true, "schema": "sipi.p7-08.retirement-approval-record.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p7_08_retirement_approval_record` passed 5/5.

## Artifact Hashes (SHA-256)

- record: `B2DE01A175FB7D2AC20949E3BCFF4302838ACBA65E357F30F1C89AC08B0C797D`
- verifier: `5EE9A28399D79DEE2B02C86CFC369194C100D274A8B9AE4781569B1473DC405A`
- tests: `86978888C051BCE1435C4BBFAA92F75421A7145FC1D80ABEC57F3F0044FB41D1`

## Scope and Non-Claims

- This record is a TEMPLATE; it grants no approval until the owner fills
  it and the verifier confirms the bindings. Even then it satisfies only
  `owner_retirement_approval`; required profile acceptance, same-batch
  drift-gate removal, and release/license/fresh-machine gates remain
  pending (record `effective_gates`). P7-08 stays blocked.
- The record is not a release approval, license clearance, fresh-machine
  certification, or profile acceptance (non_claims).
