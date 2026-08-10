# P4A IBIS Input Typical Static Profile v1

## Decision

The first required pure-IBIS profile is a single-ended input-model clamp
comparison. The external observer identifies the selected model only through
the SHA-256 digest in the associated acceptance record. The product never
reads the external asset.

The terminal roles are `SIG` and `REF`. `REF` is explicit; no global-ground
or node-zero default exists. The selected corner is the table's `typical`
column. This profile evaluates the supplied static `SIG-REF` voltages in their
declared order.

## Electrical Result

At DC, the observable is the signed shunt current into `SIG` from the sum of
the ground-clamp and power-clamp currents. `C_comp` contributes zero at DC.
Every table lookup uses piecewise-linear interpolation between adjacent source
voltage knots. A probe outside either required table domain is rejected; no
extrapolation, fitting, or silently clamped input is allowed.

The external observer and product result must have equal probe count and order.
Each finite current uses the acceptance record's absolute-plus-relative
tolerance. The report must name the worst probe and both error measures.

## Deliberate Boundary

This profile does not select a pin or package route, nor any V-T or ramp
behavior. Those features require a separately selected output or I/O profile
and must not be inferred from this input-only static comparison. No external
IBIS text, numeric table, model name, or oracle output belongs in product
source or product tests.
