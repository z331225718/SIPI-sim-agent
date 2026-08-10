# P3B Receiver Candidate Readiness v1

## Status

This is an oracle-side admission preflight for one candidate receiver profile.
It is not a receiver specification and does not authorize product capability
implementation.

## Candidate Identity

The record binds only the external PyBERT Git object
`channel-rfm-block-2-current-drive-v1`: `block_2.rfm` at the immutable
`f6ba031` source anchor. It records the prior observed current-drive boundary:
locked Windows engine identity, input port 1, output port 2, 1024 samples,
`dt = 1e-12 s`, and the calibrated current-to-voltage sign `-1`.

## Owner Gate

The candidate remains `required_by: null`. A valid preflight must list every
missing receiver decision as `missing_owner_selection`: product causal Link
stimulus, P3A periodic-kernel treatment, CTLE/FFE/DFE definitions, CDR clock
and lock behavior, BER reference/alignment/tolerance, and external reference
environment/fixture scope. The verifier rejects any implicit selection or
claim that these values are implementation-ready.

## Non-Claims

The record neither imports legacy receiver semantics into product code nor
establishes RFM Link parity, causalization, DFE/CDR/BER support, or a default
route. Product receiver types may be introduced only after an owner selects
this candidate (or another one) and a separate independent semantic contract
is accepted.
