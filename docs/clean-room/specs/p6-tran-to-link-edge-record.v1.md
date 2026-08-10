# P6 Fixed TRAN-to-Link Edge Record Specification v1

## Scope

This specification defines the identity record for the sole admitted P6 edge:
fixed RC/PULSE `voltage_in` to a causal-FIR DirectLaunch Link stimulus. It is a
specialized in-process record, not a generic edge schema, artifact manifest,
or full provenance model.

The record identifies `sipi.edge.tran-rc-pulse-to-causal-fir.v1`, the fixed
producer profile/output port, `sipi.link-plan.v1` consumer/input port,
single-ended voltage to a common reference, and the P6-03a implementation
revision. It records four SHA-256 identities: producer launch, consumer
launch input, causal-FIR consumer policy, and received Link waveform.

## Canonical Identity

Waveform identities use a domain-separated binary encoding of the unit tags,
uniform time-axis representation, f64 `to_bits()` values for start and step,
sample count, and ordered voltage `to_bits()` values. Thus `-0.0` remains
distinct from `0.0`; NaN and infinity are rejected by the existing typed
boundary before hashing. The fixed producer's explicit axis is admitted only
when it exactly represents `t0=0`, `dt=1 us`, and four samples, then encoded
as that uniform logical axis. Therefore producer and consumer-input hashes
must be equal for a valid edge.

The policy identity separately binds DirectLaunch, causal FIR, bypass CTLE,
bypass FFE, FIR interval and coefficients, and execution limits. The received
identity binds its exact uniform axis and all output samples. A verifier
recomputes every field from typed producer, consumer, and output values.

## Non-Claims

This does not create a generic edge framework, JSON wire record, project
executor, published artifact, full binary/Git provenance, retry/cache policy,
or external asset binding. It does not connect S2P/RFM/IBIS/AMI/COM or certify
any cross-domain numerical result.
