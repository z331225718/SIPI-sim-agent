# P5-06 Stage 2b DFE checkpoint acceptance

The current `83e9cb6c` product archive was replayed twice against the pinned
Agent-COM R4.80 corpus with MATLAB R2024b and twice with Rust.  Each replay
covers all 13 original workbooks.  The MATLAB harness exports the source
visible `output_args.DFE_taps` and a SHA-256 receipt over its original
little-endian f64 bytes; this avoids treating `jsonencode` display precision
as numeric data.

All 25 applicable DFE checkpoints retain source-native shape and order.
MATLAB repeat is within `1e-12`; Rust repeat is exact; each corresponding
MATLAB/Rust replay is within `1e-9`.  Raw f64 receipts are intentionally an
observation rather than an equality gate: most nontrivial source/Rust values
are numerically equal within tolerance but not byte-identical.

Under the fixed deployment wall-clock policy (MATLAB one computation thread,
Rust 16 Rayon threads), every workbook and the total satisfy Rust-not-slower.
The best MATLAB total is 1613.4832605 seconds and the worst Rust total is
157.375059 seconds, a minimum observed speedup of 10.252471203203806x.

This accepts only the named source-visible DFE checkpoint.  It does not close
P5-06, accept the full intermediate array/result graph, alter the no-fit
S-parameter boundary, or make a release claim.
