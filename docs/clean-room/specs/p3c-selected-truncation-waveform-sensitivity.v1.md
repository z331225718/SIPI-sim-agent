# P3C Selected Truncation Waveform Sensitivity v1

This external-diagnostic-only leaf consumes exactly the 51,200-sample selected bounded-causality response and evaluates only output indices `[32704, 49056)`. The PRBS9 source is the fixed OSR32, UI-boundary right-continuous projection with zero prehistory. Each output visits kernel indices from zero upward; the frozen work count is 668,477,936 multiply-accumulates.

It has no caller configuration and rejects a different sample interval or kernel length. It does not use FFT, circular convolution, tail selection, delay extraction, alignment, resampling, gain/DC/polarity adjustment, or an ADS source. Its result is not a candidate waveform, CausalFirChannel admission, truncation-policy change, or acceptance result.
