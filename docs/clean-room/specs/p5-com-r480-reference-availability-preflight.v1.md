# P5 COM R480 Reference Availability Preflight v1

## Purpose

This observer-only preflight records whether the user-selected R480 comparison
obligation has the external inputs required to generate an authoritative
reference. It deliberately does not create a `sipi-com` crate or any product
COM request, default, algorithm, or command.

## Boundary

The only external source object verified here is the already selected R480
envelope identity. MATLAB source, workbooks, fixtures, legacy parameters, and
any oracle output remain external quarantine. This preflight neither reads nor
executes those materials. A future observer may use them only under a separate
external-custody authorization and must produce a hash-addressed reference
bundle outside this repository.

## Fail-Closed Result

`reference_generation_blocked` is the only valid result while an authorized
oracle runner and toolchain, exact normalized input, parameter/default record,
reference metric bundle, and tolerance/alignment policy have not all been
independently established. A missing observation is not a negative claim about
the external source. It merely prevents a compare run and prevents product API
or numerical implementation from being claimed as R480 acceptance work.

## Non-Claims

This preflight does not define COM semantics, copy MATLAB behavior, grant
redistribution rights, authorize a runtime dependency, create a golden result,
or establish parity.
