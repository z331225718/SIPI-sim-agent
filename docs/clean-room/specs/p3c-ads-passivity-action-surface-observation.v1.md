# P3C ADS Passivity Action-Surface Observation v1

## Scope

This external-only observation uses the fixed P3C-04au off-grid one-UI pulse
bench without changing its electrical topology or numerical controller policy.
It adds only ADS `ImpSaveSpectrum=yes`, the documented output request for
discrete-mode convolution spectrum surfaces.

The authoritative ADS 2026 Update1 transient help surface states that this
request saves the final impulse response, its FFT and original spectrum.  It
also states that `CMP1_S0` exists only when passivity is enforced and denotes
the spectrum after causality but before passivity correction.

## Fixed Observation

- The exact selected S4P identity, PWL pulse topology, `ImpMaxFreq=40 GHz`,
  `ImpDeltaFreq=39.0625 MHz`, `ImpMode=1`, and
  `ImpEnforcePassivity=yes` remain unchanged from P3C-04au.
- The sole added netlist token is `ImpSaveSpectrum=yes`.
- Structured dataset vector-set identities are exact: four `CMP1_*` surfaces
  for every member of the 4x4 S-parameter matrix, plus the transient output.
  Exactly sixteen `CMP1_S0` surfaces are required.
- The two-run report retains only source/help/netlist/runner hashes, counts,
  and the canonical vector-set identity hash.  It retains neither spectra,
  waveforms, S4P bytes, paths nor free-text logs.

## Boundary

Presence of the documented pre-correction surface proves that the passivity
action surface is observable for this selected run.  It does not quantify a
correction, prove that a correction was nonzero, identify the waveform
mismatch cause, authorize a product passivity repair, or change candidate,
receiver, P4B, P5 or release status.
