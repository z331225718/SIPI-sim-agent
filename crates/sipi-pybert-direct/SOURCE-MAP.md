# PB-02 direct-port source map

Scope: the pinned PyBERT `native/pybert-core` implementation used by the
`sim-native` workflow. This map records provenance for quarantined migration
code; it does not promote PB-02 or authorize distribution.

The following seventeen upstream paths are copied byte-for-byte to the same
basename in `src/`: `analysis.rs`, `bathtub.rs`, `capabilities.rs`,
`channel.rs`, `decoder.rs`, `equalization.rs`, `error.rs`, `event.rs`,
`jitter.rs`, `output.rs`, `pattern.rs`, `pipeline.rs`, `receiver.rs`,
`response.rs`, `signal.rs`, `statistical_eye.rs`, and `units.rs`.

`input.rs` and `simulation.rs` remain bound to their pinned upstream Git
objects but carry two small, additive portable Touchstone CTLE adaptations:
the typed imported impulse field/validation and its native consumption branch.
Their source/target hashes and deltas are recorded under `adapted_files` in
`docs/baselines/pb-02-direct-port.v1.yaml`; the numerical pipeline otherwise
continues to call the copied native core stages.

The authoritative per-file Git blob and SHA-256 table is
`docs/baselines/pb-02-direct-port.v1.yaml`. `src/lib.rs` is separately bound to
the pinned upstream module/re-export root and differs only by the additive
`runner` module and re-exports. `src/runner.rs`, the CLI binary, fixture, and
direct-boundary tests are SIPI migration scaffolding and are not copies of
upstream source files.

License metadata and its unresolved boundary are recorded in
`NOTICE-PYBERT-LICENSE-BOUNDARY.md`.
