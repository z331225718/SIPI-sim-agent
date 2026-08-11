# P2 One-Node RC/PULSE CLI Slice

The product-owned `tran one-node-rc-pulse --stdin` route accepts only the
versioned typed one-node RC/PULSE request. It fixes the topology to an ideal
periodic PULSE source, one series resistor, and one capacitor to an explicit
reference. The caller supplies the output axis, R, C, initial output voltage,
and seven PULSE parameters; it cannot supply a netlist, nodes, devices,
integration policy, breakpoint policy, artifact filenames, or a fallback.

The route calls the existing `sipi-tran` one-node numerical core with fixed
bounds of 4096 output samples and 16384 integration breakpoints. It publishes
only a sealed artifact containing canonical request, result, and provenance;
duplicate publication, invalid input, numerical/resource failure, or cancelled
execution produce no success artifact.

This is product-owned bounded one-node RC/PULSE capability only. It has no
external oracle acceptance beyond the unchanged fixed `tran-rc-pulse-v1`
wrapper and does not claim general TRAN, SPICE/netlist parsing, MNA, OP, AC,
multi-node, nonlinear, adaptive-step, channel, IBIS, AMI, COM, or release
support.
