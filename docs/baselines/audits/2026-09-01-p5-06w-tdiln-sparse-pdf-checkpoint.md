# P5-06w TDILN Sparse-PDF Checkpoint

`b456e9d5` changes only the TDILN PDF backend on this path: it uses the
existing sparse PAM representation instead of scanning zero-probability bins.
The prior original-13 TDILN matrix identified workbook 10 as the slowest Rust
TDILN case, so this checkpoint reran its three package cases from fresh
candidate and upstream archives.

All six named arrays passed the frozen sidecar comparison. `time_s` is exact
f64 little-endian; the largest other array delta is `2.312e-12`, below the
frozen `5e-12 + 1e-9 relative` comparison. The production Rust invocation,
including normal artifacts but excluding diagnostic sidecar I/O, took 19.07 s
against MATLAB source-core 182.32 s: `9.56x` faster.

This is a focused regression and performance checkpoint. It does not replace
the two-replay full original-13 TDILN acceptance, serialize the complete
result graph, or close P5-06.
