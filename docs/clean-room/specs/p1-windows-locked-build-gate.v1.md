# P1 Windows Locked Build Gate Specification v1

## Scope

This specification covers the P1-11 Windows x86_64 build, isolated install
smoke, and exact product-schema drift gate. It is a worktree-external build
verification tool, not a release archive or promotion mechanism.

## Observable Behavior

The gate requires a tracked, unchanged workspace `Cargo.lock`, a fixed source
commit, and the `x86_64-pc-windows-msvc` target. It runs format, clippy, tests,
a locked release build, and a locked `cargo install` into caller-provided
external directories. The installed `sipi.exe` is run only for P1 static
commands and one valid contract-validation request using a scrubbed
environment.

The registered product schemas have exact, tracked baseline bytes. The gate
reads the installed CLI schema registry, requires the same schema identifier
set, and byte-compares each deterministic JSON export with that baseline. A
machine-readable external report records only commit, toolchain, digest,
command, and outcome evidence.

## Non-Claims

This gate does not create an archive, prove twin-build identity, invoke the
P1 release-layout verifier, sign or publish anything, resolve legal/NOTICE
status, certify platforms, execute a simulation, or establish legacy/profile
parity.
