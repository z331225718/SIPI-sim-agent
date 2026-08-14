# P3C PRBS9 Candidate Source Projection v2

This owner-confirmed v2 policy keeps the existing time axis, PRBS order, seed, OSR32,
kernel, direct full linear convolution, and metric window unchanged. For every
global UI after the first, the phase-zero sample uses the prior symbol and
phases 1 through 31 use the current symbol. Sample zero remains the first
symbol with no invented predecessor.

The policy does not accept a caller mode, source amplitude override, sequence
rotation, alignment, interpolation, resampling, fitted gain, DC removal, or
polarity change. The owner approved all four fields in the charter. The bounded
Rust generator implements only this fixed projection; a source-only replay and
the full candidate observation remain separate external gates.
