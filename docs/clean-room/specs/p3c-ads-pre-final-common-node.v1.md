# P3C ADS Exact Common-Node Pre-to-Final Observation v1

This additive external observation preserves P3C-04ax's full-axis mismatch.
It proves the mapping independently for every 4x4 member, then compares only
`CMP1_S0[k]` and the unique bit-identical `CMP1_FFT_IMP[4k]`, for
`k=0..1023`.  The authorized ADS dataset API materializes each vector in order
to verify its axis; the observer neither compares nor retains final-only
complex values.  It uses no interpolation, resampling, nearest-bin selection,
tolerance, or product policy.  It records only hash-only full-matrix and
selected Hdiff summaries.  It is not a passivity algorithm or correction-
magnitude claim, and changes no product or release gate.
