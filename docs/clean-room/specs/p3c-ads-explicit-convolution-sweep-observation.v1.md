# P3C ADS Explicit Convolution Sweep Observation v1

## Purpose

This external-only observation replaces an opaque ADS adaptive impulse decision
with a finite sweep of explicit `ImpMaxFreq` and `ImpDeltaFreq` candidates.  It
does not select a product time-domain executor.

## Fixed external bench

- The selected four-port S-parameter file is identity-bound by its logical
  name, length, SHA-256, and existing P3C port map.
- The benchmark is the existing external ADS PRBS9 ideal-load oracle: 100 as
  source edges, two 50-ohm sources, two 50-ohm receiver loads, `ImpMode=1`,
  `ImpApprox=no`, normal passivity enabled, no AMI/IBIS/DLL/CDR/equalizer.
- `ImpMaxFreq` is fixed at the observed S4P upper bound of 40 GHz.  Each
  candidate explicitly sets `ImpDeltaFreq = 2*fmax/N` for an allowlisted even
  impulse-grid length `N`.

## Result boundary

Candidates are compared to the already observed adaptive ADS waveform using
third-period strict-index differential-voltage NRMSE only.  The frozen 1% gate
is a screening condition, not a product acceptance result.  The selected
explicit ADS candidate is evidence that one explicit ADS controller setting
reproduces that oracle; it does not reveal or reimplement the proprietary ADS
convolution, interpolation, causality, passivity-correction, or output-strobe
algorithms.

## Non-claims

No product waveform, parser/executor, candidate/reference binding, accepted
receiver, P4B runtime, or release claim follows from this observation.  A
product policy remains blocked until its input construction and strobe mapping
are independently specified and implemented.
