# P7 Candidate Build License-Material Observation v2

## Scope

This external-only observation identifies the package closure actually compiled
by the fixed Windows `sipi-cli` release build for one immutable candidate. It
is an input to later legal, NOTICE, and SBOM work; it is not any of those
outputs.

The observer materializes the named candidate from its Git object twice and
runs the exact locked/offline Windows build in independent target directories.
It collects only the resulting Cargo `compiler-artifact` identities and their
required `manifest_path` fields; it must not first run `cargo metadata`.
`manifest_path` is a locator only and is never retained. Paths inside the
candidate archive identify workspace packages; every other path must be a
regular, non-link path strictly below the explicit Cargo registry source root.
The manifest supplies only a name/version locator, which must select exactly
one registry entry in the candidate lock before any checksum-matched `.crate`
is read. The two canonical package inventories must match exactly.

For each compiled registry package, the observer reads only a locally cached
`.crate` archive whose SHA-256 equals the candidate `Cargo.lock` checksum. It
records literal Cargo manifest `license` and `license-file` metadata plus the
path, SHA-256, and length of packaged `LICENSE*`, `COPYING*`, `NOTICE*`, and
`COPYRIGHT*` candidates. Workspace packages are bound to their candidate
archive manifest bytes and the candidate product-boundary classification.

A Cargo workspace-inherited declaration such as `license.workspace = true` or
`license-file.workspace = true` is retained only as an inherited declaration:
it supplies no literal SPDX expression or file path to this observer. The
observer records neither a substituted workspace value nor a legal conclusion
from that declaration.

For package identity only, a workspace package with `version.workspace = true`
uses the literal `workspace.package.version` in the same candidate root. The
report identifies that source separately; this mechanical version resolution
does not resolve inherited license metadata.

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
locked/offline build, unequal fresh package sets, a missing or ambiguous
`manifest_path`, registry-source escape, malformed Cargo JSON, unmatched lock
package, archive checksum mismatch, missing compiled archive, archive path
traversal/symlink, duplicate archive manifest, or material budget violation is
fail-closed. A partial/missing archive result is recorded as a rejected
observation and cannot be silently completed from the network.
