# P5-06w4 Normal ERL MATLAB Trace Checkpoint

## Scope

This record checks the named normal-ERL TDR path for original Agent-COM
workbooks 3, 4, and 5.  Each workbook checks both differential ports and the
four named vectors: `time_s`, `impedance_ohm`, raw `ptdr`, and gated TDR.

## Method

The original `matlab_src/com_ieee8023_480.m` is materialized from the pinned
Agent-COM archive and copied to a temporary, instrumented directory.  The
copy has a read-only trace hook only; its source hash changes from
`88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596` to
`1409a3b6923aa9e2dc8d736f0861123ea7a6602e39c65eeae729467c26928a3c`.
It is not represented as the original source.  An uninstrumented invocation
must retain the same final scalar surface and warning semantics before its
trace may be compared to Rust.

Two fresh R2024b replays show exact f64 little-endian digest and length
identity for all four vectors in all six port/workbook pairs.  The source
arrays in this named profile each contain one sample; this is therefore not a
claim of general finite-ERL array parity.

## Performance

The timing comparison uses the uninstrumented MATLAB invocation, never the
instrumented copy.  Rust is faster for every workbook in both replays.  The
conservative floor is `72.43344098541151x` (best MATLAB versus worst Rust for
workbook 5).  This is a supplemental direct normal-ERL measurement; the
public-root deployment-performance gate remains P5-06w.

## Boundaries

The Rust channel path uses raw FD-to-TD impulse processing and does not fit
S-parameters.  This checkpoint does not claim a public result wire, complete
ERL result-graph parity, a complete warning catalog, IEEE certification,
release readiness, or closure of P5-06.
