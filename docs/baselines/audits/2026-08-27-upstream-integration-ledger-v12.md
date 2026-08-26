# Upstream Integration Ledger v12 Audit

Date: 2026-08-27

## Scope and predecessor

This is an additive currentness record for
`docs/baselines/upstream-integration-ledger.v12.yaml`. It does not rewrite or
close any row in the immutable v11 ledger. The predecessor is
`docs/baselines/upstream-integration-ledger.v11.yaml`, whose SHA-256 is
`2a8fc445a0627f0bec1218a8fdabfdf2fac7a6f92b895f53cd863736c334cb4d`.

The candidate is the clean immutable commit
`a6db3dafb1c52309bdc701db31bae47e4d340cbb`, tree
`2bfb65fdd44d350786180835c6eb5f9fc4fb757d`. A
`git -c core.autocrlf=true archive --format=tar` of that commit is exactly
`52992000` bytes with SHA-256
`3f385f2f323b3b78095b1ec884697eb1dc086b4df3b5bba9b390026acbfc8890`.
The archive is the candidate boundary; the current worktree overlay is not
part of the candidate.

## Policy

The ledger retains 15 rows and `release-ready=0`. New domain features remain
forbidden. Direct Rust ports still require named upstream behavior, and an
external runtime is not parity. S-parameter fitting is forbidden. Channel
simulation uses one final frequency-domain-to-time-domain impulse; no
multi-pass S-parameter fit is inferred from any row.

## AS-05 decision

The existing `run-hspice` staging record and current Rust control
implementation are retained without rollback. The owner explicitly excluded
the Xyce/XDM extension as not required. This row therefore records
`owner_excluded_not_required` and `no_xyce_xdm_extension`. It does not claim
an Xyce or XDM implementation, solver result, numeric parity, migration row
close, or release readiness.

## Current PyBERT scoped evidence

PB-01, PB-02, and PB-03 bind the physical manifest
`docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml` and its audit
`docs/baselines/audits/2026-08-26-pb-01-03-current-scoped-replay-bc882d2e.md`.
PB-01 records 12 selected arrays and the 23-key `sipi.pybert_data.v1`
default dictionary. PB-02 records 11 logical NPZ members. PB-03 records a
44-member stable subset, 113 candidate members versus 150 upstream members,
and `whole_payload_parity=false`. These are scoped observations only; they
are not branch completion, global parity, product admission, or release
evidence.

## Current COM formal evidence

COM-02 and COM-04 bind the v5 formal manifest
`docs/baselines/com-workbook-accm-replay-v5.manifest.yaml`, its audit
`docs/baselines/audits/2026-08-27-com-workbook-accm-replay-v5.md`, both fresh
reports, and the aggregate. The formal gate status is
`scoped_mismatch_observed`; the sole blocker is
`candidate_dfe_taps_not_published`. Port order is `not_observed`, DFE
publication is `candidate_not_published`, and the gate is not numeric,
global, product, or release parity. The two replays remain observations even
where the COM/FOM residuals are small, because candidate DFE taps are not
published and artifact receipts differ. The channel policy is one final
FD-to-TD impulse and S-parameter fitting is not used.

COM-01 and COM-03, plus all other rows not changed by this successor, retain
their v11 historical or scoped semantics. No row is closed by this audit.

## Verification boundary

The v12 verifier binds the v11 predecessor hash, candidate commit/tree and
archive bytes/SHA, the PLAN marker, all row evidence and nested evidence
paths, the PB and COM manifest/audit/report/aggregate SHA-256 values, and the
v12 audit and mutation harness. The mutation suite covers AS-05 exclusion,
PB scoped counts, COM blocker/status/no-fit/impulse/nonclaims,
`release_ready=0`, predecessor drift, and physical/hash drift. The harness is
mechanical custody evidence, not a promotion mechanism.

# PLAN_MARKER: 2026-08-27 v12 upstream-first successor
# LEDGER_SCHEMA: sipi.upstream-integration-ledger.v12
# CANDIDATE_ANCHOR: a6db3dafb1c52309bdc701db31bae47e4d340cbb|2bfb65fdd44d350786180835c6eb5f9fc4fb757d|52992000|3f385f2f323b3b78095b1ec884697eb1dc086b4df3b5bba9b390026acbfc8890
# PREDECESSOR_ANCHOR: docs/baselines/upstream-integration-ledger.v11.yaml|2a8fc445a0627f0bec1218a8fdabfdf2fac7a6f92b895f53cd863736c334cb4d
# PB_ANCHOR: manifest|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e.v1.yaml|32763b2bc0f4f14dc3c291ca91fa9cb0b260ad9606cc48d556e69f3811b7966e|12|23|11|44|113|150|whole_payload_parity=false
# COM_ANCHOR: manifest|docs/baselines/com-workbook-accm-replay-v5.manifest.yaml|6ac1bd5cec34e960c992876fe35471b7019178b1af9db88cdaffe8f612cc7bd9|status=scoped_mismatch_observed|blocker=candidate_dfe_taps_not_published|port_order=not_observed|dfe=candidate_not_published|fresh=2|no_fit=true|impulse=one_final_fd_to_td_impulse
# HARNESS_ANCHOR: verifier|tools/verify_upstream_integration_ledger_v12.py|manifest_bound
# HARNESS_ANCHOR: mutation_tests|tools/test_verify_upstream_integration_ledger_v12.py|manifest_bound
