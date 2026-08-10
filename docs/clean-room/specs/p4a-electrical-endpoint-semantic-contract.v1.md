# P4A Electrical Endpoint Semantic Contract v1

## Selected Topology

The selected electrical-load topology has three terminals: differential `P`,
`N`, and explicit endpoint reference terminal `REF`.

- `Rdiff = 100 ohm` is connected from `P` to `N`. Its passive positive current
  direction is `P` to `N`; `Vpn = V(P) - V(N)`.
- `Cp_ref = 1 pF` is connected from `P` to `REF`.
- `Cn_ref = 1 pF` is connected from `N` to `REF`.

`REF` is a terminal role, not a default spelling for global ground or node
zero. A future profile must bind it explicitly to the channel return/reference
node before any electrical solve or acceptance comparison.

The two per-leg capacitors are not replaced by a P-to-N capacitor or by a
total differential-equivalent capacitance. Such a replacement loses the
declared common-mode boundary.

## Deliberate Limits

This contract does not define an initial state, integration method, channel
return binding, stimulus, timebase, observable, tolerance, or solver. It is
therefore selected but not required-accepted, and product runtime input must
continue to reject it.

## Future Shapes

A P-to-N capacitor is an independent, future component. A single-ended
channel is likewise an independent `SIG`/`REF` terminal grammar. Neither is
derived from this three-terminal differential topology, and neither is
implemented here.

## Non-Claims

No electrical-load solve, channel termination, parser, CLI command, IBIS/AMI
composition, or external-profile parity follows from this semantic contract.
