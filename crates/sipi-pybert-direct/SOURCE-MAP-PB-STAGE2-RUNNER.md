# PB stage 2 runner source map

Scope: the additive public artifact boundary for the existing PB stage 2
native engine.  This map covers the runner-only changes that publish the
typed `SimulationOutputV1` envelope beside the pinned CLI projection.  It
does not add a numerical engine, copy Python runtime code, or make an
external parity claim.

## Pinned provenance

The runner consumes the Py-bert-agent native contract at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` (tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`).  The path-level custody below
uses the upstream Git blob ID, byte length, and SHA-256 of the exact blob
bytes.  `LICENSE` is the governing license object for these paths.

| Upstream path | Blob ID | Bytes | Blob SHA-256 | Local source port / adaptation |
| --- | --- | ---: | --- | --- |
| `native/pybert-core/src/output.rs` | `54cfa6b4d51c6ef923885d29a9004dd5265b26d2` | 4359 | `74a54504c38424532f19fa0f6a9b22942b07694ef771d4d3ab37dda1e7b3b1ac` | `src/output.rs`; typed `SimulationOutputV1`/`ArtifactRefV1` contract is ported, no runner fields added |
| `native/pybert-core/src/simulation.rs` | `1f19bff64315e0042bab89d67e9131c289f5e583` | 85056 | `99425e94e6336dd39330ce6c1db4bbd0c43699ed7abc9e8a1fe8f56acde239fd` | `src/simulation.rs`; the single numerical `simulate_native_v1` engine, with stage-local Rust adaptation recorded by the stage-2 map |
| `src/pybert/cli.py` | `4c1116007d31bcebf8db3252363eed7774c7b349` | 12806 | `3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9` | `src/runner.rs`; `_write_native_artifacts` file names and outer CLI schema are adapted, not copied as Python |
| `native/pybert-python/src/lib.rs` | `89aa11197349da28f7a8d1427113d5ff3ff65f9b` | 63916 | `d6cdd06c3fb6a86efe8af0616fc6ef9e1e896fcac9262a339e5cf30877f6ed13` | `src/runner.rs`; JSON camelCase field spelling is adapted from the native Python extension boundary |
| `LICENSE` | `64d198ba43675ede5fbdef1ec918a63954951640` | 1466 | `4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1` | `NOTICE-PYBERT-LICENSE-BOUNDARY.md`; provenance only, not a redistribution decision |

The existing `SOURCE-MAP-PB-STAGE2.md` and
`NOTICE-PYBERT-LICENSE-BOUNDARY.md` remain authoritative for copied native
objects and licensing.  This file records the runner adapter only; it is not
a legal conclusion or a redistribution grant.

## Boundary contract

`run_sim_native_json` and `run_sim_native_input` execute the same
`simulate_native_v1` engine and pass its validated result to
`write_simulation_artifacts...`.  The writer now serializes that exact typed
result under `meta.json.output`.  `backend_metadata.schema`, `run_id`, and
`metrics`, plus `diagnostics.capabilities` and `diagnostics.events`, are
mechanical projections of the nested result.  Consumers must use the nested
`SimulationOutputV1` as canonical and reject a coexisting flat projection
that drifts.

The pinned `src/pybert/cli.py::_write_native_artifacts` does **not** publish
`effective_randomness`; that field is candidate-adapter provenance owned by
this Rust boundary.  The runner removes the engine-only
`effective_prbs_seed` metric from the narrow `sim-native` direct projection so
the typed metrics match the pinned CLI payload.  The candidate's separate
`meta.json.effective_randomness` remains explicitly local provenance and is
not attributed to upstream.

The writer keeps the existing `arrays.npz` artifact and enforces a bounded
16 MiB metadata budget.  Before any `serde_json::to_value` materialization, a
borrowed `MetadataEnvelopeV1` is streamed through the same pretty-JSON writer
used for `meta.json`.  It includes every final field and duplicate projection:
the input, nested output arrays/metrics/capabilities/events/artifacts,
`backend_metadata`, `effective_randomness`, diagnostics, both workflow
namespaces, `artifact_schema`, `backend_label`, and the canonical source path.
The bounded writer counts actual serialized bytes, indentation, keys, and
punctuation and fails closed at the limit; it uses no fixed overhead estimate.
Typed artifact references, when supplied by a workflow, retain all six
required fields (`name`, `schema`, `relativePath`, `mimeType`, `sha256`, and
`byteLength`) and are validated by `SimulationOutputV1::validate`.

The native f64 `sim-native` direct path writes the same one-dimensional
`SimulationOutputV1.arrays` values to `arrays.npz`; the artifact-reference
test verifies the on-disk logical payload.  The generic
`...and_typed_arrays` adapter may preserve bool/int/2-D source dtypes and does
**not** claim that its nested f64 projection is byte- or logical-identical to
the typed NPZ payload.

Workflow extras are retained without authority over canonical fields.  Safe
nonreserved keys retain their established compatibility locations; reserved
collisions are isolated under `workflow_metadata` or
`workflow_diagnostics`, and canonical schema/output/backend/capability/event
fields are written last.

## Verification

`tests/direct.rs::direct_run_writes_upstream_artifact_names_and_metadata`
round-trips the emitted nested value through `SimulationOutputV1`, checks
mechanical projection equality, checks the candidate-only randomness split,
verifies six-field artifact references after disk deserialization, checks the
native NPZ logical payload, exercises reserved workflow collisions, and
exercises the metadata preflight/overflow gates.  The complete-output
comparison and strict artifact field gate remain in `src/workflows.rs` and
`tests/workflows.rs` as recorded by the stage 2 source map.
