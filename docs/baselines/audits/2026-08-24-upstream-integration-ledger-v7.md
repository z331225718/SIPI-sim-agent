# Upstream Integration Ledger v7 Audit

Schema: `sipi.upstream-integration-ledger.v7`; status:
`current_clean_candidate_open_no_release`.

This additive successor preserves the immutable v1-v6 ledgers. It binds clean
candidate `246a285fb4c12af50c272fe17427418723445c2a`, tree
`86248d9296b3d5c8fc2f7379067c6d4b52d28c01`, and the explicit
`git -c core.autocrlf=true archive --format=tar` clean archive SHA
`bfc50b05f8fdc7338017052ebff2e21f75ef8e7e9465bbcb13012e80fb3f900b`
(`44738560` bytes), with no worktree overlay. The v6 ledger remains a
historical immutable predecessor at its recorded physical SHA; a v6 live-path
hash drift caused by the COM source-map evolution is historical drift, not a
reason to rewrite v6. The v6 live-path verifier is expected to fail its stale
COM source-map hash gate on the current tree; v7 explicitly takes over current
validation and does not claim that the v6 live verifier passes.

AS-04 is bound only to its relative source-map and NOTICE path; HSPICE remains
an external runtime blocker, with no numeric parity and no verified external
solver result claimed. AS-06 is currently bound to the v2 build-preflight manifest: the source asset
is missing, `docker info` failed, build was not attempted, workflow was not
run, parity is false, and release is false. PB-01 binds the
`pb-01-03-branch-inventory-ab1fc` inventory as a single environment-local
observation. PB-02 and PB-03 bind the same inventory but retain
`no_current_numeric_replay` and `rust_reachability_only`; PB-03 also retains
`no_candidate_parity`. All remain without branch-completion claims. PB records the additive AMI
materializer source map, PyAMI license boundary, and pinned source-oracle
anchors; it remains bounded `example_rx`/control semantics only, with vendor
DLL and numeric parity open. No generic or vendor capability is promoted.

COM binds the current `SOURCE-MAP-COM-02` only as an internal staged DC/ACCM
leaf. A complete public S4P plus legal-search E2E remains open at
`Chain(Equalizer)`; pinned numeric outputs, canonical ACCM fields, upstream
DC/ACCM numeric parity, full-row parity, and release remain open. COM-01/03
retain historical evidence and do not inherit this observation.
The corresponding non-claim is `no_public_accm_e2e`; this is not a public
ACCM parity or canonical-field claim.

All fifteen rows remain open (15 rows) and `release-ready=0`. No promotion is
made from source maps, external assets, build observations, synthetic artifacts,
or historical evidence to global parity, row closure, or release. The v7
verifier and mutation suite reject fake closure/release, AS build claims, PB
vendor/generic claims, COM fit/DC/ACCM/upstream-parity claims, predecessor
drift, hash/path drift, malformed types, and coordinated self-declarations.
No promotion.
