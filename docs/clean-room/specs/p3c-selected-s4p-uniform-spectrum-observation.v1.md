# P3C Selected S4P Uniform-Spectrum Observation v1

## Purpose

This external-only observation runs the exact selected S4P through the already
implemented, fixed IEEE BSD interpolation leaf twice from a clean archive. It
determines only whether that frozen policy admits the real selected input.

## Custody

The external source must match the selected S4P's exact byte length and SHA-256
before, during, and after each materialization. Each run creates a distinct
temporary `ArtifactRoot`, seals exactly `channel.s4p`, and calls the v2 static
admission followed by `interpolate_selected_p3c_hdiff_v1`.

The report retains only source identity, clean archive/source inventory hashes,
two opaque manifest hashes, record count, outcome, and outcome-specific
aggregate identities. It never retains absolute paths, source bytes, spectrum
arrays, or temporary roots.

## Outcome

An admitted run records the fixed grid count, step bits, DC/Nyquist complex bit
patterns, and canonical spectrum digest. A rejected run records exactly the
fail-closed interpolation error enum. The two fresh runs must agree on every
outcome field except their manifests. Neither outcome changes the interpolation
policy or selects a fallback.

## Non-Claims

This is not an IFFT, causal impulse, delay/causality/passivity policy,
truncation, convolution, waveform, ADS parity, receiver, P5 reference, or
release admission. Historical raw quadrature diagnostic and source-drift
records remain unchanged.
