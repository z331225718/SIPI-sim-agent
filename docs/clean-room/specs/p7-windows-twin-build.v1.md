# P7 Windows Twin Build v1

## Scope

This external Windows x86_64 gate materializes two isolated source directories
from the same immutable SIPI Git `HEAD` object. Each directory runs the same
locked, offline release build for `sipi-cli`, with its own external Cargo target
directory and incremental compilation disabled. The gate replaces inherited
`RUSTFLAGS` with the fixed MSVC `/Brepro` linker argument and records its
identity; this prevents PE linker timestamps from creating false twin-build
drift.

The gate records only the commit/tree identity, `Cargo.lock` and toolchain
hashes, target triple, per-build executable size/digest, tool version digests,
and the size/digest comparison. Any missing immutable input, archive safety
failure, toolchain failure, build failure, missing executable, or unequal
output is fail-closed. The default success state is exactly `identical`.

## Isolation

The worktree itself is not a build input: both source copies come from `git
archive HEAD`. Output roots and reports must be outside the workspace. Python
and Conda injection variables are removed; Cargo targets are independent and
offline. The gate does not write a target directory, lockfile, artifact, or
source copy into the workspace.

## Non-Claims

This is provisional twin-build identity evidence only. It does not create a
release archive, validate NOTICE/SBOM, inspect PE imports, sign/publish a
binary, prove fresh-machine installation, certify a profile, or grant release
approval.
