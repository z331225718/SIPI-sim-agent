# P3C PRBS9 Candidate Source Projection v2

This pending v2 policy keeps the existing time axis, PRBS order, seed, OSR32,
kernel, direct full linear convolution, and metric window unchanged. For every
global UI after the first, the phase-zero sample uses the prior symbol and
phases 1 through 31 use the current symbol. Sample zero remains the first
symbol with no invented predecessor.

The policy does not accept a caller mode, source amplitude override, sequence
rotation, alignment, interpolation, resampling, fitted gain, DC removal, or
polarity change. The owner must explicitly approve all four pending fields in
the charter before any v2 Rust generator, ADS replay, or candidate compare is
implemented.
