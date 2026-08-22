# PB-02 direct-port audit

## Scope

This audit covers only the lane-local `PB-02` `sim-native` direct port in
`crates/sipi-pybert-direct`. It is an exact-source and artifact-boundary audit
for one explicit PRBS7 NRZ impulse-response fixture. It does not promote a
product capability, close the global migration row, or implement PB-03, PB-04,
or PB-05.

## Pinned source and license paths

The source of truth is the clean Git archive/object set for
`Py-bert-agent@5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`. The 19 copied native-core source
files are byte-identical to their pinned Git blobs; their license boundary is
the pinned `native/pybert-core/Cargo.toml`, which declares MIT. The crate root
`src/lib.rs` is separately bound to the pinned upstream `lib.rs`; its only
changes are the additive lane runner module and re-exports.

The Python CLI and backend, root `LICENSE`, and the PyO3 extension were used as
read-only contract/provenance inputs. The Python CLI/backend and root license
are BSD-3-Clause; the extension Cargo manifest declares MIT. The extension
source was not copied into the product lane. These path-level observations are
not a legal conclusion.

## Build closure

The clean pinned native-core archive passed its offline library test (3 tests).
The clean archive containing `native/pybert-python` passed offline Cargo check
and offline release build. The product lane is an independent standalone Cargo
package with an empty `[workspace]` boundary; it does not modify the root
workspace or the existing adapter.

## Runtime and artifacts

The lane admits strict `SimulationInputV1` JSON, rejects unknown fields and
non-object variant payloads, and does not coerce legacy YAML. A successful run
writes `meta.json` and an uncompressed NPZ containing float64 NPY members, with
typed pipeline/capability/event/cancellation diagnostics. Invalid input,
unsupported native input, native execution failures, and artifact I/O failures
return a typed JSON error on stderr and a nonzero exit without success artifacts.
Output-directory links are rejected. These strict-admission, artifact-writer,
NPZ-compression, and symlink policies are SIPI-owned wrapper behavior. They are
not asserted as semantics of the pinned upstream `sim-native` command; the
upstream parity claim below is limited to the native numerical core.

## Fresh replay

The fixture is `crates/sipi-pybert-direct/fixtures/pb-02-nrz.json` with SHA-256
`5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13`. A prior
two-process observation exists, but it was not produced by an immutable
candidate-commit replay runner and is therefore retained only as historical
observation. Current evidence intentionally does not use it as reproducible
candidate admission. After a preparation commit, run
`tools/run_pb_02_direct_replay.py` twice from that immutable commit and combine
the two hash-only reports with `tools/aggregate_pb_02_direct_replay.py`.

Exact parity for the frozen native numerical profile is the next evidence
target, not a current claim. Uncovered input branches, legacy YAML projection,
selection, comparison, wrapper-policy equivalence, and product release
admission remain open by design.
