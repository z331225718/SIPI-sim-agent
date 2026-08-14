# P3C External ADS Selected High-Loss Waveform-Only Observation v3

Each run independently materializes the selected S4P chain, reads the immutable
ADS canonical triple payload, extracts only the RX differential column, and
seals fresh v3 reference and candidate waveform artifacts. It then invokes the
separate `compare prbs9-waveform-only` CLI route from the same clean archive.

Two runs require distinct S4P, reference, and candidate artifact manifests.
The selected source and ADS payload identities are checked before and after
each read/materialization. The runner retains only hashes, fixed counts,
NRMSE bit patterns, and acceptance booleans; it retains no paths, source bytes,
waveform samples, eye metrics, TIE metrics, or CLI diagnostic streams.

Both runs must agree on all measurement facts. A finite NRMSE above the fixed
one-percent limit is an observed non-acceptance, not a custody or CLI failure.
No run may align, resample, fit gain, remove DC, flip polarity, or infer an eye
or TIE result. This evidence can bind the exact external reference to the
selected v3 waveform input only. It cannot accept a receiver, causal FIR,
passivity, ADS edge-shape parity, statistical eye, P4B/P5, or release.
