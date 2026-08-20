# P2-09a Performance-Protocol Consistency Gate

P2-09 requires an owner-approved workload baseline for TRAN performance and
RSS. P2-09a already fixed the observation protocol (3 warmup / 10 measured,
perf_counter wall clock, PeakWorkingSetSize) and the pending-budget
verifier; the owner approval, thresholds, statistical rule, and over-limit
disposition remain pending. This audit records the mechanical gate that
keeps the four-tool protocol consistent while that approval is pending.

## Delivered Gate

- `tools/verify_p2_09a_performance_protocol_consistency.py` — verifier for
  schema `sipi.p2-09a.performance-protocol-consistency.v1`. It fails
  closed if: any of the four tools
  (measure/verify_budget/policy/candidate) disappears; the measure module
  constants drift from warmup=3, measured=10, profile
  `tran-rc-pulse-v1`, request schema `sipi.tran.rc-pulse-request.v1`; the
  verify-budget protocol/metric/platform tokens drift (perf_counter_ns,
  PeakWorkingSetSize, median_min_max_*, windows-x86_64); the pending
  budget approval guard is lost; the policy verifier stops importing the
  same measure module; or the candidate verifier loses its (direct or
  policy-mediated) path to the measure module.
- `tools/test_verify_p2_09a_performance_protocol_consistency.py` — 7 tests:
  live validity, measure constants, verify tokens, pending-approval guard,
  policy import, candidate indirect reachability, and tool tracking.

## Verification

`python -B tools/verify_p2_09a_performance_protocol_consistency.py` returned
`{"tools": 4, "schema": "sipi.p2-09a.performance-protocol-consistency.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p2_09a_performance_protocol_consistency`
passed 7/7.

## Artifact Hashes (SHA-256)

- verifier: `278A9152413DCA830F21BBAF1865BB83981EA2FB8C269210D4255910972D9BE9`
- tests: `AAABE48603855FFD1401DD371E840EAA0CF435A4602CD8B8069C0002238419A5`

## Scope and Non-Claims

- This gate records tool-chain protocol consistency only. It does not
  approve a workload, set thresholds, define the statistical rule, or
  decide the over-limit disposition — those remain owner decisions for
  P2-09 (release stays fail-closed while the budget is pending).
- The gate does not certify TRAN performance, RSS bounds, or release
  readiness, and it does not change the delegated P7-06a policy.
