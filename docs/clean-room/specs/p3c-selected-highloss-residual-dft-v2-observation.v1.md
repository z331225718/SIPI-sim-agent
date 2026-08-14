# P3C Selected High-Loss Residual DFT v2 Observation

This external-only diagnostic consumes the current finite-edge v2 candidate
and the immutable ADS RX reference at their existing strict third-period
indices `[32704,49056)`. It applies an unnormalized forward DFT with negative
exponent to exactly 16,352 real samples. The fixed mixed-radix factorization
is `[32,7,73]`; it is an implementation identity, not a caller option.

The only retained one-sided bins are `k=0..8176`. Parseval mean-square uses
weight one for DC and Nyquist, weight two for all interior bins, and division
by `N^2`. Fixed bands are `k=[0,1)`, `[1,256)`, `[256,639)`, and
`[639,8177)`. A zero reference-band energy or a failure to reproduce the
time-domain NRMSE within `abs <= 1e-24 OR rel <= 1e-10` rejects the run.

The diagnostic has a rectangular window and forbids normalization, padding,
detrending, DC removal, alignment, phase rotation, gain fitting, filtering,
inverse transform, parameter selection, and candidate mutation. It retains
only hashes, finite scalar bit patterns, band summaries, and a lowest-index
maximum residual-energy bin. It does not infer a cause or change an
acceptance, receiver, release, interpolation, causality, or source policy.
