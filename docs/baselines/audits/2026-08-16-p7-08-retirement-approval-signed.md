# P7-08 Retirement Approval Signed — Audit Record

- Date (UTC): 2026-08-16T07:10:49Z
- Scope: P7-08 owner retirement approval; P7-08a/08b proposal approval
- Status: recorded; P7-08 main item stays open

## Decision

The owner, via interactive session instruction ("1、approve by"), approved the
P7-08 retirement plan on 2026-08-16. The approval is recorded in
`docs/baselines/p7-08-retirement-approval-record.v1.yaml`:

- `approval_state: owner_approved`
- `approved_by: owner` (signing identity recorded as `owner`; the session
  instruction is the provenance)
- `approved_at_utc: 2026-08-16T07:10:49Z`
- evidence bindings re-bound to the post-migration hashes of the map
  (5F31233AE030E0CF87EF57EFD9E5D90C6A85E845CAF941C6786F3E30AD70523B) and the
  strategy (BFC7B3D58ED8867FD51F016BD474D457D9216BA41846462B25A9812AB5711A8A).

The replacement map and drift-gate retirement strategy migrated from
`awaiting_owner_approval` to `owner_approved` in lockstep, and all three
verifiers were upgraded from "template/proposal integrity" to
"owner-approved + cross-bound" validation:

- `tools/verify_p7_08_path_scoped_replacement_map.py` — requires
  `owner_approved`, cross-binds the signed record (schema, approval state,
  non-empty signer/time, exact current map hash).
- `tools/verify_p7_08_drift_gate_retirement_strategy.py` — same cross-bind
  for the strategy hash.
- `tools/verify_p7_08_retirement_approval_record.py` — requires signed state
  (non-empty `approved_by`, ISO-8601 UTC `approved_at_utc`), exact evidence
  hashes, unchanged `non_claims`, and every gate other than
  `owner_retirement_approval` still `still_pending`.

## Explicitly NOT granted by this approval

- No path deletion (all map dispositions must remain retain/quarantine;
  FORBIDDEN_DISPOSITIONS unchanged).
- No drift-gate removal (strategy dispositions must remain retain;
  same-batch rule and mandatory pre-removal gates unchanged).
- No profile acceptance (`required_profile_accepted: still_pending`).
- No release approval / license clearance / fresh-machine certification
  (`release_license_fresh_machine_gates: still_pending`).
- P7-08 blocker remains `blocked_no_path_scoped_replacement_and_retirement_approval`
  (renamed only when the remaining gates pass).

## Verification

`python -m unittest` on the three P7-08 suites: 39 tests, all passed
(8.731s). Negative cases re-asserted: reverted approval state, deletion /
removal dispositions after approval, gate dropping, claim tokens in free text,
tracked-count drift, coverage gaps, unsigned record, blank signer.

## Remaining gates (unchanged)

required_profile_accepted; same_batch_drift_gate_removal;
release_license_fresh_machine_gates; per-path replacement mapping is satisfied
by the bound evidence; deletion still forbidden until all gates pass.
