# PB-03 Current Immutable Evidence Audit

Status: **passed replay / open branch scope**

Both fresh `sim-rust` replays (`pb-03-current-bound-archive-01` and `pb-03-current-bound-archive-02`) ran from candidate archive commit `64b783f66d7e986d0975be5ac3946b453b15c4ed` (tree `0e11721f2bb5b564002820cc7a5aaab45e30ba3b`, archive `c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9`) against the pinned oracle archive (`e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25`). Run IDs and report digests are distinct; toolchain identity is exact.

The fixed legacy projection payload passed both replays. Each candidate was built and executed directly from a fresh Git archive materialization; the working tree was not consulted. This does not close external AMI/IBIS or full branch parity.
