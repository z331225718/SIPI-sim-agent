# P7 Fixed TRAN Performance Policy v1

This policy is a delegated numerical decision for one Windows x86_64 fixed
RC/PULSE workload. It consumes an external, hash-addressed P2 observation as
its baseline but does not alter that observation's pending-owner-budget state.

The policy admits exactly three warmups and ten measured direct invocations of
the typed `tran-rc-pulse-v1` request. The verifier consumes both the external
P2 observation and its external P1 locked-build report, requiring their commit,
lock, and executable hashes to agree with the policy binding. It evaluates only
the median wall time and the child process `PeakWorkingSetSize`; the latter is
not RSS or resource enforcement. The fixed v1 thresholds are 30,000,000 ns and
5,000,000 bytes.

The approval records a project-owner delegation to choose numeric values. A
future policy version needs a new delegation reference. Exceeding either
threshold blocks the candidate, preserves a scrubbed observation, and never
automatically retries, relaxes a threshold, or replaces the baseline.

P7-06a verifies policy/baseline binding only. P7-06b must separately bind a
fresh candidate observation to the P7 twin-build, composition, archive, and
direct installed executable identity. Neither step makes the overall release
ready.
