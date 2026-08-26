# PB-03 payload serializer source map

This file maps the narrow Rust serializer projection to the pinned PyBERT
production paths. It is not a license grant and does not claim that the Rust
crate contains the upstream implementation.

## Candidate implementation

- `src/legacy_runtime.rs`: `augment_sim_rust_result_arrays_v1` validates and
  projects the already materialized `SimulationOutputV1.arrays` map.
- `src/workflows.rs`: `run_projected_input` invokes the projection after
  `simulate_native_v1` and before the existing artifact writer.
- `src/runner.rs`: the existing `SimulationOutputV1` serializer writes the
  resulting map to the existing `arrays.npz` and nested metadata envelope.

The projection is called only for `sim-rust`. The `sim-native` output contract,
`sim-compare`, and external AMI/IBIS paths are unchanged.

## Pinned upstream paths

Authority for all mappings below is PyBERT commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` (tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`). The path and line references are
for audit navigation and are not copied source.

The pinned files are bound by Git blob, raw byte length, and SHA-256:

| Pinned path | Git blob | bytes | raw SHA-256 | License mapping |
| --- | --- | ---: | --- | --- |
| `src/pybert_web/engine_adapter.py` | `8cdb9fb612635b58cf2e071a9e90d07d272faa61` | 50326 | `c86a84a9787c542b81247784eb14a1a4c7aa266c36a2e33e73a7e74f7c2452b5` | BSD-3-Clause via pinned `LICENSE` |
| `src/pybert_web/simulation.py` | `cdc065bd692ca4836a7c62eb5a71492ff34620c1` | 45813 | `e5e0c0ba1e3cdc4356f027a8ea79a1e459d11377657a1ba231be5b7cbdf98c3c` | BSD-3-Clause via pinned `LICENSE` |
| `LICENSE` | `64d198ba43675ede5fbdef1ec918a63954951640` | 1466 | `4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1` | BSD-3-Clause; copyright David Banas |

These bindings identify the semantic reference and its license. They do not
change the SIPI-owned Rust files' license or expand this direct-port beyond the
mechanical operations below.

| Rust projection | Pinned production path | Mechanical operation |
| --- | --- | --- |
| `t_ns_chnl`, `chnl_h`, `chnl_s`, `chnl_p` | `src/pybert_web/engine_adapter.py:635-655`; `src/pybert_web/simulation.py:787-811` | Reuse channel impulse, peak-centered time, cumulative sum, and delayed difference. |
| `f_GHz`, `chnl_H_raw`, `chnl_H`, `chnl_trimmed_H`, `tx_H`, `tx_out_H`, `ctle_H`, `ctle_out_H`, `dfe_H`, `dfe_out_H`, `rx_out_H` | `src/pybert_web/engine_adapter.py:600-649`; `src/pybert_web/simulation.py:823-847` | Scale existing frequency bins and take magnitude of existing real/imaginary telemetry. |
| `parity_channel_impulse_v_per_v`, `parity_ctle_output_v`, `parity_rx_output_v`, `parity_dfe_output_v`, `parity_dfe_decisions`, `parity_dfe_clock_times_s` | `src/pybert_web/engine_adapter.py:440-444`; `src/pybert_web/simulation.py:772-777` | Direct array aliases. |
| `jitter_bins` | `src/pybert_web/engine_adapter.py:681-685`; `src/pybert_web/simulation.py:771` | Alias existing `jitter_bin_centers_s`. |
| `bathtub_chnl`, `bathtub_tx`, `bathtub_ctle`, `bathtub_dfe`, `bathtub_rx` | `src/pybert_web/engine_adapter.py:687-692`; `src/pybert_web/simulation.py:624-770` | Apply the pinned `log10(max(value, 1e-13))` presentation to existing BER curves; RX aliases DFE. |

## Explicitly not ported

The pinned adapter creates `eye_*` and `native_eye_*` display matrices through
its eye extraction/resampling path. The current typed Rust output does not
contain those 2-D sources. The projection therefore does not recreate that
algorithm. The candidate/oracle contour count also remains 2 versus 3 and is
recorded as drift rather than guessed.

AMI, IBIS, DLL, GetWave, vendor noise, and exact `PyBertData` class pickle
behavior are outside this map. No public wire schema v2 or second engine was
introduced.
