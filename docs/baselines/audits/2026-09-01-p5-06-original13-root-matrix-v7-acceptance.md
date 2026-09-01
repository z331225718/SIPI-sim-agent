# P5-06 Public Root Matrix v7 Acceptance

Candidate `bdc0dfd8` was independently archived and exercised through the
deployable root command `sipi com run`, built from
`crates/sipi-cli/Cargo.toml` with `com-direct-integration`. Each successful
Rust record binds the path-free root receipt and the content and length of
`result.json`, `report.html`, and `diagnostics.json`.

Two fresh Rust replays and two fresh MATLAB R2024b replays cover the original
13 workbooks, ordered THRU/FEXT/NEXT inputs, 28 package cases, and 509 shared,
source-visible scalar slots. All repeat, cross-engine scalar, no-fit, and
per-workbook plus total performance gates passed. Rust worst total wall time
was 89.3625233 seconds while MATLAB best total was 1578.885291 seconds, a
measured speedup floor of 17.66831589680503 under the stated deployment
process policy.

This supersedes v6 only as the current candidate scalar/performance evidence.
It does not accept array or checkpoint payload parity, warning/full-result
coverage beyond the 509 scalar slots, IEEE conformance, release, or closure of
the P5-06 main item.
