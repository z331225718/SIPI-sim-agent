# P1-11 Windows Locked Build Audit

Date: 2026-08-10

## Slice

Commit `00f92d8` adds the worktree-external Windows x86_64 P1 build gate. It
requires a tracked and unchanged `Cargo.lock`, uses an explicit Rustup
toolchain, sends Cargo home, target output, install prefix, and report outside
the workspace, and runs locked fmt, clippy, test, release build, and install.

The installed CLI smoke checks static P1 commands, one valid stdin validation
request, and the fail-closed `run` response under a scrubbed environment. A
tracked schema inventory binds the registered `sipi.capabilities.v1` export to
its exact deterministic JSON bytes. The gate rejects a changed schema registry
or bytes.

## Verification

- Focused gate tests passed; the Python tool suite reports 110 tests passed.
- Workspace fmt, test, and clippy with warnings denied passed.
- An external Windows gate run for commit `00f92d8` passed: five locked build
  commands and seven installed-CLI smoke commands completed successfully.
- P0 product boundary, clean-room register, release-license preflight, and
  Rust source-map verifiers remain valid and provisional.

## Independent Audit

OMP request `msg_5a5466ccc733` reviewed the committed slice. Conclusion
`msg_3be9db971d58`: 0 P1 / 0 P2.

## Scope Limits

This gate does not create a release archive, prove twin-build identity, invoke
P1-10 stage layout checks, grant MIT/legal/NOTICE approval, certify a platform,
run a domain simulation, or establish legacy/profile parity.
