# P3C IEEE BSD Inline Causality Direct Port v1

## Purpose

This is a source-specific BSD-3-Clause direct port of the inline Alternating
Projections loop in the already admitted IEEE `s21_to_impulse_DC.m` object.
It consumes only the fixed P3C uniform spectrum and produces a bounded
causal-response candidate. It is not a general causality service.

## Frozen Policy

The owner selected `ENFORCE_CAUSALITY=true`, pulse/relative/difference
tolerances `0.05`/`0.006`/`1e-4`, and a 256 iteration cap. The first-half
threshold is strict. In Rust zero-based indexing, each iteration clears
`[0,start]` and `[floor(L/2)-1,L)`. The suffix preserves the IEEE source's
one-based `floor(L/2):end` endpoint, including its overlap with the first-half
window. The relative error divides by the signed
maximum of the zero-window response; a non-positive or non-finite denominator
rejects. On either source stop condition, the output is the pre-projection
zero-window response. All listed failure conditions reject with no partial
output.

## Source And Exclusions

Only `s21_to_impulse_DC.m` lines 66--88 plus its enabled branch at 92--94 are
implemented. Its `interp_Sparam` dependency is already separately admitted.
The named-author delay helper remains excluded. The source all-zero epsilon
substitution, delay, truncation, passivity repair, pulse construction,
convolution, external artifacts, and command surface are out of scope.

## Non-Claims

Implementation alone does not admit an external selected input, a causal FIR,
candidate waveform, ADS/COM parity, receiver, P5 reference, AMI, or release.
