# P6 Fixed TRAN-to-Link Edge Specification v1

## Scope

This specification defines the sole executable cross-domain edge admitted in
P6 v1: `tran-rc-pulse-v1` source `voltage_in` to a causal-FIR Link
`DirectLaunch` stimulus. It is an in-process library composition only.

The producer is exactly the existing fixed RC/PULSE transient result. The edge
selects its source-voltage waveform, never the RC output waveform. The
producer axis must be exactly four explicit samples at `0 s`, `1 us`, `2 us`,
and `3 us`; the samples are copied as voltage values without interpolation,
resampling, padding, trimming, delay, phase, sign, or unit conversion.

The consumer is exactly an existing `LinkPlanV1` with `DirectLaunch`, one
caller-provided causal FIR, and CTLE/FFE bypass. The FIR sample interval must
be exactly `1 us`. Its existing execution limits and deterministic linear
convolution remain the only consumer numerical implementation.

## Validation

The producer axis and waveform length are checked before a launch artifact is
created. Any different axis, count, or consumer sample interval is rejected.
The artifact contract identifier is `sipi.tran.rc-pulse-launch.v1`.

The composition calls the existing fixed TRAN solver, the one admission
function, `LinkPlanV1` constructor, and existing causal-FIR convolution in
that order. It creates no files or artifacts and has no project executor,
worker, runtime policy, cache, retry, or CLI route.

## Non-Claims

This does not implement a general TRAN-to-Channel interface, continuous pulse
preservation, a Touchstone/S2P or periodic-kernel handoff, termination,
reflection, RFM, IBIS, AMI, COM, receiver/equalizer processing, project
execution, artifact provenance, external-profile parity, or certification.
