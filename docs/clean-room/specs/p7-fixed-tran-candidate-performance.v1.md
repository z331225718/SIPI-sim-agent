# P7 Fixed TRAN Candidate Performance Evaluation v1

P7-06b evaluates one provisional P7 archive candidate without changing the
P2 measurement schema. The raw `sipi.tran.performance-observation.v1` remains
an external, hash-addressed 3-warmup/10-measured-run fact. This wrapper adds
only the release-candidate lineage needed for admission.

The evaluator first verifies the P7-06a delegated policy with its separate
external P1 locked-build and P2 baseline reports. It then requires the current
Git HEAD/tree to match an identical P7-01 twin-build report; the P7-02
composition report must name that report and its binary; the P7-03 archive
report must name that composition and contain the same executable; and the
P7-04 same-host install report must name that archive and installed executable.
The candidate observation must match the chain commit, Cargo lock, and
executable digest exactly.

The versioned evaluation report contains hashes and bounded identities only.
It never contains paths, executable bytes, measurement samples, artifact
payloads, external assets, or environment text. The status is `within_policy`
or `over_limit`; the latter still creates the external report but exits
nonzero. Every report has `promotion_status=blocked`: satisfying this one
fixed performance policy cannot clear license, NOTICE, fresh-machine, asset,
profile, or any final release gate.
