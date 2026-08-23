# COM-02 clean-archive immutable evidence v2

This additive evidence binds COM-02 to preparation commit
`64b783f66d7e986d0975be5ac3946b453b15c4ed` and tree
`0e11721f2bb5b564002820cc7a5aaab45e30ba3b`. The binary was built from a
fresh `git archive` with no working-tree overlay. Two independent top-level
fresh runs used distinct run IDs and nonces; each top-level run itself executed
the fixed ten-scenario semantic corpus twice and required identical payloads.

The reports bind the archived runner/helper, v2 wrapper, generated fixture
inputs, candidate archive and binary SHA-256, exact Cargo/Rust toolchain, and
the pinned Agent-COM MIT commit/tree. The payload compares channels, waveform
identity, metrics, portable branch payloads, and artifact manifest semantics.
It is semantic replay evidence only, not numerical parity with MATLAB or a
release/promotion claim.

Each fresh run resolves explicit `cargo.exe` and `rustc.exe`, clears
`RUSTC_WRAPPER`, removes the archive target directory, and rebuilds the
selected binary from that archive. Reports retain only executable basenames,
executable file hashes, version-output hashes, exit/timeout/redaction status,
and relative build identities; no absolute host path is included.

The clean archive source probe confirms both S2P and S4P routes call the
validated `sipi-com::s21_to_impulse_dc_v1` COM impulse leaf, do not use a
matched-kernel/`NotAssessed` fallback, and retain the no-S-parameter-fit
policy. Custody tests remain in the archived Rust test surface and reject
equal, ancestor, descendant, symlink, and hardlink-alias output paths before
artifact mutation; no test or input was supplied from the working tree.

Evidence is recorded in `com-02-direct-port.v2.yaml`, with two reports, one
aggregate, and the clean-archive Rust contract-test result
`com-clean-archive-rust-tests.v2.json` (49 passed). External MATLAB engine, proprietary golden data, and non-core
plotting remain external blockers; no upstream numerical parity is claimed.
