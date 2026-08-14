# P3C Selected S4P Raw-Periodic Observation v1

## Purpose

This external-only observation runs the exact selected S4P through the frozen
sealed v2 admission, IEEE BSD interpolation, and raw-periodic inverse-transform
leaves twice from a clean archive. It determines only whether that fixed chain
admits the real selected input and is repeatable.

## Custody And Report

Each fresh run creates a distinct temporary `ArtifactRoot`, seals exactly
`channel.s4p`, and verifies source identity before, during, and after staging.
The retained report is hash-only: source identity, clean archive/inventory,
two manifest hashes, record count, status, and raw-periodic summary fields.
It never retains paths, source bytes, uniform-spectrum values, raw samples, or
temporary roots.

An admitted summary records uniform bin count, raw sample count, frequency and
sample-interval bit patterns, endpoint/inverse residual bit patterns, and a
canonical raw-response digest. It separately records the selected uniform
spectrum digest and the exact residual-bound bit patterns used by the leaf, so
admission margins are auditable without retaining samples. A rejected summary
records only the fixed stage and error enum. The two runs must agree except for
their manifests.

## Non-Claims

This is not causality, delay, passivity, truncation, convolution, waveform,
ADS/COM parity, receiver, P5 reference, candidate metric, or release evidence.
The raw output remains a full periodic response and cannot enter a causal FIR or
candidate route. Historical exact-grid diagnostic and source-drift records stay
unchanged.
