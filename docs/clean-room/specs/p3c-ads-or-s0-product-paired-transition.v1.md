# P3C ADS OR/S0 Product Paired Transition Observation v1

This external-only diagnostic uses only the exact 1,024-node `CMP1_S0` axis.
Every ADS `CMP1_OR[4k]` frequency bit must equal `CMP1_S0[k]`; otherwise it
rejects without interpolation, resampling, or nearest-node matching.

At each node, the fixed Hdiff reduction produces ADS original `O` and S0 `S`.
The product raw-periodic `R` and bounded `B` responses use the already frozen
full-length finite DTFT. The observer records hashes and aggregate facts for
`A=S-O`, `P=B-R`, and `E=A-P` only. It calls `A` the documented-surface
transition, not an ADS causality transform or algorithm.

No threshold, fit, correction, waveform generation, alignment, gain, DC,
phase, delay removal, ADS on/off variant, or product policy change is allowed.
The result cannot identify a physical root cause or admit a candidate waveform.
