# P2-06c Fixed TRAN Current Evidence Rebinding

The historical v1 attestation remains immutable and intentionally drifts from
the current product candidate. This v2 record binds the fixed
`tran-rc-pulse-v1` comparison to current commit
`49979dff461682401356cfd95d43d68bcc288069`.

The observer rebuilt the pinned Agent-Spice oracle from a clean detached
worktree at its accepted commit, with clean build metadata, and rebuilt the
feature-gated SIPI harness from a clean Git archive. Two fresh oracle custody
runs produced identical time, `v(in)`, and `v(out)` hashes. The product result
passed the frozen comparison policy; the external report remains outside the
worktree and the tracked evidence retains only hashes and metrics.

This accepts only the four indexed samples of the fixed RC/PULSE wrapper on
Windows x86_64. It does not accept the parameterized one-node route, a netlist
parser, OP, AC, general SPICE behavior, release readiness, or legal clearance.
