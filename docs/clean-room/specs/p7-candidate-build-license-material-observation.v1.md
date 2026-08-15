# P7 Candidate Build License-Material Observation v1

## Scope

This external-only observation identifies the package closure actually compiled
by the fixed Windows `sipi-cli` release build for one immutable candidate. It
is an input to later legal, NOTICE, and SBOM work; it is not any of those
outputs.

The observer materializes the named candidate from its Git object twice, runs
the exact locked/offline Windows build in independent target directories, and
collects structured Cargo `compiler-artifact` package identities. The two
canonical package inventories must match exactly.

For each compiled registry package, the observer reads only a locally cached
`.crate` archive whose SHA-256 equals the candidate `Cargo.lock` checksum. It
records literal Cargo manifest `license` and `license-file` metadata plus the
path, SHA-256, and length of packaged `LICENSE*`, `COPYING*`, `NOTICE*`, and
`COPYRIGHT*` candidates. Workspace packages are bound to their candidate
archive manifest bytes and the candidate product-boundary classification.

## Exclusions

The observation must not read the network, fetch missing archives, retain
license text, emit cache/source/target absolute paths, classify license
compatibility, decide NOTICE obligations, produce SPDX/CycloneDX, approve a
dependency or first-party path, or change the release-license manifest.

`license_concluded=NOASSERTION`, `notice_requirement=not_evaluated`, and all
release, SBOM, NOTICE, first-party, dependency, fresh-machine, and promotion
gates remain blocked regardless of the package inventory result.

## Failure Rules

Candidate/tree/lock/toolchain drift, a non-clean materialization, a failed
locked/offline build, unequal fresh package sets, malformed Cargo JSON,
unmatched lock package, archive checksum mismatch, missing compiled archive,
archive path traversal/symlink, duplicate archive manifest, or material budget
violation is fail-closed. A partial/missing archive result is recorded as a
rejected observation and cannot be silently completed from the network.
