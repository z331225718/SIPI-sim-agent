# P3C ADS Transient Noncausal-Delay Policy Surface v1

This external-only observer binds one installed ADS troubleshooting document, the
fixed-PWL selected-S4P netlist declaration, and the current product bounded
causality contract.  It records only an explicitly documented controller policy
surface: the controller documentation describes introducing a delay to force
causality, names `ImpNoncausalLength` with default 32, and relates its timestep
to the default `ImpMaxFreq` setting.

The observer verifies that the fixed PWL netlist explicitly selects 40 GHz
`ImpMaxFreq`, 39.0625 MHz `ImpDeltaFreq`, discrete convolution mode, and has no
`ImpNoncausalLength` declaration.  It also binds the product contract that
prohibits delay extraction and caller alignment overrides.

It does not run ADS, inspect a dataset or log, infer any delay duration, claim
that the selected run acted on the documented policy, alter a waveform, or port
an ADS algorithm.  Its result is a policy-surface asymmetry only, not causal-FIR
admission, candidate acceptance, or release evidence.
