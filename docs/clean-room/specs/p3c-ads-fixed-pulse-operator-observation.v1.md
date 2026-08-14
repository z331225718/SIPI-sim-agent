# P3C ADS Fixed Pulse Operator Observation v1

## Scope

This external-only diagnostic removes `PRBSsrc` from one selected channel
observation. It compares one fixed ADS sampled channel response with the
current product fixed selected S4P path at exactly the same sample indices.

## Fixed Topology And Input

- The external ADS topology is exactly two ideal PWL voltage sources, two
  explicit 50-ohm source resistors, the exact selected four-port S4P, and two
  50-ohm receiver loads to ground. It contains no PRBS source, AMI, IBIS, DLL,
  CDR, receiver or extra network element.
- The open-circuit differential input rises from zero to `+1 V` with a
  `100 as` edge, holds for one UI, and returns to zero with a `100 as` edge.
  It starts at `511 UI + dt/2`; no strobe lies on either edge.
- ADS is fixed to `ImpMaxFreq=40 GHz`, `ImpDeltaFreq=39.0625 MHz`, `ImpMode=1`,
  normal passivity enforcement, three PRBS-contract periods, OSR32 output and
  its inclusive final point. The final ADS point is discarded.
- The product input is exactly 49,056 samples with 32 `+1 V` entries at
  `[16353,16385)` and zero elsewhere. It enters only the current selected
  sealed S4P, interpolation, 32-iteration bounded causality, `1e-3`
  truncation, and direct full linear convolution path.

## Evidence Boundary

Two fresh ADS work directories and two distinct `ArtifactRoot` manifests are
required. Reports retain only hashes, fixed counts, bit patterns and scalar
RMS/NRMSE facts. Source bytes, pulse waveforms, S4P bytes, paths and arrays
remain external.

This does not choose a product policy, identify ADS output-strobe or
convolution semantics, admit causality/passivity/FIR behavior, accept the
PRBS profile, or alter receiver, P4B, P5 or release gates.
