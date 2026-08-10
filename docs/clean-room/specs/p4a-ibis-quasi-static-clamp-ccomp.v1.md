# P4A IBIS Quasi-Static Clamp Plus C_comp V1

## Scope

This product-owned relation extends the selected typed Input/TYP DC clamp
model with its declared ideal `C_comp`. It is a memoryless I-V clamp relation
plus a continuous capacitor constitutive relation, not a transient solver.

## Inputs And Outputs

The model holds two typed DC I-V tables and a finite, non-negative `C_comp`
in farads. A state supplies three explicit finite values:

- the ground-clamp drive voltage;
- the power-clamp drive voltage; and
- `d(V(SIG)-V(REF))/dt` in volts per second.

The DC drives remain independent. The model does not infer them from a supply,
PVT selection, signal voltage, or reference binding. The clamp currents keep
the selected profile's positive-into-shunt sign. The capacitive current is
`i_c=C_comp*d(V(SIG)-V(REF))/dt` with that same sign, and the total shunt
current is the finite sum of ground, power, and capacitive currents.

The existing DC table evaluator runs first. An out-of-domain table drive
rejects before any capacitive or total response is published.

## Deliberate Limits

There is no time step, previous sample, waveform, retained state, Euler or
trapezoidal integration, FFT, supply derivation, package, pin network, PVT,
V-T, ramp, AMI, file I/O, CLI, or external transient comparison. The accepted
external six-point profile remains DC-only and does not certify this continuous
extension.
