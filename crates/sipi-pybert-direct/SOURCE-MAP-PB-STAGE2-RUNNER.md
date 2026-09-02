# PB stage 2 runner source map

Scope: the artifact boundary for the existing PB stage 2 native engine. This
map distinguishes the pinned `sim-native` compatibility artifact from the
SIPI-owned rich writer used by projected workflows. It does not add a
numerical engine, copy Python runtime code, or make an external parity claim.

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

`run_sim_native_json` executes `simulate_native_v1` and then writes the six
top-level fields published by pinned `src/pybert/cli.py::_write_native_artifacts`:
`schema`, `input_file`, `effective_input`, `backend_metadata`, `diagnostics`,
and `arrays_file`. It deliberately does not inject the SIPI nested
`SimulationOutputV1`, `effective_randomness`, source custody, workflow
namespaces, or artifact references into the compatible `meta.json`.

The source request adapter drops `analysis.jitterRelThresh` from
`effective_input`: that is a SIPI control absent from the pinned Python
request model and Pydantic drops it before the source CLI writes its artifact.
The direct writer also projects the source build-info shape (`name`, `version`,
and profile/target/build id) from the same Rust compile-time facts as
`native/pybert-python/src/lib.rs::native_build_info`. This is artifact-wire
compatibility, not a claim that this executable is the upstream Python wheel.
The crate and source maps remain the authoritative provenance for the actual
direct-port executable.

`run_sim_native_input` and explicit rich-writer callers retain the SIPI-owned
nested envelope/provenance form for projected workflows. Their 16 MiB
streaming preflight, reserved workflow namespaces, typed artifact references,
and all six artifact-reference fields remain outside the pinned `sim-native`
wire contract.

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
checks the exact six-key source envelope, source-shaped build metadata,
absence of `jitterRelThresh`, and the native NPZ logical payload. Separate
rich-writer tests retain the provenance/noise, artifact-reference, reserved
workflow collision, and metadata preflight coverage. The complete-output
comparison and strict artifact field gate remain in `src/workflows.rs` and
`tests/workflows.rs` as recorded by the stage 2 source map.
