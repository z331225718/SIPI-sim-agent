# COM-02 direct semantic replay audit

Status: scoped open.  This audit covers the fixed Agent-COM commit
`5272ffe74702cd585054d975559b06f8afae7b6e` / tree
`7094ab6e84989b218730c52432c70da10261f8ea`.  The reachable paths and their
MIT blob/content identities are recorded in
`crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md` and the baseline manifest.

The executable leaf is `sipi-com-direct-run`; the library leaf is
`run_com_v1`.  It loads a canonical parameter document (or the existing
source-schema materializer), consumes a bounded f64/JSON impulse, or parses
the strict `Hz S RI R 50.0` two-port subset and resolves S21 to a time-domain
impulse.  No S-parameter fitting is performed.  Frequency-domain JSON and
strict Touchstone S2P routes use the same validated
`sipi-com::s21_to_impulse_dc_v1` interpolation/IFFT path, including causality
and truncation metadata; no finite-band kernel or `NotAssessed` fallback is
used.
The Rust COM scalar chain is the existing `sipi-com::execute_com_run_v1`
path, with optional Apply_EQ (including multi-channel THRU/FEXT/NEXT outputs),
FEXT/NEXT residual/noise-PDF integration, and TDILN report diagnostics
reachable through the canonical JSON `portable` object.

The two fresh semantic replays each exercised the same ten-scenario fixed
corpus (`base`, `fd_to_td`, `mixed_mode`, `fext_next`, `equalization`,
`tdiln`, `search`, `calibration`, `mmse`, and `rx_ffe_search`) in
independent temporary directories.  Both produced the same semantic payload:
scenario identity, contiguous case index, channel identity, COM/VEC/VEO/noise
metrics, impulse count/digest/source kind, portable branch diagnostics, and
report topology.  The committed reports intentionally contain no full result
or waveform payloads and are unbound observations, not upstream numerical
parity evidence.

The branch-complete portable matrix is recorded in
`2026-08-23-com-02-04-branch-coverage-matrix.v1.yaml` with
`portable_missing: []`.  In addition to the ten replay scenarios, the Rust
leaf now exposes semantic MMSE KKT/search, FV-LMS/fixed-force RxFFE search,
calibration-noise transfer plus fresh per-sigma package-case COM evaluation and
the bounded outer loop, full-evaluator-only FV-LMS/RxFFE legality, composable
Apply_EQ/search channel selection, COM-01 workbook/CSV/MAT
ingestion reuse, source-schema legacy CSV projection, bounded multi-package
case fan-out, and ERL-only dispatch.  Each emits taps, waveforms, per-iteration
case COM, channel/calibration identity, or artifact payloads rather than
status-only diagnostics.  Calibration derives pulse/FEXT/NEXT from parsed
`package_case` channel state and re-runs the same channel-producing
orchestration for every sigma; selected per-case pulse and crosstalk digests
are published in `selected_case_orchestration`, while
`per_sigma_search_orchestration` records the sigma-specific search/FOM inputs.
The calibrated `sigma_ne` now flows through the same search/equalizer evaluator
callback instead of a fixed zero-noise callback; focused tests assert distinct
sigma scores.  Search publishes `search_input_sha256`; a focused replay asserts
that the digest changes when Apply_EQ generates a different channel.  Plotting format rendering, MATLAB engine execution, and
non-distributable proprietary golden data remain explicit external blockers;
no numerical upstream parity claim is made.

Evidence:

- `com-02-direct-semantic-replay-run1.v1.json`
- `com-02-direct-semantic-replay-run2.v1.json`
- `com-02-direct-semantic-replay-aggregate.v1.json`
- verifier `tools/verify_com_02_direct_semantic_replay.py`
- mutation tests `tools/test_verify_com_02_direct_semantic_replay.py`
