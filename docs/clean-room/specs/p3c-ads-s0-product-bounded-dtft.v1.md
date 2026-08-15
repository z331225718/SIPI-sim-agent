# P3C ADS S0 to Product Bounded DTFT Observation v1

This external-only diagnostic compares the documented ADS `CMP1_S0` surface,
reduced through the already fixed four-port Hdiff expression, with a product
`SelectedP3cCausalResponseV1` before truncation or convolution.

For every one of the exact 1,024 ADS S0 frequency nodes, the product result is
the finite sequence DTFT `sum(h[n] * exp(-j * 2pi * f * n * dt))` for
`n=0..51199`, in ascending order. The window is the whole bounded response;
there is no normalization, FFT-bin interpolation, resampling, delay/phase
removal, gain/DC fit, alignment, or candidate generation.

The ADS dataset API may materialize the 16 S0 member vectors to prove their
identical axes and fixed Hdiff reduction. The observer retains only temporary
axis/Hdiff payloads outside the worktree, then records hash-only and aggregate
comparison summaries. This does not establish ADS algorithm equivalence or
identify the cause of the waveform residual.
