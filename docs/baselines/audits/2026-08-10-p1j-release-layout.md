# P1-10 Release Layout Verifier Audit

Date: 2026-08-10

## Slice

Commit `f7632a6` adds `sipi-layout-verify`, a Windows x86_64 verifier for an
externally constructed stage directory. It checks a closed file allowlist,
rejects unsafe links and reparse points, parses the executable as AMD64 PE,
allows only declared normal imports, rejects delay-import directories, and
runs only policy-declared static CLI smoke commands with a scrubbed
environment.

The verifier reports `layout_conformant` only. The current product boundary is
provisional, so it cannot report release readiness. Its report explicitly does
not claim hostile-filesystem containment or that arbitrary future commands
cannot start child processes or dynamically load code.

## Verification

- `python -B -m unittest discover -s tools -p 'test_*.py'`: 107 passed.
- `cargo fmt --check`, `cargo test --workspace --locked`, and workspace
  clippy with warnings denied: passed.
- P0 product boundary, clean-room register, release-license preflight, and
  Rust source-map verifiers: passed with their existing provisional status.

## Independent Audit

OMP request `msg_406dba36556b` reviewed the committed slice. Conclusion
`msg_7d4148f5570c`: 0 P1 / 0 P2.

## Scope Limits

This is not package/archive validation, a twin build, an installation smoke,
release promotion, legacy compatibility, numerical/profile evidence, or a
general no-child/no-dynamic-load proof. Those boundaries remain separate.
