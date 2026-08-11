# P2/P7 Fixed TRAN Evidence Reconciliation

The prior capability ledger described `tran-rc-pulse-v1` as specified but not
externally compared. That state conflicted with historical PLAN prose and was
not promoted from prose alone.

For product source commit `da1a9b9f0d1c8df47c2f8a4fce4f0d0c3e5160b8`,
the observer gate rebuilt the pinned Agent-Spice source in an external clean
worktree, verified its release build identity, materialized the required Git
blob twice, and compared both deterministic oracle runs with the independently
built product harness. The hash-only external report is retained outside the
worktree; its identity and aggregate metrics are captured by
`tran-rc-pulse-external-compare-evidence.v1.yaml`.

The report passed all three scoped comparisons. The largest result difference
was `9.963737488231927e-7 V` at index 3 for `v(out)`, within the frozen
`2e-6 V + 5e-4 relative` threshold. The report and evidence contain no deck,
waveform, executable, or absolute path.

This reconciliation accepts only the fixed four-point `time`, `v(in)`, and
`v(out)` profile on Windows x86_64. It does not establish general TRAN,
netlist parsing, OP, AC, cross-platform support, legal clearance, or release
readiness.

One Orca read-only review reported zero P1 findings and four P2 findings. The
relevant verifier gaps were closed: recorded tolerances now must match the
acceptance contract, each maximum absolute error must fit the saved
worst-sample bound, and report-binding tests cover oracle identity and metric
tampering. The verifier explicitly documents that evidence-only mode validates
attestation structure and current product inputs, while external report custody
is checked only when the report is supplied.
