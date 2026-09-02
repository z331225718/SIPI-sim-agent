# PB-03 payload serializer source map

This file maps the narrow Rust serializer projection to the pinned PyBERT
production paths. It is not a license grant and does not claim that the Rust
crate contains the upstream implementation.

## Candidate implementation

- `src/legacy_runtime.rs`: `augment_sim_rust_result_arrays_v1` validates and
  projects the already materialized `SimulationOutputV1.arrays` map.
- `src/workflows.rs`: `run_projected_input` invokes the projection after
  `simulate_native_v1`, then direct-ports the pinned Web adapter's private
  presentation metadata before the existing artifact writer.
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
| `src/pybert_web/models.py` | `ec69a14ed97dbb500e57e378c4d8f39d359aaf20` | 11640 | `66194501d7753ddb07105edf9b724095f13682f538585e3ee455dbad5fd554d9` | BSD-3-Clause via pinned `LICENSE` |
| `src/pybert/utility/sigproc.py` | `9e4abd5991e0d31123f5a4b7d3d3c8d618dc7140` | 17416 | `394c8ffebf5ae2c352ab16c0155a1241b84089f6bd8bbb40fc7ce1d73e0758ad` | BSD-3-Clause via pinned `LICENSE` |
| `src/pybert/utility/statistical_eye.py` | `195f87f48cecc55bf7bcda371c4c51b17111ea21` | 38893 | `da70853bde4c0b5f428eef072c47dbd085692744031ce18fce1e0ec079d18895` | BSD-3-Clause via pinned `LICENSE` |
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
| `result_mode`, `channel_semantics`, eye ranges/samples/statistical summary, FOM/BER/eye/jitter/randomness/shape/presentation metadata | `src/pybert_web/engine_adapter.py:693-852` | Assemble the same metadata only from the admitted typed-RLGC request, existing waveform/clock/metric/contour telemetry, and the serializer's existing eye shapes. No second simulation or public metadata API is introduced. |

## Eye and contour follow-up

- `src/pybert_web/models.py` defines the pinned default with
  `statistical_ber_levels = [1e-5, 1e-4, 1e-3]`. `project_legacy_config_v1` and the workflow fallback
  now pass that list to the existing typed `StatisticalEyeConfigV1`, and the
  existing `calculate_statistical_contours` operation emits one summary and
  coordinate pair per requested level. This is parameter plumbing only; it
  does not add a visual-eye algorithm. The pinned contour semantics are mapped
  to `src/pybert/utility/statistical_eye.py`; the Rust implementation remains
  the already admitted typed contour operation.
- The third contour summary and its `eye_contour_2_x_ui` /
  `eye_contour_2_y_v` keys are therefore materialized by the existing typed
  contour operation. Empty coordinates remain empty when that operation finds
  no points; no points are fabricated by the serializer.
- The ten pinned display matrices (`eye_chnl`, `eye_tx`, `eye_ctle`,
  `eye_dfe`, `eye_rx`, and the five `native_eye_*` fields) are produced from
  the already computed typed waveforms using the bounded `calc_eye` and
  order-one presentation projection. Their raw/display shapes are retained
  for the metadata adapter; this stays presentation-only and does not rerun
  channel or receiver physics.
- The seven response magnitude fields (`chnl_H`, `chnl_trimmed_H`,
  `ctle_out_H`, `dfe_out_H`, `rx_out_H`, `tx_H`, `tx_out_H`) continue to use
  the mechanical magnitude projection above. Their candidate/oracle logical
  f64 hashes drift because the upstream telemetry differs before serialization;
  no serializer-only correction or ULP claim is made.

## Observed boundary and explicit non-claims

The source comparison checks the complete 150-member NPZ payload (names,
dtypes, shapes, and numerical tolerance) and all mechanically derived Web
metadata fields. Two statistical-eye observations remain deliberately visible,
not normalized into product behavior: `eye_distribution_state_count` and
`eye_height_at_ber_v` / `statistical_eye.height_at_ber_v`. They are generated
by the existing native statistical-eye core rather than this serializer and
are not evidence of complete Web-result parity. The direct port therefore
does not claim full PyBERT Web parity, release acceptance, or any correction
of those numerical observations.

AMI, IBIS, DLL, GetWave, vendor noise, and exact `PyBertData` class pickle
behavior are outside this map. No public wire schema v2 or second engine was
introduced.
