# PB-01 direct-port workflow-boundary audit

Date: 2026-08-23

## Scope

This audit freezes the public `sim` workflow at the pinned PyBERT commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`. The CLI blob is
`4c1116007d31bcebf8db3252363eed7774c7b349` with content SHA-256
`3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9`.
The source was inspected through the pinned Git objects; no PyBERT Python
source, fixture, array, pickle, DLL, or local source path is copied into SIPI.

PB-01 is materially different from PB-02. `sim` accepts a legacy
`PyBertCfg` YAML or pickle configuration, always selects the Python backend,
calls `PyBERT.simulate(initial_run=True, update_plots=True)`, and writes one
opaque `PyBertData` pickle. PB-02 instead accepts strict versioned JSON,
selects the native Rust backend, and writes `meta.json` plus `arrays.npz`.
The PB-01 legacy parser, Python simulation graph, optional model/DLL paths,
and pickle codec are therefore not inferred from the PB-02 native contract.

## Frozen branch and error inventory

The command shape is `sim CONFIG_FILE [--results RESULTS_FILE]`. Click checks
that `CONFIG_FILE` exists before dispatch. `PyBertCfg.load_from_file` accepts
`.yaml`, `.yml`, and legacy `.pybert_cfg`; YAML uses the pinned safe loader
with only the `PyBertCfg` and tuple constructors, while `.pybert_cfg` uses the
legacy pickle loader. Other suffixes raise `InvalidFileType`, malformed YAML
or a wrong object type raises from the configuration loader, and simulation
backend failures propagate from `PythonSimulationBackend`.

There is no PB-01 auto/compare selector and no silent native fallback. The
backend is explicitly the Python reference backend. The CLI invokes
`backend.validate(pybert)`, then `backend.run` with an always-false abort
callback and a no-op stage callback. The backend calls `PyBERT.simulate` with
`initial_run=True` and `update_plots=True`.

When `--results` is omitted, the default is exactly
`Path(CONFIG_FILE).with_suffix(".pybert_data")`. An explicit result path is
passed through unchanged. `PyBert.save_results` serializes a `PyBertData`
object with Python pickle. Its save helper catches write errors and logs them;
therefore a Rust replacement must require the result-file postcondition rather
than treating a zero exit status as success. The candidate does not decode
the pickle and does not claim compatibility with its internal arrays.

## Rust candidate boundary

`crates/sipi-pybert-direct/src/legacy_sim.rs` adds only a typed request,
default-result-path resolution, extension/existence checks, exact argv
manifest, and an explicit `BlockedLegacyProjection` status. It does not parse
legacy YAML or pickle, run the Python numeric graph, or guess a
`SimulationInputV1` from a partial config. It names the existing
`run_sim_native_file` core entry point as reusable infrastructure for a later
proven projection; no new numerical algorithm was added here.

This is a candidate-only boundary slice. It is not PB-01 runtime integration,
not a product route, and not numeric parity.

## Supersession relationship

This record is retained as the predecessor branch/default/error/artifact
inventory. Its boundary-only implementation status is superseded for the
scoped NRZ metallic-line leaf by
`docs/baselines/pb-01-legacy-leaf.v1.yaml`. The executable leaf does not close
the imported-model, pickle-config, noise, adaptive equalization, analysis, or
class-compatible result branches frozen here, so this inventory remains in
force for all those open paths.

## Two-stage oracle preparation

`tools/run_pb_01_direct_replay.py` has two explicit stages. Stage one
materializes immutable candidate and upstream Git archives, snapshots source
inventories before generated files, and records only a caller-owned config
hash/size/extension. Stage two can run the pinned external `pybert sim` and a
caller-supplied candidate process with identical config bytes. It inventories
only the result-file existence, size, and SHA-256; it never decodes or stores
pickle payloads. Without a candidate executable it remains `prepared_open`.
`tools/aggregate_pb_01_direct_replay.py` enforces distinct reports, run IDs,
nonces, source/config identity, and path-free report IDs, but remains blocked
until a legacy-config projection and result comparator exist.

No two-run PB-01 report is bound by this slice. A future replay must bind a
new immutable candidate commit, a branch-complete config corpus, and an
independent opaque-payload comparator before any parity claim.

## License and non-claims

The PyBERT root is BSD-3-Clause and remains an external/quarantined source
boundary. The Rust lane remains subject to the existing native-core
MIT/BSD-license review. The implementation agent did not directly edit
`license-manifest.v1/v2`, `product-boundary.v1`, the shared source map, or P0;
this slice itself makes no promotion, while the coordinating batch may
mechanically rebind those records after review. This audit is not a license,
redistribution, product-capability, or release decision.
