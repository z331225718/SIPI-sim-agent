# COM-04 direct public API semantic replay audit

Status: scoped open.  This audit covers the fixed Agent-COM commit
`5272ffe74702cd585054d975559b06f8afae7b6e` / tree
`7094ab6e84989b218730c52432c70da10261f8ea`.  The reachable paths and their
MIT blob/content identities are recorded in
`crates/sipi-agent-com-direct/SOURCE-MAP-COM-04.md` and the baseline manifest.

The public executable is `sipi-com-direct-public-api`; the library leaf is
`load_config_run_com_write_artifacts_v1`.  It exposes the ordered
`load_config -> run_com -> write_artifacts` sequence, delegates config
materialization and the fixed-tap chain to existing Rust COM modules, and
writes bounded `result.json`, `report.html`, and `diagnostics.json` artifacts.
Strict Touchstone S2P/S4P paths use the same validated
`sipi-com::s21_to_impulse_dc_v1` leaf without S-parameter fitting, finite-band
kernel, or `NotAssessed` fallback. Before any artifact rename or deletion,
output custody rejects equal, ancestor, descendant, symlink, and hardlink-alias
relations to config, pulse, channel, workbook, calibration, and reuse inputs.
The result payload includes the upstream reporting/model semantic surfaces:
source/profile, contiguous cases, channels, metrics, diagnostics, warnings,
provenance, input manifest, and report manifest.  This is not a status-only
wrapper. The public API also reaches the portable mixed-mode/P-N-skew,
FD-to-TD interpolation/IFFT, Apply_EQ (including generated THRU/FEXT/NEXT
channels), FEXT/NEXT residual/noise-PDF integration, COM/VEC/VEO scalar
metrics, and TDILN diagnostics through the canonical JSON `portable` object;
It additionally reaches the portable MMSE KKT/RxFFE candidate searches and
calibration noise/controller payloads, source-equivalent multi-package case
fan-out with channel/calibration identities, and ERL-only dispatch metrics;
calibration consumes parsed package-case pulse/FEXT/NEXT state on each outer
loop evaluation and publishes selected-case pulse/search input digests;
the current sigma_ne is passed into search/equalization candidate evaluation,
with per-sigma FOM evidence rather than a fixed zero-noise callback;
Apply_EQ/mixed-mode generated search inputs are hashed in the semantic payload
and are not replaced by the raw impulse;
MATLAB-engine and proprietary-golden
parity remain explicit external blockers.

The two fresh replays used independent temporary directories and compared the
same ten-scenario fixed corpus (`base`, `fd_to_td`, `mixed_mode`,
`fext_next`, `equalization`, `tdiln`, `search`, `calibration`, `mmse`, and
`rx_ffe_search`), including metric values, waveform
digest/count/source kind, portable branch diagnostics, artifact topology, and
workflow order.  They are unbound observations; no upstream result payloads
are vendored and no numerical parity claim is made.

The branch-complete portable matrix is recorded in
`2026-08-23-com-02-04-branch-coverage-matrix.v1.yaml` with
`portable_missing: []`.  COM-04 reuses COM-01 workbook/CSV/MAT ingestion and
publishes the source-schema `legacy.csv` projection with known metrics and
explicit empty cells for unavailable non-core fields.
Plotting format rendering, MATLAB engine execution, and non-distributable
proprietary golden data remain explicit external blockers.

Evidence:

- `com-04-direct-semantic-replay-run1.v1.json`
- `com-04-direct-semantic-replay-run2.v1.json`
- `com-04-direct-semantic-replay-aggregate.v1.json`
- verifier `tools/verify_com_04_direct_semantic_replay.py`
- mutation tests `tools/test_verify_com_04_direct_semantic_replay.py`
