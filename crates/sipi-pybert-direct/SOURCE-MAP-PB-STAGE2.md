# PB stage 2 source map

Scope: the second-stage native PB lane only.  This document binds the small
semantic correction and the complete typed-output comparison added on top of
the existing `SimulationInputV1 -> simulate_native_v1 ->
SimulationOutputV1` path.  It does not add a simulation engine, copy Python
runtime code, or promote an external-model boundary.

## Pinned upstream

The comparison source is the Py-bert-agent repository at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` (tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`).  The exact upstream objects
relevant to this stage are:

| Upstream path | Git blob | Rust destination / use |
| --- | --- | --- |
| `native/pybert-core/src/simulation.rs` | `1f19bff64315e0042bab89d67e9131c289f5e583` | Existing `src/simulation.rs`; jitter stage assembly and waveform-to-crossing calls |
| `native/pybert-core/src/jitter.rs` | `92e0fd6e6b2d40590b967f5f5d057a3de2969672` | Existing `src/jitter.rs`; modulation-specific crossing thresholds |
| `native/pybert-core/src/input.rs` | `ae6d1883b65640d1719022df2c9e8b0763636dc0` | Existing `src/input.rs`; typed `DfeConfigV1.decision_scaler` contract |
| `native/pybert-core/src/output.rs` | `54cfa6b4d51c6ef923885d29a9004dd5265b26d2` | Existing `src/output.rs`; typed output envelope and artifact references |
| `native/pybert-core/src/event.rs` | `525cf44fb2b50ffc79f1b9efa1fadd138369ca41` | Existing `src/event.rs`; ordered stage-event contract |
| `src/pybert/models/bert.py` | `f04340c1028078175b26d7882efeeaf96f001abf` | Semantic reference only: passes `decision_scaler` to all jitter crossing calls |
| `src/pybert/utility/jitter.py` | `467cd706906352883d9784ff29b17610034aede5` | Semantic reference only: Duo-binary thresholds are `+/-0.5 * amplitude` |

The two Python blob IDs are recorded as provenance for the behavior being
matched; Python is not invoked by the production Rust path.  The existing
`SOURCE-MAP.md`, `SOURCE-MAP-PB01.md`, and `docs/baselines/pb-02-direct-port.v1.yaml`
remain authoritative for the copied native-core file inventory and its
adapted-file hashes.

## Stage 2 changes

| Local path | Change | Boundary |
| --- | --- | --- |
| `src/simulation.rs` | For a typed DFE, pass `DfeConfigV1.decision_scaler` to the existing `find_crossings` call.  NRZ/PAM4 remain zero-threshold; Duo-binary uses the two signed half-scaler thresholds already defined by the pinned jitter routine. | Reuses the existing native core; no default DFE, auto-tuning, or fallback is introduced. |
| `src/workflows.rs` | Compare `SimulationOutputV1.schema`, nested arrays/metrics, capabilities, ordered stage events (excluding run IDs), and artifact references in addition to the legacy projection, metadata, and diagnostics. | Nested arrays/metrics are canonical; any coexisting flat projection must exactly match before comparison. Artifact name, schema, path, MIME type, SHA-256, and byte length are strict fields. `run_id` remains provenance-only; incomplete external envelopes fail the comparison instead of being silently synthesized as equivalent. |
| `tests/native_branch_matrix.rs` | Focused Duo-binary jitter test with an explicit typed DFE decision scaler. | Test-only coverage of an existing branch. |
| `tests/workflows.rs` | Mutation coverage for capabilities and event payloads. | Test-only complete-envelope gate coverage. |

## Explicitly retained external or fail-closed

This stage does not claim or implement S2P/analytic-metallic parity, AMI/IBIS
models, TS4/GetWave DLLs, adaptive hidden defaults, Python legacy execution, or
exact `PyBertData` class pickle compatibility.  Those paths remain governed by
the existing PB manifests and boundary notices; an unsupported request must
remain an explicit external/fail-closed result.

## License boundary

The copied native-core license ambiguity and required notices are unchanged
and are defined by `NOTICE-PYBERT-LICENSE-BOUNDARY.md`.  This stage adds no
upstream byte copies and does not change the crate's non-distributed status.
The source mapping above is provenance, not a legal conclusion or a grant of
redistribution rights.

## Verification status

The focused stage tests are expected to run with the crate-local locked Cargo
manifest.  No two-fresh external oracle claim is made by this source map; a
future bound replay must use a clean immutable candidate archive and compare
the complete typed output envelope as well as every numeric payload member.
