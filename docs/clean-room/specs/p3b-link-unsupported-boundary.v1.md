# P3B Link Unsupported Boundary v1

The executable `sipi.link.causal-fir-request.v1` accepts only direct launch, a
causal FIR channel, and explicitly selected CTLE and FFE bypass stages. It
does not infer defaults for absent or unknown stages.

Seeded stimuli, PRBS generation, noise injection, jitter or time warping, DFE,
CDR, and BER are rejected at the wire boundary. This document defines no random
distribution, seed format, interpolation, clock model, or receiver behavior.
Those semantics require a required profile and owner-approved independent
specification before a future version may add them.

The current fixed receiver is a library-only, profile-scoped implementation.
Its required external RFM profile is blocked by the approved unique-phase CDR
rule, so it is not a Link CLI stage or a general receiver capability.
