# P2 One-Node RC/PWL Transient v1

## Scope

This independently authored specification defines one bounded, typed transient
primitive. It has exactly one caller-owned piecewise-linear voltage source, one
series resistor, and one capacitor to an explicit reference. It accepts no
netlist text, model selection, implicit ground, or topology description.

## Request

A request supplies a finite positive resistance in ohms, a finite positive
capacitance in farads, a finite initial capacitor voltage, a finite strictly
increasing output axis beginning at zero, and matching finite source-knot
times and voltages. The source needs at least two knots, its time axis begins
at zero and is strictly increasing, and its final knot time must exactly equal
the final requested output time. A source is undefined outside this coverage;
the primitive does not hold, extrapolate, or infer a source value.

Between adjacent knots, the source voltage is linearly interpolated. A knot
that coincides with an output time belongs to the endpoint sample at that time.

## Numerical Semantics

The only v1 integrator is f64 backward Euler. Its state is the capacitor
voltage relative to the explicit reference. The integration breakpoints are
the sorted, deduplicated union of requested output times and source-knot times.
For every interval ending at `t_next`, it evaluates the PWL source at `t_next`
and computes:

```text
tau = R * C
vout_next = (vout_previous + (dt / tau) * vin(t_next)) / (1 + dt / tau)
```

The result is reported only at the requested output axis. There is no output
interpolation, resampling, adaptive stepping, windowing, fitting, operating
point solve, or implicit initial-condition calculation.

The caller supplies explicit output-sample and merged-breakpoint limits. The
primitive rejects a request that exceeds either limit. With a `RunContext`, it
checks cooperatively at entry, before integration work, at every merged
breakpoint, and before producing the final waveforms.

## Rejections and Non-Claims

The primitive rejects non-finite values, non-positive R or C, invalid axes,
mismatched source arrays, insufficient knots, incomplete source coverage, and
output or breakpoint limit exceedance. It does not define a SPICE parser,
general PWL syntax, arbitrary circuit topology, general MNA, multiple nodes,
other devices, nonlinear convergence, OP, AC, artifact publication, CLI input,
channel coupling, IBIS/AMI composition, or external-profile acceptance.
