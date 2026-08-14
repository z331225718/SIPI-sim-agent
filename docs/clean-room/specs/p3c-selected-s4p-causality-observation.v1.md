# P3C Selected S4P Causality Observation v1

## Purpose

This external-only runner observes the exact selected S4P through sealed v2
admission, the fixed IEEE BSD interpolation leaf, and bounded inline causality
enforcement twice from one clean archive. It establishes only repeatable
invocation and its admitted or rejected result for that exact chain.

## Custody

Each run creates a different temporary `ArtifactRoot`, stages exactly
`channel.s4p`, and checks source identity before, during, and after staging.
The external report is hash-only. It retains no path, S4P byte, spectrum, raw
periodic sample, causal-response sample, or temporary root. An admitted report
records only count, interval/error bit patterns, stop enum, canonical response
digest, source/inventory identity, distinct manifests, and cleanup status.

## Boundaries

This is not causal-impulse admission. It does not implement or admit delay,
passivity, truncation, convolution, a candidate waveform, ADS/COM parity,
receiver behavior, P5 reference, AMI/IBIS/DLL execution, metric acceptance, or
release capability. A rejected causality result is evidence, not permission to
relax the frozen direct-port policy.
