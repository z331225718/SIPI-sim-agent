# Upstream Integration Ledger v8 Audit

Schema: `sipi.upstream-integration-ledger.v8`; status:
`current_clean_candidate_open_no_release`.

This additive successor preserves immutable v1-v7 ledgers. It binds clean
candidate `b2de8ed6ecbff44ac85d5371a1dcf8499a4f584e`, tree
`b7903ef234b3c03915d9b2c03c1c244370de9c64`, and the explicit
`git -c core.autocrlf=true archive --format=tar` clean archive SHA
`3b59eb25ce7b8bd942d3d6e82d666da369136fb48d56154cd390228474a78b88`
(`44963840` bytes), with no worktree overlay. The v7 ledger remains immutable
at physical SHA `32ebc1761340d9dd6344376d634d0619e777939518aa568e206b9ea02c09b3c6`;
v8 takes over current validation without rewriting v7. The historical v6 live-path verifier is not a current acceptance gate.
The v7 live-path verifier is a historical predecessor gate; v8 is the current
successor and does not promote its expected live-path drift to closure.

AS-03 is bound to its source-map and NOTICE only. The v2 global mismatch and
v3 fixed-fixture scope remain open; no SI S-parameter fit, numeric parity, or
release is claimed. AS-04 remains a relative source-map/NOTICE binding with
HSPICE external. AS-06 remains source-asset-missing, docker-info-failed,
build-not-attempted, workflow-not-run, parity-false, and release-false.

PB-01 remains a single environment-local inventory observation. PB-02 binds
the 43c formal v2 manifest, two run reports, and aggregate as one fixed-fixture
environment-local numeric observation. It does not claim branch completion,
global parity, bit-reproducible build, pure-Python legacy, promotion, or
release. PB-03 retains its conservative inventory-only claims; PB's AMI
`no_current_numeric_replay` remains explicit for PB-03.
materializer remains bounded example_rx/control semantics with vendor DLL and
numeric parity open.

COM is unchanged from v7: `SOURCE-MAP-COM-02` records an internal staged
DC/ACCM leaf, while complete public S4P plus legal-search ACCM E2E remains
blocked at `Chain(Equalizer)`. Pinned numeric/canonical outputs, upstream
DC/ACCM parity, full-row parity, and release remain open. COM-01/03 retain
historical evidence and do not inherit this observation; no fit is claimed and
channels remain impulse-only. The explicit non-claim is `no_public_accm_e2e`.

All fifteen rows (15 rows) remain open and `release-ready=0`. No source map, external
asset, build observation, synthetic artifact, or historical evidence promotes
global parity, row closure, or release. The v8 verifier and mutation suite
reject fake closure/release, AS/PB/COM overclaims, predecessor/archive/plan
drift, hash/path drift, malformed types, and coordinated self-declarations.
No promotion.
