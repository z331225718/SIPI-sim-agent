# P3C ADS OR to Product Raw-Periodic DTFT Observation v1

This external-only diagnostic reads the user-authorized documented ADS `CMP1_OR`
complex payload. ADS help calls that surface an original spectrum; it does not
fully disclose the causal-stage algorithm. The diagnostic compares the
fixed Hdiff reduction of that surface with a product
`SelectedP3cRawPeriodicResponseV1` before causality, truncation, convolution, or
candidate generation.

The ADS `CMP1_OR` native axis is the only evaluation axis. All sixteen matrix
members must first prove bit-identical, finite, strictly increasing axes. At every
such node the product uses the finite sequence DTFT
`sum(h[n] * exp(-j * 2pi * f * n * dt))` for `n=0..51199`, in ascending order,
with no normalization or transformation of either input.

The observer may retain temporary external payloads only long enough to produce
hash-only identities and aggregate deltas. It must not interpolate, resample,
nearest-bin match, align, remove delay or phase, fit gain or DC, run causality,
truncate, convolve, or generate a waveform. The result cannot identify an ADS
algorithm, a causal-stage position, or explain a waveform mismatch, and raw-periodic output is not a causal
impulse or FIR admission.
