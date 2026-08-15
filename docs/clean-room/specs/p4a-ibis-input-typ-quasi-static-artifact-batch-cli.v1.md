# P4A Sealed Input/TYP Quasi-static Artifact Batch CLI v1

## Scope

`sipi ibis quasi-static-evaluate-artifact-batch --stdin --artifact-root <root>`
consumes one exact sealed `model.ibs` artifact and evaluates a non-empty,
ordered list of at most 1024 independent Input/Typical quasi-static probes.
The request binds only the artifact ID, manifest SHA-256, explicit model
selection, and each probe's two clamp drives and `SIG-REF` slope.

The exact artifact is consumed once, and the selected model is parsed and
decoded once before every probe is evaluated independently in request order.
The response contains only verified artifact identity and bounded current
records; it never returns IBIS source bytes or tables.

## Required Behavior

- The artifact has exactly one regular payload named `model.ibs`, at most 1 MiB.
- The sealed manifest is at most 64 KiB and must match the request identity.
- The artifact root is an explicit CLI option, never request data.
- The batch is non-empty, has at most 1024 finite probes, and is all-or-nothing.
- Each probe uses existing in-domain clamp interpolation and
  `C_comp * d(SIG-REF)/dt` evaluation without sharing state with other probes.
- Any custody, UTF-8, parse, selection, probe, slope, or evaluator error
  rejects without a partial response.

## Exclusions

This route has no time axis, trace, waveform history, interpolation between
probes, integration, inferred slope, state evolution, or terminal-network
solve. It keeps the existing app-owned no-hostile-concurrent-writer artifact
root assumption. It is caller asset identity verification only, not external
profile acceptance, transient parity, general IBIS support, package/pin/PVT,
V-T/ramp, channel, or AMI behavior.
