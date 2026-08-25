# Upstream integration ledger v11 audit

Schema: `sipi.upstream-integration-ledger.v11`; additive successor to the
immutable v10 ledger. Candidate `e7e9882e5a7c3b058ee3e1cc7830da5ac60dd82d`,
tree `6bf982dfecb226f656feaad5a31dc93820cd7893`, and the exact
`git -c core.autocrlf=true archive --format=tar` are bound by the v11
verifier: archive SHA256 `4dce7e63ae169f5d1659549ac10433c3befa1f36641ce124719b1abb2de31336`
and `52152320` bytes. The immutable v10 predecessor is physically bound by
`docs/baselines/upstream-integration-ledger.v10.yaml`.

This is an additive governance snapshot, not a feature or release promotion.
All 15 rows remain open or scoped and `release-ready=0`. The standing policy
remains no SI S-parameter fitting, impulse-only channel handling, no global
parity, and no release claim.

AS-04 now binds its v2 source map and NOTICE, including frozen best-trial
artifact custody, but HSPICE remains an external solver and no E2E or numeric
parity is claimed. AS-06 now binds its v3 source map and NOTICE, including
native caller custody and the real CLI/output protocol; the solver remains an
external boundary with no E2E or parity claim.

PB-01 now records bounded class-pickle compatibility: the pinned Python load
observation is source-bound and the default dictionary path is unchanged. It
does not close the branch, establish global parity, or make a release claim.

COM-01/COM-02 may retain the source-exact `Do_White_Noise` diagnostic from the
trusted workbook consumption registry. That option remains
source-unimplemented and Wiener-Hopf-only; the branch is fail-closed and no
generic DTO, numerical white-noise gate, or public JSON alias is admitted.
COM remains no-fit and impulse-only, with no global parity or release claim.

The v10 predecessor, current candidate archive, PLAN, audit, verifier,
mutation suite, and all changed source maps/notices are physically hash-bound
by the v11 verifier. No historical ledger is rewritten and no external
runtime observation is promoted.

Audit markers: AS-01 AS-04 AS-05 AS-06 PB-01 class-pickle PB-02 flat Temp
COM-01 COM-02 Do_White_Noise source-unimplemented Wiener-Hopf-only not formal evidence
impulse-only No v10 file.
