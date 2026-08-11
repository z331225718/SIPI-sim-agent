# P2 One-Node RC/PULSE Audit

Scope: P2-02d/P2-03b. The change introduces the product-owned,
topology-fixed one-node RC/PULSE library core and reuses it for the existing
`tran-rc-pulse-v1` wrapper.

One Orca OMP reviewer performed a read-only audit. Its first pass found a
breakpoint-limit admission gap, missing cooperative checkpoints while
expanding many PULSE periods, and missing read-only request accessors. The
implementation added an initial breakpoint-limit check, a per-period
checkpoint, explicit getters, and regression coverage. The same reviewer then
rechecked the current worktree and reported 0 P1 / 0 P2 findings.

The fixed harness still emits the four original result values bit-for-bit. The
new API remains library-only: it does not add a wire request, CLI route,
netlist parser, MNA, OP/AC, non-linear device, artifact, or external-fixture
surface.
