# P3C-03 Current Compare Semantics Boundary

## Result

The product C4 profile and its profile-agnostic compare engine are useful
bounded components, but they do not close the required COM compare contract.
The current C4 surface is `COM_dB / ICN_mV / ERL` with a caller-supplied finite
reference and 1% relative tolerance. The pinned required-contract audit
requires `COM_dB / ERL / TD_ILN`; it explicitly records that `ICN_mV` cannot
substitute for `TD_ILN`.

The compare engine now rejects both missing and unknown candidate metric names,
so a report cannot appear complete while carrying an unprofiled value. This is
a local structural hardening only. It does not choose the required metric
values, source/input provenance, checkpoint alignment, tolerance policy, or
authoritative reference artifact.

## Exact blocker

P3C-03 remains blocked until a fresh current compare binds the required
COM/ERL/TD-ILN values, clean input and checkpoint identity, alignment semantics,
and independently fixed acceptance tolerances. Historical source-drift
records remain historical and are not reused. No MATLAB or external runtime
was invoked for this record.

## Non-claims

This record is not TD-ILN implementation, COM parity, product-vs-oracle
acceptance, or release evidence.
