# P2 One-Node RC/PWL CLI Slice

The product-owned `tran one-node-rc-pwl --stdin` route accepts exactly one
versioned, bounded topology: a caller-owned piecewise-linear voltage source,
one series resistor, and one capacitor to an explicit reference. The caller
supplies an output axis, a source-knot axis and values, R, C, and an explicit
initial output voltage. It cannot provide netlist text, nodes, devices,
integration options, breakpoint options, artifact filenames, paths, URLs, or a
fallback.

Both axes start at zero and are strictly increasing. The final source knot
must equal the final output time; the route never holds or extrapolates a
source beyond its supplied coverage. Between knots the source is linear. The
solver merges output times with source knots, samples the source at each
backward-Euler step endpoint, and uses fixed bounds of 4096 output samples and
16384 merged breakpoints.

The route publishes only a sealed artifact containing canonical request,
result, and provenance. Invalid input, numerical or resource rejection,
cancellation, and duplicate publication produce no success artifact.

This is a specified, product-owned bounded RC/PWL capability. It has no
external oracle acceptance and does not claim generic TRAN, netlist parsing,
SPICE parity, MNA, multi-node or nonlinear support, adaptive integration,
IBIS/channel/AMI/COM composition, or release readiness. The independently
accepted fixed RC/PULSE profile remains separate and requires fresh external
evidence after product-source changes.
