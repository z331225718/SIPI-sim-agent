# P7 Current Canonical Build License-Material Observation

## Result

This is a current, hash-only build-closure observation for the repository
`HEAD` on 2026-08-21. It is not a license conclusion, NOTICE decision,
dependency approval, SBOM, or release decision. The external JSON report is
retained outside the repository and is bound by
`docs/baselines/p7-current-candidate-build-license-material-observation-evidence.v1.yaml`.

The current evidence uses its own v1 schema. The historical v2 verifier and
evidence remain unchanged and continue to reject same-commit candidate and
observer shortcuts.

## Exact source and archive identities

- Candidate Git commit: `97b0f271abcb7df02a3a9b259c4dafee86f3a783`
- Candidate tree: `7ae439ec366e30e050931ecb1f18f360e66540c1`
- Archived `Cargo.lock` SHA-256: `43c931a505347f95bb632a76f142c31756c72fbd0558ff15cbff32864e0d4b9d`
- Archived `rust-toolchain.toml` SHA-256: `3cc13c37191008eaab5490eea2136223fa1bc5b5d2aa9c74a199a0c0c854aa90`
- Observer source commit: `97b0f271abcb7df02a3a9b259c4dafee86f3a783` (same
  candidate archive; permitted only by the dedicated current v1 verifier)
- Observer source tree: `7ae439ec366e30e050931ecb1f18f360e66540c1`
- Observer archived bytes SHA-256: `2c95a14c88b5bc7bb18f84fad5f66e614b7c7931e22aa2965e3470348334478d`
- External report SHA-256 / bytes: `39b8dd0a88c2357c05bee566e2c42aec2ebdeaecbbf4f4644efa07b0410a3085` / `57976`

The observer ran twice from clean Git archive materialization with
`core.autocrlf=false`, using Cargo offline custody. The candidate and observer
source are the same pinned commit only because this dedicated current schema
explicitly records a clean archive observation of that commit; the verifier
re-hashes the archived inputs and does not change the historical v2 rule.

## Closure observation

The fixed Windows target was `x86_64-pc-windows-msvc`, with `--release
--locked --offline`. Both builds emitted the same package closure:

- 86 compiled packages: 73 registry packages and 13 workspace packages;
- package-set SHA-256:
  `ceed1c50195318fdbde69e313c7d7c44394cd4b5b319614680572d3208d7170d`;
- every observed registry crate archive matched its immutable Cargo.lock
  checksum;
- the report records each compiled package's manifest identity and the
  SHA-256/length of archive members whose names begin with `LICENSE`,
  `COPYING`, `NOTICE`, or `COPYRIGHT`.

Workspace package declarations remain boundary observations rather than
license approvals. Registry `license` fields and archive material are kept as
literal identities; they are not converted to SPDX conclusions or NOTICE
obligations. All package records retain `license_concluded=NOASSERTION` and
`notice_requirement=not_evaluated`.

## Gate state and next input

The selected build package set and declared metadata are observed. Dependency
snapshot readiness, dependency approval, NOTICE approval, first-party scope
approval, SBOM generation, release readiness, and promotion remain false or
blocked. The report does not rebind the other P7 chain stages or certify a
fresh machine, loader/runtime closure, or any required external profile.

The next non-mechanical inputs are first-party product-path scope, dependency
distribution-rights review, NOTICE/distribution review, and (for release)
fresh-machine/profile certification. No legal conclusion is inferred from a
Cargo metadata string.
