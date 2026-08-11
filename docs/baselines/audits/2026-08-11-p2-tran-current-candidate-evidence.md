# P2 Current-Candidate TRAN Evidence

The historical TRAN evidence remains unchanged. A current clean archive of
SIPI commit `25a11236984d4a7d01f7465797392d6fd5518aae` built only the
feature-gated RC/PULSE harness in external custody. A separate clean archive
of `agent-spice@2cc92316` built the pinned oracle with its revision and clean
build-info explicitly injected.

Two fresh oracle materializations produced identical array hashes. The current
product harness passed the fixed time, `v(in)`, and `v(out)` policy without
recording a fixture or waveform array in the worktree. The current-candidate
evidence record binds the product source trees, lock object, executable hashes,
report hash, and comparison metrics.

This restores only profile-scoped Windows acceptance for the fixed four-sample
RC/PULSE wrapper. It does not accept the parameterized one-node API, general
TRAN or netlist behavior, CLI end-to-end behavior, or release readiness.
