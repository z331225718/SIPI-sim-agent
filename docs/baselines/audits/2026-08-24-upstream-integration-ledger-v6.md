# Upstream Integration Ledger v6 Audit

Schema: `sipi.upstream-integration-ledger.v6`; status:
`current_clean_candidate_open_no_release`.

This additive successor preserves the immutable v1-v5 ledgers. It binds clean
candidate `a2b1f9bdee65d34e586bfb36ba440eb41c4815fa`, tree
`8138a7d7ab51099cc44cb92fda743277e7072d07`, and the explicit
`git -c core.autocrlf=true archive --format=tar` clean archive SHA
`ad24059cf87ae817ebeb3a6a7c2a3c989f30d39542b1fdc6e99420545dcc9462`
(`44564480` bytes), with no worktree overlay. The v5 ledger remains a
historical immutable predecessor at its recorded physical SHA; a v5 live-path
hash drift caused by the COM source-map evolution is historical drift, not a
reason to rewrite v5. The v6 verifier takes over current validation.

AS-06 is currently bound to the v2 build-preflight manifest: the source asset
is missing, `docker info` failed, build was not attempted, workflow was not
run, parity is false, and release is false. PB records the additive AMI
materializer source map, PyAMI license boundary, and pinned source-oracle
anchors; it remains bounded `example_rx`/control semantics only, with vendor
DLL and numeric parity open. No generic or vendor capability is promoted.

COM binds the current `SOURCE-MAP-COM-02`: the internal DD package FD cascade
and public 64-point synthetic artifact E2E include FEXT/NEXT metric integration
and one final FD-to-TD impulse conversion, with S-parameter fitting forbidden.
COM-02/04 current observation is scoped synthetic package E2E only; there is
no clean upstream package numeric replay. DC/ACCM, full-row parity, and
release remain open. COM-01/03 retain historical evidence and do not inherit
this current observation. The synthetic E2E is scoped evidence only.

All fifteen rows remain open (15 rows) and `release-ready=0`. No promotion is
made from source maps, external assets, build observations, synthetic artifacts,
or historical evidence to global parity, row closure, or release. The v6
verifier and mutation suite reject fake closure/release, AS build claims, PB
vendor/generic claims, COM fit/DC/ACCM/upstream-parity claims, predecessor
drift, hash/path drift, malformed types, and coordinated self-declarations.
No promotion.
