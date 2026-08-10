# P3A Matched S2P Response Compare

The external-only comparator added by `8b2c125` and corrected through
`564b937` materializes the selected PyBERT Git object, structurally maps its
two-port `Hz S RI R 50.0` table into the product helper's binary spectrum
record, and independently evaluates the frozen Hermitian inverse DFT twice.
The product runner is built from a fresh SIPI Git archive with the locked
dependency graph. Neither product code nor Git history receives the S2P text,
observer array, or product kernel array.

Windows x86_64 execution from `564b93739dce87e72480f327a31f21d1288d8cc1`
passed the required `channel_16ghz_3db` response-kernel gate:

- source: PyBERT `f6ba0311350fc67bd90fa13b8d578312f956d7e7`, blob
  `e10bfb4a43731645984f1f5e24bd3fbf2268dedd`, SHA-256
  `9d4cfeaad7c971fa45454f639b40e08c538855058f326fbdec64298b8933b5ad`
- observer and product: `N=400`, `dt=25 ps`; two fresh observer kernel hashes
  agreed exactly
- product input SHA-256:
  `74eff145b4896b888fcd1d28d53d18300b867430da2be41bade303f2ff37e5e0`
- max absolute error: `9.80e-15 V/V`, below `1e-9 V/V`
- max relative error: `6.08e-9`, below `1e-5`; worst index: `365`
- Cargo lock provenance is the raw `Cargo.lock` Git blob SHA-256
  `c7adbe35f6c4f0d09c4a3afa92785e92d26c1f9e9863ce8291e9676d3c484c57`,
  not an autocrlf-sensitive materialized worktree hash

The runner executable hash is recorded per execution but is not treated as
byte-reproducible evidence: independent temporary archive builds can embed
different source paths. The acceptance result instead binds the source commit,
tree, raw lock object, product-input hash, observer reproducibility, and
comparison metrics.

Verification passed:

- `cargo test -p sipi-channel --all-targets --locked` (12 tests)
- `cargo clippy -p sipi-channel --all-targets --locked -- -D warnings`
- `tools/test_compare_channel_s2p_matched.py` (3 tests)
- `tools/run_all_tests.py` (77/77)
- P0 boundary, clean-room register, release-license preflight, and Rust source
  map verifiers (all valid; release remains provisional/not ready)

OpenCode final audit `msg_d60db6bba039`: **0 P1 / 0 P2**.

## Non-Claims

This accepts only the selected matched-S21 discrete V/V response-kernel scope.
It does not establish public Touchstone ingestion, reflections, multiport or
RFM handling, Link/eye/BER parity, default routing, byte-identical builds, or
release/MIT promotion.
