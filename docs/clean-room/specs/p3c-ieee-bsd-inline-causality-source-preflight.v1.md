# P3C IEEE BSD Inline Causality Source Preflight v1

## Purpose

This observation records a narrow source fact needed for the next P3C channel
step: the already admitted IEEE BSD `s21_to_impulse_DC.m` object contains its
own Alternating Projections causality loop. That loop calls interpolation and
FFT/IFFT operations but does not call the separately blocked
`calculate_delay_CausalityEnforcement.m` helper.

## Exact Boundary

The only upstream implementation input is the already registered immutable
`src/s21_to_impulse_DC.m` object. `interp_Sparam.m` is an existing admitted
dependency leaf. The blocked named-author helper, Agent-COM, PyBERT, PyAMI,
MATLAB, worksheets, ADS outputs, fixtures, and all external runtime inputs are
excluded. This is a source/dependency observation, not an implementation scope.

## Required Future Decisions

Before any translation, the owner must freeze all three tolerances, a finite
iteration cap, MATLAB-to-Rust indexing endpoints, the relative-error
denominator, and rejection behavior for all-zero input, missing threshold
crossing, non-finite arithmetic, and non-convergence. Truncation, delay, and
passivity remain separate future decisions.

## Non-Claims

No causal impulse, causal FIR, waveform, external oracle binding, receiver,
P5 reference, AMI runtime, or release gate is admitted by this observation.
