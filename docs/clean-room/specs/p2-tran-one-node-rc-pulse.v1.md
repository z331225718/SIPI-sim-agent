# P2 One-Node RC/PULSE Transient v1

## Scope

This independently authored specification defines one bounded, typed transient
primitive. It has exactly one ideal periodic PULSE source, one series resistor,
and one capacitor to an explicit reference. It accepts no netlist text, model
selection, implicit ground, or topology description.

## Request

A request supplies all of the following explicitly:

- finite low, high, and initial output voltages;
- a finite positive resistance in ohms and a finite positive capacitance in
  farads;
- a finite PULSE delay greater than or equal to zero, positive rise and fall
  durations, non-negative high width, and a positive period;
- pulse corner end `delay + rise + width + fall` no greater than one period; and
- a finite, non-empty, strictly increasing output time axis starting at zero.

The source is continuous and piecewise linear. Each period begins at the low
level, remains low through its delay, rises linearly, remains high through its
width, falls linearly, and remains low for the rest of the period.

## Numerical Semantics

The only v1 integrator is f64 backward Euler. Its state is the capacitor
voltage relative to the explicit reference. For every interval ending at
`t_next`, it evaluates the source at `t_next` and computes:

```text
tau = R * C
vout_next = (vout_previous + (dt / tau) * vin(t_next)) / (1 + dt / tau)
```

The integration breakpoints are the sorted, deduplicated union of requested
output times and all PULSE corners in the requested time range. The result is
reported only at the requested output axis. There is no interpolation,
resampling, adaptive stepping, windowing, fitting, operating-point solve, or
implicit initial-condition calculation.

The caller must give explicit output-sample and integration-breakpoint limits.
The primitive rejects a request that exceeds either limit. With a
`RunContext`, it checks cooperatively at entry, before integration work, at
every PULSE-period expansion, at every breakpoint, and before producing the
final waveforms. Cancellation and deadline observation are cooperative only.

## Fixed Profile Wrapper

`tran-rc-pulse-v1` remains a fixed wrapper over this sole core. It fixes the
four requested times, 1 kohm resistor, 1 microfarad capacitor, zero initial
output, and the existing 0-to-1 V PULSE parameters. Its returned values and
external comparator scope do not expand. The wrapper must preserve its
existing result bits for its defined four samples.

## Rejections and Non-Claims

The primitive rejects non-finite values, non-positive R or C, invalid PULSE
durations or corner order, an invalid output axis, and output or breakpoint
limit exceedance. It does not define a SPICE parser, arbitrary PWL source,
general MNA, multiple nodes, other devices, nonlinear convergence, OP, AC,
artifact publication, CLI input, channel coupling, IBIS/AMI composition, or
external-profile acceptance beyond the unchanged fixed wrapper.
