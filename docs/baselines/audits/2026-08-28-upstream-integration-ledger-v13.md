# Upstream Integration Ledger v13 Audit

Date: 2026-08-28

Governance marker: 2026-08-28 v13 upstream-first successor
Schema: sipi.upstream-integration-ledger.v13
Recorded statuses: `blocked_numeric_semantics`, `scoped_matrix_blocked`,
`scoped_exact_materialized_fingerprint_stage2_formal_record`,
`scoped_current_candidate_observed`.

This audit records the v13 additive governance snapshot for the three upstream
projects. It is an index and custody check, not a new implementation or a
parity decision. The candidate is the clean Git commit
`189ffaa85f8f21ae7cdc7b2ca8f126122d9b335f`, tree
`f4a76932fef0a8f1f790ce682477d7639c7822de`. With
`core.autocrlf=true`, its Git archive is 55,480,320 bytes and has SHA-256
`3e96cf027f2aa9daa313474061cf783a0bff07fb8f896ae86c4380f9ea08ecbf`.

The v12 ledger remains immutable. This v13 successor binds the current formal
evidence without changing the product boundary:

- AS-03 binds `docs/baselines/as-03-power-wave-solve-replay.v1.yaml`. Its
  status is `blocked_numeric_semantics`: four real bits were compared, three
  differ, and the maximum observed difference is one ULP. This is not numeric
  parity, global parity, acceptance, or release evidence.
- PB-01 and PB-02 bind
  `docs/baselines/pb-01-02-portable-matrix.v1.yaml`. Two fresh replays are
  consistent. PB-01 has five passed cases and a blocked Duo case; PB-02 has
  six blocked cases. The matrix status remains `scoped_matrix_blocked`.
- COM-01 binds the root manifest
  `com-01-fingerprint-current-replay-stage2.manifest.json`. Its scope is only
  `scoped_exact_materialized_fingerprint_stage2_formal_record`, with raw
  SHA-256 recorded per replay and no configuration payload claim.
- COM-03 binds
  `docs/baselines/com-03-current-candidate-replay.v1.yaml`. Its two-replay,
  23-scenario result is a scoped current-candidate observation, not complete
  COM parity or a release artifact.

All 15 migration rows remain open and `release-ready=0`. No row is closed and
no row is promoted by this ledger. AS-05 remains
`owner_excluded_not_required`; Xyce/XDM work is explicitly out of scope and
the existing external solver boundary is retained. SI S-parameter fitting is
forbidden. Channel simulation remains one-final FD-to-TD impulse only.

The ledger preserves the existing MIT/BSD source-authority records and binds
the formal evidence files, their audit files, and the current source receipts
by relative path and SHA-256. Absolute paths, temporary outputs, raw result
payload promotion, global parity, product capability promotion, and release
readiness are not claimed. Any future row close requires a separate
branch-complete evidence decision; it cannot be inferred from this successor.
