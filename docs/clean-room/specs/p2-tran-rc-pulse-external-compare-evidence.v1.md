# P2 RC/PULSE External Comparison Evidence v1

## Purpose

This record reconciles a fixed TRAN acceptance policy with an externally run,
hash-only comparison report. It is evidence metadata, not a simulation input,
oracle fixture, product artifact, or release approval.

## Inputs and Binding

The evidence must bind exactly one accepted `sipi.tran.rc-pulse.compare.v1`
report in external operator custody. It records only the report hash, the
acceptance-contract hash, the fixed external Git-object identity, oracle and
product executable hashes, all Rust crate and lockfile build-input identities,
f64-le array hashes, and aggregate comparison metrics.

Recorded tolerances must exactly match the acceptance contract. The external
report also records the allowed bound at the worst-error sample; an accepted
evidence record is rejected if its maximum absolute error exceeds that bound.

The verifier recomputes the current `crates/sipi-tran` tree identity and rejects
source drift. When given the external report path, it also recomputes its hash
and checks all report identities, two oracle replay hashes, product sample
hashes, and metrics. The report, fixture, executable, and waveform arrays are
never copied into this repository.

Without a supplied external report, the verifier checks only the tracked
hash-only record and current product build inputs. That mode is an integrity
check for the attestation, not proof that an operator still holds the report;
custody is separately audited.

## Claims and Limits

An accepted record applies only to the fixed four-point RC/PULSE profile's
indexed time, `v(in)`, and `v(out)` observables. It does not establish general
TRAN, netlist compatibility, OP, AC, broader simulator parity, legal clearance,
or release readiness.
