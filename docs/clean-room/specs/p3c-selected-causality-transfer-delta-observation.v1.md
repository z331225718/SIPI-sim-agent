# P3C Selected Causality Transfer-Delta Observation v1

## Scope

This external-only observation isolates the already fixed selected bounded
causality leaf.  It reads the exact sealed selected S4P through the v2 static
admission and selected interpolation, then derives both the raw periodic
response and the bounded causal response from the same uniform spectrum.

## Fixed Observation

- Each run uses a fresh `ArtifactRoot`, a distinct sealed manifest, and the
  fixed selected S4P SHA-256 and byte length.
- Both responses contain 51,200 finite samples at `dt = 9.765625e-13 s`.
- A negative-sign, unnormalized, rectangular forward DFT with factors
  `[32, 32, 2, 25]` is independently applied to each real response.  The
  bounded-minus-raw delta is formed only after those two transforms.
- The report records only domain-separated response/spectrum digests, the
  causality iteration and stop reason, bins 203 and 204, and four fixed bands:
  `[0,1)`, `[1,801)`, `[801,2001)`, and `[2001,25601)`.

## Rejections And Nonclaims

Source drift, seal/admission failure, nonfinite values, unexpected grids,
DFT failure, duplicate manifests, unequal fresh observations, or cleanup
failure reject the observation.  No raw/bounded waveform, S4P bytes, path, or
spectrum array is retained.

This is not an ADS/COM parity result, a causality cause determination,
causal-FIR or passivity admission, parameter sweep, candidate waveform,
reference comparison, acceptance, receiver, or release result.  It does not
apply gain, delay, phase, alignment, resampling, filtering, or policy changes.
