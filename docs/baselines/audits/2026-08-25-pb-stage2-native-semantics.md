# PB stage 2 native semantics audit

Date: 2026-08-25

## Scope

This audit covers the additive PB stage 2 slice bound by
`docs/baselines/pb-stage2-native-semantics.v1.yaml`, whose status remains
`pending_immutable_external_replay`.  The production path is
the existing `SimulationInputV1 -> simulate_native_v1 -> SimulationOutputV1`
engine in `crates/sipi-pybert-direct`; no second simulation core was added.

The pinned comparison source is Py-bert-agent commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`.  Per-path upstream objects and
the license boundary are recorded in
`crates/sipi-pybert-direct/SOURCE-MAP-PB-STAGE2.md` and the existing
`NOTICE-PYBERT-LICENSE-BOUNDARY.md`.

## Implemented semantic slice

The native jitter stage now consumes the explicit typed DFE
`decision_scaler` when it calls the existing modulation-aware crossing helper.
This matches the pinned PyBERT Duo-binary threshold contract (`+/-0.5 *
decision_scaler`) while preserving the zero-threshold NRZ/PAM4 behavior.  A
missing DFE does not create an implicit configuration; the existing explicit
zero-stage behavior remains unchanged.

The compare workflow now gates the complete typed output envelope in addition
to all numeric arrays and metrics.  Nested `SimulationOutputV1.arrays` and
`SimulationOutputV1.metrics` are canonical; when a legacy flat `arrays` or
`metrics` projection is also present, ingestion requires an exact shape/value
match before comparison proceeds.  A drift is rejected before the top-level
projection can mask the nested payload.  Schema, capabilities, ordered
stage-event payloads, and artifact references are compared; artifact name/id,
schema, relative path, MIME type, SHA-256, and byte length use strict equality
rather than numeric tolerance.  Run IDs remain provenance-only so fresh runs
can be compared without a false mismatch.  An incomplete flat external result
is therefore not silently treated as a complete equivalent.

The branch matrix exercises NRZ, PAM4, Duo-binary, explicit TX/RX FFE and
CTLE/DFE selection, explicit bypass, and the new Duo-binary jitter scaler
path.  Workflow mutation coverage exercises schema, capabilities, events,
artifacts, arrays, and metrics.

## Verification performed

The following completed successfully from the crate-local locked manifest:

* `cargo fmt --manifest-path crates/sipi-pybert-direct/Cargo.toml -- --check`
* `cargo test --manifest-path crates/sipi-pybert-direct/Cargo.toml --locked --test native_branch_matrix` (15 passed)
* `cargo test --manifest-path crates/sipi-pybert-direct/Cargo.toml --locked --test workflows` (16 passed)
* `cargo test --manifest-path crates/sipi-pybert-direct/Cargo.toml --locked --test legacy_runtime` (6 passed)
* `cargo clippy --manifest-path crates/sipi-pybert-direct/Cargo.toml --locked --all-targets -- -D warnings`

The focused output-envelope test covers schema, capabilities, ordered events,
arrays, metrics, and artifact hash/path/byte-length mutations.  A separate
workflow test covers a valid nested-plus-flat payload and fail-closed metric
and array projection drift.  `git diff --check` also passed for the working
tree.

The dedicated evidence verifier returned `valid: true`; its mutation suite
contains 15 tests covering status promotion, false and string-typed claims,
extra claims, exact branch/test tuples, coordinated branch/status payload
mutations, reciprocal physical harness hashes, source drift, and audit drift.

## Deliberate non-claims and blockers

No clean immutable candidate preparation commit or two-fresh complete-output
external replay is bound by this audit.  Consequently this evidence does not
claim Python payload parity, global PB-02/PB-03 closure, release approval, or a
license decision.  S2P/analytic-metallic oracle parity, AMI/IBIS/DLL behavior,
and exact Python `PyBertData` class pickle compatibility remain external or
fail-closed under the existing notices and manifests.
