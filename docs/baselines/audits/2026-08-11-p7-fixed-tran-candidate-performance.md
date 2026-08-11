# P7-06b Fixed TRAN Candidate Performance Evaluation

The candidate wrapper was evaluated for commit
`5edced573a8df3889965a768b860a03c33790444`.  It bound one direct-installed
Windows x86_64 executable to the following external evidence chain:

- twin-build report: `77812781d38833d563addb6fa8729763524de66e3ca77521419a77f7521b7164`
- composition report: `3e4f9a2e0457e3856cc10bd80221c7e3cc3e9e2dfeb9da06b21a6fdd5db184b3`
- archive report: `32c2e2bf127948a47686151e870a25ceb83a4d51702e9043c0d8cf49c86d38cf`
- isolated-install report: `251cb2b3fc2a22e0daaf97c85464981a324e90ca640f5cac14f5f4eb6aba6df7`
- new 3+10 candidate observation: `5f1a2ce267caa00b28bfa7e921f9114bbb310e2d5b260b4cc98669e46e5bd3eb`
- wrapper evaluation: `sipi.p7-fixed-tran-candidate-performance-evaluation.v1`

The executable SHA-256 was
`cf36303e8997124c8bc1f9d53ea410eb09a6b17431453ef1dd2fb0cca73adfd8`.
The fixed `tran-rc-pulse-v1` workload produced a 10-sample median wall time
of `18,040,400 ns` and a median child `PeakWorkingSetSize` of `4,259,840`
bytes.  Both satisfy the delegated policy limits of `30,000,000 ns` and
`5,000,000 bytes`.

The evaluation status is `within_policy`; its `promotion_status` remains
`blocked`.  This is one same-host observation for the fixed workload, not a
hard CPU, RSS, OOM, cross-machine, service, GUI, legal, fresh-machine, or
release-approval result.  Pending license/NOTICE, asset, profile, and
fresh-machine gates remain independent blockers.

An independent Orca audit of the wrapper implementation reported 0 P1 and
0 P2 findings before this candidate evidence was generated.
