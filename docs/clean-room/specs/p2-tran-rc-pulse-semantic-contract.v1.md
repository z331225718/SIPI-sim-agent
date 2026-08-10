# P2 RC Pulse TRAN Semantic Contract v1

## Scope

This independently authored specification defines the first product-owned
transient behavior for a typed RC/PULSE request. It is limited to an ideal
piecewise-linear pulse source, one series resistor, one capacitor to ground,
and the requested output grid `0`, `1 us`, `2 us`, and `3 us`.

## Product Semantics

- The capacitor output starts at exactly `0 V`; no operating-point solve or
  UIC mode exists in this profile.
- The source is `0 V -> 1 V` with delay `1 us`, rise/fall `1 ns`, width
  `10 us`, and period `20 us`. Its segments are continuous and piecewise
  linear.
- The product uses f64 backward Euler. It evaluates the source at each
  substep endpoint and must create substeps at requested output times and all
  pulse corners.
- Outputs are index-aligned only. They contain exactly four finite time,
  input-voltage, and output-voltage values. No interpolation, resampling,
  parser, OP, AC, measurement, or other device behavior is in scope.

## Acceptance Policy

The external oracle comparison checks the time axis pointwise with `1e-15 s`
absolute tolerance. Input voltage uses `1e-9 V + 1e-9 * max(|a|, |b|)`;
output voltage uses `2e-6 V + 5e-4 * max(|a|, |b|)`. Every value must be
finite, lengths must match, and the report must identify max absolute and
relative error and its sample index. A comparison is not accepted until both
fresh oracle reproducibility and independent product results are available.

## Boundary

The external deck and engine are comparator-only Git-object assets. The
product accepts separately authored typed data and never parses, copies,
redistributes, or falls back to the deck or engine.

## Non-Claims

This does not define generic SPICE, netlist compatibility, a general MNA
solver, nonlinear devices, OP/AC, or any profile beyond this RC/PULSE scope.
