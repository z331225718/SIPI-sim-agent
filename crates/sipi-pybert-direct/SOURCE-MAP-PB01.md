# PB-01 direct-port source map

Pinned source: PyBERT repository `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`,
tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.

The table records the upstream objects that define this additive leaf. The
Rust destination is a projection, not a byte-for-byte copy. Exact source
bytes are not vendored in this PB-01 slice.

| Upstream path | Git blob (SHA-1) | Rust destination / use |
| --- | --- | --- |
| `src/pybert/cli.py` | `4c1116007d31bcebf8db3252363eed7774c7b349` | `src/legacy_sim.rs`, `src/bin/sipi-pybert-direct.rs`: `sim` argv/default path |
| `src/pybert/configuration.py` | `ef24ded89768291e7b5e945fab4fe50be3bd6c2d` | `src/legacy_runtime.rs`: tagged YAML object/tuple projection |
| `src/pybert/pybert.py` | `1af665c4595fff1ff5fb30341fe063bd10e5cd89` | `src/legacy_runtime.rs`: NRZ timing, metallic-line, TX/RX FFE leaf mapping |
| `src/pybert/engine/python_backend.py` | `6b7b664d89da1502c74fc7cd97fe4451bf98ab82` | `src/legacy_runtime.rs`: execute-after-validation workflow boundary |
| `src/pybert/results.py` | `4d8eafa77a20ef8a3ac307f6ae8c0397deb8e907` | `src/legacy_runtime.rs`: 23 canonical result item names and `.pybert_data` suffix |

The analytic metallic-line and convolution implementation is reused from the
already quarantined pinned native Rust core; its separate source/license map is
`SOURCE-MAP.md`. The fixture
`fixtures/pb-01-legacy-nrz.yaml` is authored test input, not an upstream source
copy.

The direct-port boundary intentionally remains scoped at the external/runtime
edges. Imported S2P channel and CTLE files, deterministic random/periodic
noise, adaptive DFE/Viterbi, and jitter/eye/bathtub analysis are now projected
through the same portable native core and covered by the PB-01 branch matrix.
The portable `.pybert_cfg` input branch is admitted by a bounded Rust
pickle-state decoder that accepts only the pinned `PyBertCfg` mapping shape; it
never restores Python classes or invokes a Python runtime. External AMI/IBIS,
TS4/GetWave DLLs, and exact `PyBertData` class pickle compatibility remain
outside this lane.
