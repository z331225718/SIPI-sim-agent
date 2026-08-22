# AS-01 `fit-sparam` immutable replay audit

Date: 2026-08-23

## Scope

This audit binds two independent executions of the bounded AS-01 Rust leaf against the pinned Agent-Spice `fit-sparam` oracle. The candidate is commit `8bcfd1d1bc511461615f19338e453f0148e5dcb1` (tree `ed221a36f2d3325b0aac3f3336a9c8a14d13e99a`). The oracle is Agent-Spice commit `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` (tree `b6bde97128030d6cea0d68b2f0a35d807be8c402`). Both source trees were materialized from Git archives, not from mutable worktree files.

The replay covers the ten scenarios frozen in the archived preparation runner. `target_failure_and_success` is byte-for-byte equivalent in effective arguments to `full_band_defaults`, so it is recorded as duplicate noncoverage rather than an additional numerical branch. Candidate execution is available only for the current bounded two-port leaf. Upstream-only SPICE, RFM, wrapper, and HTML artifacts are inventoried but excluded because the Rust leaf explicitly does not implement them.

## Custody controls

The runner rejects unsafe archive members, duplicate or case-colliding paths, oversized members, and archive/extraction budget overruns. It binds the source commit, tree, selected archive digest, complete extracted inventory, candidate Cargo lock, upstream MIT license, frozen fixture, scenario set, archived preparation runner, and the built executable.

Each run creates a separate Python virtual environment. Dependencies come from `as-01-agent-spice-oracle-windows-py312.lock`, which contains exact versions and hashes and is installed with `uv pip sync --require-hashes --strict`. The report binds the complete installed distribution inventory and NumPy/SciPy configuration digest. Python isolation clears inherited Python environment state and fixes numerical thread counts to one.

Candidate builds use the same explicitly resolved Rust compiler, clear wrapper variables, disable incremental compilation, set `SOURCE_DATE_EPOCH=0`, remap source and target prefixes, set a fixed Rust metadata value, and request reproducible MSVC linking. The two builds produced the same executable SHA-256. Reports contain only path-redacted tool identities. The aggregate rejects report-path aliasing, run ID or nonce reuse, report digest reuse, source/toolchain/environment drift, executable drift, and path leakage.

The formal harness and dependency lock are content-addressed in every report by SHA-256 and Git blob SHA-1, but they remain pending an owner commit. This is an explicit custody limitation, not concealed provenance. The candidate and upstream sources under test are immutable committed objects.

## Semantic comparison

Report parsing is schema-specific: Agent-Spice uses `best_effort_final_mean_rms`, while the Rust result uses `rms_error`. Fitted Touchstone files are independently parsed into canonical frequency and complex RI f64 streams. The runner recomputes full-band RMS, priority-band RMS, and sampled-grid maximum singular value rather than trusting either implementation's summary alone.

For the common `full_band_defaults` leaf, Agent-Spice reports RMS `0.030266038995446727`; Rust reports `0.37790224348580714`, an absolute delta of `0.3476362044903604`. Independent fitted-Touchstone RMS values are `0.030266038995446727` for Agent-Spice and `0.18895112174290357` for Rust. Sampled-grid maximum singular values are `0.5` and `0.566611420285334`, respectively. The differing report and independent metrics are intentionally preserved.

## Result and non-claims

The replay custody completed successfully, but numerical parity did not. The evidence status is `completed_numeric_mismatch`; `numeric_mismatch_open` remains true and no acceptance tolerance is set. The old preparation-only statement is superseded only by these bounded external reports. Nothing here closes AS-01, promotes a product capability, proves complete CLI or artifact parity, proves continuous passivity, establishes acceptance, approves release, or changes license admission.
