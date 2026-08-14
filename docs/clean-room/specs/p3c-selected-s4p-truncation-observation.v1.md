# P3C Selected S4P Truncation Observation v1

This external-only runner invokes the exact selected S4P chain twice: sealed
v2 admission, fixed IEEE BSD interpolation, bounded causality, then the fixed
`1e-3` truncation leaf. Each run has a separate temporary `ArtifactRoot` and
source identity checks before, during, and after staging. Its report is
hash-only: identity, counts, diagnostics, canonical truncated response digest,
and cleanup status only. No asset path/byte, spectrum, causal response or
truncated sample enters the repository.

It does not admit a causal impulse/FIR, delay, passivity, convolution,
candidate waveform, reference, receiver, or release capability.
