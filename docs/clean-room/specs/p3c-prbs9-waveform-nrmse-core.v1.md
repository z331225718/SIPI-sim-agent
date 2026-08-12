# P3C PRBS9 Waveform NRMSE Core v1

This product-owned core implements only the unambiguous waveform NRMSE portion
of the PRBS9 v2 metric profile. It accepts two finite full three-period
strict-grid waveforms, evaluates only indices `[32704, 49056)`, and uses the
fixed 1% reference-relative NRMSE limit. It performs no alignment,
resampling, gain/DC/polarity transform, source lookup, or external binding.

The profile identity is bound to the v2 contract content hash. Eye and TIE
algorithms are intentionally absent until their remaining discrete boundary
rules are independently frozen. The result is a formula report only, not a
candidate or external-profile acceptance result.
