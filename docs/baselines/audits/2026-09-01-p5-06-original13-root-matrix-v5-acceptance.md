# P5-06 Public Root Matrix v5 Acceptance

The candidate `b456e9d5` was archived independently and exercised through
the deployable root command `sipi com run`, built from
`crates/sipi-cli/Cargo.toml` with `com-direct-integration`.  This is not a
private direct-port replay: each successful Rust record binds the path-free
root receipt and the content/length of `result.json`, `report.html`, and
`diagnostics.json`.

Two fresh Rust replays and two fresh MATLAB R2024b replays cover the original
13 workbooks, ordered THRU/FEXT/NEXT inputs, 28 package cases, and 303 final
scalar slots.  All repeat, cross-engine scalar, no-fit, and per-workbook plus
total performance gates passed.  Rust worst total wall time was 113.0148048
seconds while MATLAB best total was 1568.9991522 seconds, a measured speedup
floor of 13.88311876311187 under the stated deployment process policy.

This is a scalar and performance acceptance only.  It does not accept array or
checkpoint payload parity, warning/full-result coverage beyond the 303 scalar
slots, IEEE conformance, release, or closure of the P5-06 main item.
