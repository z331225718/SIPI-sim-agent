# P7 License/NOTICE Currentness Reconciliation v1

## Scope

This record is an additive currentness and normalization reconciliation for
the exact Windows `sipi-cli` build closure observed by the P7-07c/P7-07d
evidence family. It keeps the historical package-set identity and structural
metadata counts, then compares their bound candidate and lock inputs with the
current build baseline. It is not a license conclusion, a NOTICE decision, an
SPDX/CycloneDX SBOM, a dependency approval, or a release approval.

## Currentness rule

An observation is current only when the candidate commit/tree, archived
`Cargo.lock`, toolchain, observer provenance, and external report bytes are
all bound to the same current source. A byte-identical observer does not make
a report current when its candidate or source provenance is old. A report
reference without its external bytes is historical/blocked and cannot supply
per-package metadata or material identity.

## Retained historical facts

The bound P7-07c report identifies two fresh locked/offline Windows
`x86_64-pc-windows-msvc` release builds and a package-set digest with 86 total
packages: 73 registry and 13 workspace. P7-07d records 86 structurally
normalized records, with 73 literal Cargo license strings left unparsed and
13 workspace records unresolved/conflicting. These are hash-bound historical
summaries. They do not establish that the current source has the same set.

`license-file` and NOTICE candidates are material identities, not conclusions.
When the external report bytes are unavailable, the reconciliation records
their identity as unavailable rather than inferring absence or a requirement.

## Required next input

The next current replay must provide, outside the repository, the exact
observer JSON bytes for the current candidate and the exact normalization JSON
bytes derived from that report. Each must be bound by SHA-256 and byte length.
The build report must expose every package identity, lock checksum, literal
metadata field, and per-file SHA-256/byte length for `LICENSE*`, `COPYING*`,
`NOTICE*`, and `COPYRIGHT*` candidates. The normalization report must preserve
literal strings, license-file declarations, material identities, and an
unresolved set without rewriting strings to SPDX or deciding NOTICE duties.

T17 still needs owner/legal review inputs for first-party scope, dependency
distribution rights, and NOTICE/distribution obligations. Cargo `license`
strings are input metadata only.
