# P4A Dynamic Endpoint Transient Composition Contract v1

## Purpose

This is the single semantic boundary for a future composition of the selected
IBIS Input/Typical clamp and the selected three-terminal R-C load. It records
what the existing product contracts already determine and keeps every
composition decision that is not uniquely determined explicitly blocked.

This document is a contract/admission record only. It does not add a Rust
solver, a wire request, a CLI route, an artifact route, or a runtime.

## Existing Decisions That Carry Forward

- The electrical-load terminals are `P`, `N`, and explicit `REF`. `REF` is a
  terminal role, never an implicit global ground or node zero.
- The selected load is a 100 ohm `P-N` resistor and separate 1 pF `P-REF` and
  `N-REF` capacitors. The selected topology is not replaced by a single
  differential capacitor.
- The selected pure-IBIS model is Input/Typical. Its ground and power clamp
  drives are independent explicit voltages, use in-domain linear interpolation,
  and reject out-of-domain probes. No supply or PVT value is inferred.
- The existing constitutive extension defines
  `i_c = C_comp * d(V(SIG)-V(REF))/dt`, with positive current into the `SIG`
  shunt. At zero slope its capacitive contribution is zero. This is a
  memoryless relation and is not a transient integrator.
- P2 one-node RC/PULSE and RC/PWL use f64 backward Euler, a fixed union of
  source corners and requested output times, explicit initial state, and
  requested-axis-only output. Those are P2 profile decisions, not implicit
  P4A composition decisions.

## Blocked Decisions

The following remain owner decisions because the repository does not select
one unique P4A composition policy:

1. `REF` to a channel return and the mapping between IBIS `SIG/REF` and the
   `P/N/REF` load.
2. Supply source and power-clamp supply binding. A model corner, PVT value,
   signal value, or global default cannot fill this gap.
3. Initial state for every retained capacitor state, including whether an
   operating-point or UIC-like mode exists. P2's zero initial output is not
   inherited.
4. Integration method, internal stepping, timebase, and requested output grid.
   The P2 method and limits are references only until explicitly adopted.
5. Channel return and stimulus source, waveform ownership, and the relation
   between a waveform and the explicit continuous derivative consumed by the
   existing constitutive cores.
6. Numeric resource bounds for output samples, source points, integration
   breakpoints, table knots, and work. Existing P2 and IBIS batch limits are
   not composition limits.
7. Dynamic acceptance tolerances for time, voltage, current, alignment, and
   any state/trace observable. Existing P2 and static-DC tolerances do not
   transfer to this profile.

Until all seven decisions are confirmed and evidence is supplied, T12
admission is false. Missing, pending, non-finite, out-of-domain, overflowing,
or otherwise unsupported inputs reject before any partial dynamic result is
published.

## Deliberate Boundary

Quasi-static evaluation and quasi-static artifact batches remain memoryless,
independent-probe operations. They must not be labeled or counted as
transient composition evidence. No general netlist/SPICE semantics, external
parity, release promotion, IBIS/AMI runtime, channel resolver, or implicit
fallback follows from this contract.

The machine-readable baseline and fail-closed verifier are the authoritative
admission record for this slice.
