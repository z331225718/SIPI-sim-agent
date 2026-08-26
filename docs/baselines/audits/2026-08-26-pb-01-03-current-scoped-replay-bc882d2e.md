# PB-01/02/03 Current Scoped Replay Audit

Date: 2026-08-26

## Scope

This audit binds the six existing replay reports whose filenames contain
`pb-01-03-current-scoped-replay-bc882d2e`. The reports are additive evidence
only. No production crate, prior evidence manifest, PLAN, ledger, or license
record is changed by this bundle.

## Source custody

Every report declares `git_archive_at_immutable_commit`. The candidate identity
is commit `bc882d2e5a19c2a844bacc485ede5b874e8f9c37`, tree
`d87cfecea77ccd670073a6c069658e6b4e8c3137`, and archive SHA-256
`1f44f6dccba7a00684a82c4c7ce6248eb5ea7f353875af5d9589d17ece6883d0`.
The pinned PyBERT identity is commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`, and archive SHA-256
`e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25`.
The candidate archive SHA was independently checked with `git archive` using
the repository's `core.autocrlf=false` setting. The same check was performed
against the pinned upstream repository. Both fixture records are archive
present and their byte count and SHA-256 are bound in the manifest.

## Report and runtime identity

Each report has a repository-relative report path, a manifest-bound full-file
SHA-256, a distinct run ID, and a distinct fresh nonce. PB-01 and PB-02 use
the 64-hex nonce emitted by their runner. PB-03 uses the established
32-hex UUID nonce emitted by `pb_03_replay_common`; the verifier deliberately
requires at least 32 lowercase hexadecimal characters and does not pretend
that the two runner nonce encodings are the same format.

Toolchain records contain only executable basenames, role labels, path-redacted
flags, executable-file SHA-256 values, version-output SHA-256 values, and a
successful version exit code. No report contains an absolute host path. The
toolchain identity is required to be exact between the two runs of each row.
Required roles are row-scoped: PB-01 and PB-02 require cargo, rustc, and uv;
PB-03 additionally requires the Python oracle identity.

## Scoped results

* PB-01: both runs report the default `sipi.pybert_data.v1` Python pickle
  dictionary with exactly 23 item names. Twelve selected arrays are compared
  numerically and pass the recorded tolerance. This is not a claim for the
  class-compatible `PyBertData` pickle or for uncovered branches.
* PB-02: both runs report exactly eleven logical NPZ members. Candidate and
  oracle logical member facts and the bound logical digest are identical. ZIP
  bytes and wrapper metadata are intentionally outside this native-core scope.
* PB-03: both runs report 113 candidate members and 150 oracle members. Only
  the 44-member stable subset listed in the manifest is compared; its logical
  digest matches on both sides. `whole_payload_parity` remains false.

## Claim boundary

The manifest keeps nested-output parity, global closure, branch completion,
product admission, independent implementation, license decision, and release
approval false. These reports are not a release gate and do not authorize
redistribution. External AMI/IBIS/vendor-runtime and other uncovered PyBERT
branches remain open.

The companion verifier checks all source, fixture, path, toolchain, nonce,
report-digest, schema, scoped payload, and claim-boundary facts. Its mutation
tests intentionally corrupt each class of binding and require fail-closed
verification.

## Immutable anchors

The normalized anchor is computed from the exact report paths, full report
SHA-256 values, run IDs, nonces, source identities, and path-free toolchain
identities used by the verifier. It is recorded in the manifest and checked
again here so a manifest-only promotion cannot change the scope.

NORMALIZED_ANCHOR_SHA256: bfd472d138fde41cdf2c1c061a2bc02f46152451ac768a68d4d0f7c694b09d6b
HARNESS_ANCHOR_ALGORITHM: sha256-source-with-dynamic-assignment-lines-removed-v1
HARNESS_ANCHOR: verifier|tools/verify_pb_01_03_current_scoped_replay.py|69eca360a9e7a8acdd55a32b36ec4fb129a37370bc3d4092b64bb6bb22d56c79
HARNESS_ANCHOR: mutation_tests|tools/test_verify_pb_01_03_current_scoped_replay.py|7c992c9d4fe4fd5ef260e48b4cc22146d3b4d546e907b550f05ca57feecbc5e2
REPORT_ANCHOR: PB-01|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb01-run-01.v1.json|de1307394a1435af1c7162558662101791b081f741b3a4776d2e40284c6c7528|pb01-current-a-20260825180204|16a1b2e41a8f239fa63342dfb5e39d1372e55b3cce7439771de5c71daba593fa
REPORT_ANCHOR: PB-01|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb01-run-02.v1.json|1d779f9e46679fbc62a09333283b5e80691c50073693cb0fe9b078e342faa528|pb01-current-b-20260825180352|d05bae15bcaed48e034667aaeaa1dc2281057a31de7f09f3ef19c45ee537c7f7
REPORT_ANCHOR: PB-02|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb02-run-01.v1.json|38c1f00b30282911a3dea84058a242a35f604142a8c86f7c72ff7e20d6b9c8ca|pb02-current-a-20260825175748|e9d337f2e5fb9ee8fb2b157971ca70f8924473228d81babfbd609ca2550ea306
REPORT_ANCHOR: PB-02|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb02-run-02.v1.json|722b71d85c503fe1e3047dbce21767158784b6f098738330a2634ee19845bfd0|pb02-current-b-20260825180014|b67e2d490e814fd8ae512d6c0a69af48ddd9a3d040e6018c68084bc98e884da9
REPORT_ANCHOR: PB-03|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb03-run-01.v1.json|a27a26ac06d81894ec3190de212b7be963e57a876d1f900dac3e4ffd9e61d556|pb03-current-a-20260825180534|f2118d3ff6904227969ad80b6d985d23
REPORT_ANCHOR: PB-03|docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb03-run-02.v1.json|0f069b8a659255f2a30d9220dc3ae0e0a6a340cc090bc1a10ba32355b3762d3b|pb03-current-b-20260825180814|cbcee92db8984a0cb62c116f401537a4
