# P5-06w Source Warning Observation

This record freezes a fresh external observation, not a warning-parity
acceptance. The source was materialized from the exact Agent-COM archive
listed in the companion manifest, then the five original-13 workbooks known
to emit a pinned MATLAB-source warning were run under MATLAB R2024b.

All three `COM:read_s4p:MaxFreqTooLow` warnings at source line 9715 match the
existing source-mapped Rust warnings by occurrence and role. Every observed
workbook also emitted the line-6337 anti-causal warning through the normal
TDR route. Its source vector has only 2.27e-17 to 4.55e-17 magnitude, whereas
the Rust vector is zero-magnitude signed-zero data. The unwrapped-phase
predicate therefore differs and cannot honestly be promoted into a MATLAB
warning-equivalent Rust event.

The final COM scalars and root performance remain accepted by P5-06w. This
record deliberately leaves full warning parity, the complete warning catalog,
release, and P5-06 main closure open.
