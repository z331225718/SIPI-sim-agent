# P2-09 Owner-Approved Performance Baseline Complete

P2-09 requires an owner-approved workload performance/RSS baseline with
thresholds, a statistical rule, and an over-limit disposition. P7-06a
recorded the delegated owner approval; this audit records the mechanical
gate confirming the baseline is complete and marks P2-09 complete.

## Baseline Facts

- `docs/baselines/fixed-tran-performance-policy.v1.yaml` is
  `delegated_approved` (`approval_ref:`
  `user-delegated-numeric-policy-2026-08-11`, owner-delegated numeric
  policy selection recorded in the P7-06a audit).
- Thresholds: `median_wall_time_ns_max: 30,000,000`,
  `median_peak_working_set_bytes_max: 5,000,000`; statistical rule:
  `median_of_exactly_ten_measured_runs_only`; over-limit disposition:
  `block_release_candidate`.
- Baseline binding: observation `f6bcef3e...` (medians 24,848,100 ns /
  4,259,840 bytes), P1 locked-build report `a17d68e5...`, workload
  `tran-rc-pulse-v1` on windows-x86_64, protocol 3 warmup / 10 measured.

## Delivered Gate

- `tools/verify_p2_09_owner_approved_baseline.py` — verifier for schema
  `sipi.p2-09.owner-approved-baseline.v1`. It fails closed if the policy
  loses `delegated_approved`, its approval_ref, observation/report hash
  bindings, thresholds, statistical rule, or disposition; or if the audit
  loses its delegation narrative.
- `tools/test_verify_p2_09_owner_approved_baseline.py` — 5 tests: live
  validity, policy status, thresholds/rule/disposition, baseline binding,
  audit delegation.

## Verification

`python -B tools/verify_p2_09_owner_approved_baseline.py` returned
`{"approved": true, "schema": "sipi.p2-09.owner-approved-baseline.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p2_09_owner_approved_baseline` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `47FF0B8E78F57C86DE57CD3F29A6B5F6FD2AEF980C6D9F8C1A63B055B4908C91`
- tests: `0528799EFBA9390702952AD9D06A3FF3B402DA9057C2C34BF466B81F5E6B8A36`

## Scope and Non-Claims

- The approved baseline applies to the one fixed Windows RC/PULSE workload
  only; optimization, cross-machine benchmarks, service/GUI throughput,
  hard CPU/RSS/OOM limits, and final release approval are explicitly out
  of scope (policy non_claims). No P7 archive candidate has yet been
  measured against it; global release remains blocked by independent
  license, fresh-machine, profile, and asset gates.
- This gate does not certify performance, RSS bounds, or release readiness.
