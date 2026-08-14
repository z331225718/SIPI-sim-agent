# P3C IEEE BSD Truncation Direct Port v1

This source-specific BSD-3-Clause leaf ports only the final strict
peak-relative truncation in `s21_to_impulse_DC.m`. The owner freezes threshold
`1e-3`. It retains samples `[0,last]`, including leading zeros, and preserves
the original sample interval. It does not extract delay, shift time, normalize,
repair passivity, convolve, or construct a waveform.

The input is bounded to 51,200 finite samples. Empty/all-zero input and any
non-finite calculation reject. The report exposes a finite dropped-L2/total-L2
ratio and a structural zero-tail enum only; neither is an acceptance gate.
Implementation alone does not admit an external input, causal impulse/FIR,
candidate waveform, receiver, reference, or release.
