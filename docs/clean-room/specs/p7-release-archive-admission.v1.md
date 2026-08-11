# P7 Release Archive Admission v1

## Scope

This is a bounded, no-extract scanner for an explicit external ZIP archive.
It verifies a deliberately narrow provisional capsule: exactly `sipi.exe` and
the root MIT `LICENSE`. It binds the executable bytes to a P7-02a composition
report and binds the license bytes to the report's exact source commit.

## Required Behavior

The caller supplies an external archive, P7-02a composition report, policy,
and fresh external report destination. The scanner reads ZIP members directly
from memory and never extracts them. It accepts only exact ASCII entry names,
the two policy-defined roles, regular stored or deflated entries, bounded
archive/member/total sizes, and a bounded compression ratio. Every byte is
streamed through SHA-256 and must match its declared evidence source.

Directories, duplicate or case-colliding names, non-ASCII names, traversal,
Windows drive/UNC/ADS forms, comments, encryption, data descriptors, ZIP64 or
other unsupported features, links, unknown entries, CRC/read failures, and
resource-limit violations are rejected. The output omits source paths,
original entry names, payload bytes, comments, and external asset identities.

An archive producer for this provisional capsule must therefore emit a
single-disk ZIP with no comment or data descriptors, no ZIP64 records, and
only stored or deflated regular files. A producer that cannot satisfy this
format is rejected rather than receiving a compatibility exception.

`observe` may emit an admission report with `promotion_status: blocked`. The
default `release-gate` mode always fails nonzero because the associated
composition evidence remains provisional.

## Non-Claims

This scanner does not create, publish, sign, install, or approve an archive.
It is not an SPDX/CycloneDX SBOM, authorized NOTICE, legal compatibility
finding, full PE/dynamic-load closure, hostile-writer containment, or
fresh-machine certification. Byte identity with the staged executable only
inherits P7-02a's static PE observation; dynamic and runtime closure stay
unassessed.
