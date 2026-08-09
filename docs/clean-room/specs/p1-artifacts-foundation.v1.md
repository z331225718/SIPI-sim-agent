# P1 Artifacts Foundation Specification v1

## Scope

This specification covers `crates/sipi-artifacts/**` for P1-05. It defines a
local immutable publication primitive for application-owned artifact roots. It
does not define a CLI, a domain result, a simulation algorithm, or a runtime
policy.

## Allowed Materials

The implementation may use this independently authored specification, the P1
contracts foundation specification, the Rust standard library, and the
declared SHA-256 dependency. It must not consume legacy source, oracle output,
external engine, vendor asset, or legacy artifact format.

## Observable Behavior

An artifact root creates staging directories beneath its own `.staging`
directory. A caller selects a valid artifact identifier and stages bounded
byte streams under validated relative UTF-8 paths. Each staged file receives a
byte count and SHA-256 record. Duplicate paths, unsafe paths, symlinks, and
existing final artifact identifiers are rejected.

Sealing re-reads every staged regular file before writing the final
`success.json` manifest. Publishing renames only a fully sealed, previously
nonexistent directory to `root/<artifact-id>` and never replaces or merges a
published artifact. Consumers accept a published artifact only when the
manifest is valid, the file set is exact, and all file lengths and SHA-256
values re-verify. A failed or indeterminate publication is not a success.

The serialization of the manifest reuses the P1 contracts deterministic
serialization profile. It is not claimed to be cross-language canonical JSON.
The version 1 root is application-owned and has no hostile concurrent writer;
symlink checks do not claim to eliminate filesystem TOCTOU races.

## Non-Claims

This specification does not define artifact cleanup, retention, crash
recovery, remote storage, signatures, compression, encryption, ACL hardening,
cross-process locking, CLI/stdin behavior, cancellation, timeout, provenance
semantics, numerical output, legacy compatibility, profile accuracy, platform
certification, release readiness, or strict clean-room process.
