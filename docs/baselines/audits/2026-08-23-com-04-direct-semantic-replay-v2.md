# COM-04 clean-archive immutable evidence v2

This additive evidence binds COM-04 public `load_config -> run_com ->
write_artifacts` to preparation commit
`64b783f66d7e986d0975be5ac3946b453b15c4ed` and tree
`0e11721f2bb5b564002820cc7a5aaab45e30ba3b`. The public API binary was built
from a fresh `git archive` with no working-tree overlay. Two independent
top-level fresh runs used distinct run IDs and nonces; each top-level run
itself executed the fixed ten-scenario semantic corpus twice and required
identical payloads.

The reports bind the archived public-api runner/helper, v2 wrapper, generated
fixture inputs, candidate archive and binary SHA-256, exact Cargo/Rust
toolchain, and the pinned Agent-COM MIT commit/tree. Semantic payloads include
workflow order, cases/channels, waveform identity, COM metrics, portable
branch payloads, and result/report/diagnostics artifact topology. This is
semantic replay evidence only, not numerical parity with MATLAB or a
release/promotion claim.

Each fresh run resolves explicit `cargo.exe` and `rustc.exe`, clears
`RUSTC_WRAPPER`, removes the archive target directory, and rebuilds the public
API binary from that archive. Reports retain only executable basenames,
executable file hashes, version-output hashes, exit/timeout/redaction status,
and relative build identities; no absolute host path is included.

The clean archive source probe confirms both S2P and S4P routes call the
validated `sipi-com::s21_to_impulse_dc_v1` COM impulse leaf without fitting or
matched-kernel/`NotAssessed` fallback. Archived custody tests cover output
equal/ancestor/descendant relations and symlink/hardlink aliases before
artifact rename/delete; input bytes are hashed by the tests and remain
unchanged on rejection.

Evidence is recorded in `com-04-direct-port.v2.yaml`, with two reports, one
aggregate, and the clean-archive Rust contract-test result
`com-clean-archive-rust-tests.v2.json` (49 passed). External MATLAB engine, proprietary golden data, and non-core
plotting remain external blockers; no upstream numerical parity is claimed.
