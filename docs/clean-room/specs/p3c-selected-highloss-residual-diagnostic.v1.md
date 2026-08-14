# P3C Selected High-Loss Residual Diagnostic v1

This selected-profile diagnostic consumes only already validated three-period
finite waveforms. It subtracts `candidate-reference` at the original index and
partitions the result into the fixed three PRBS periods. Its third-period
NRMSE must be bit-identical to the existing v3 waveform-only result.

The diagnostic has no caller options, public CLI, external reader, frequency
transform, or corrected result. It records only finite scalar bit patterns,
canonical digests, and fixed offsets in external evidence. Alignment, lag or
correlation search, phase/fold search, resampling, gain/DC/polarity changes,
and any adjusted acceptance result are forbidden.
