# P4B-01 AMI Candidate Quarantine Audit Complete

P4B-01 requires auditing the sipi-ami candidate material origin,
implementer exposure, dependency licensing, and standard basis. P4B-01a
delivered the quarantine provenance/license/exposure preflight (Orca
0 P1/0 P2). This audit records the mechanical gate confirming the audit
is complete and marks P4B-01 complete; resolving dependency licensing
itself remains a separate, later step (explicitly out of the audit
non-claims).

## Delivered Gate

- `tools/verify_p4b_01_ami_candidate_audit_complete.py` — verifier for
  schema `sipi.p4b-01.ami-candidate-audit-complete.v1`. It fails closed
  if the preflight verifier or its audit disappears; if the preflight
  loses its source_map/dependency/exposure/promotion_eligible coverage;
  if the audit loses its quarantine/dependency/exposure/
  promotion_eligible coverage; or if the audit stops recording
  `promotion_eligible: false`.
- `tools/test_verify_p4b_01_ami_candidate_audit_complete.py` — 5 tests.

## Verification

`python -B tools/verify_p4b_01_ami_candidate_audit_complete.py` returned
`{"elements": 4, "schema": "sipi.p4b-01.ami-candidate-audit-complete.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p4b_01_ami_candidate_audit_complete`
passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `953B45582A0730F24C8170B3CCA6A49E46E8927CDDC47A0BA87E6A7080793B32`
- tests: `FA47E7C0F8E4752DE3302DA2AAC2BFD37B44488C458B01018D6894BB43296A21`

## Scope and Non-Claims

- The audit records source identity, dependency closures, exposure labels,
  and quarantine/unknown source-map state; it does not start the AMI host,
  establish ABI/runtime behavior, certify external assets, resolve
  dependency licensing, or permit release promotion (audit non-claims).
- The gate does not certify AMI behavior or release readiness; P4B-02/03/
  04/07/08/09 implementation steps remain open.
