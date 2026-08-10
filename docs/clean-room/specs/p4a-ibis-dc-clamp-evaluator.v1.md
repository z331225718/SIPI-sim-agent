# P4A IBIS DC Clamp Evaluator v1

## Scope

This product-owned primitive evaluates two caller-provided, signed DC I-V
tables: one ground clamp and one power clamp. It is the mathematical core for
the selected input-static profile, not an IBIS text decoder or a network
solver.

Each table has at least two finite voltage/current knots with strictly
increasing voltage. Current remains signed exactly as supplied. A probe carries
two explicit drives, one for each table; the evaluator never guesses a supply,
reference, polarity, or power-clamp offset.

## Evaluation

For a probe inside a table's inclusive voltage domain, the result is the exact
knot current or the linear interpolation between adjacent knots. A voltage
outside either domain is rejected. There is no extrapolation, clipping,
fitting, interpolation across a missing knot, or current sign conversion.

The response exposes both branch currents, their sum, and an exactly-zero
capacitive contribution. `C_comp` transient behavior is not represented.
Non-finite arithmetic rejects the whole response.

## Deliberate Boundary

The primitive consumes only typed, product-owned values. It does not decode
IBIS text; read files; select a model, PVT corner, package, pin, or terminal;
or use V-T, ramp, AMI, differential, or network semantics. A later strict
profile decoder may create these typed tables, and an external-only comparator
may provide them temporarily for the selected asset.

## Test Boundary

Tests use only project-authored knots. They cover exact and interior lookup,
signed sums, DC capacitor zero, invalid table rejection, out-of-domain
rejection, scaling, and deterministic repetition. No external IBIS asset,
table, model name, or oracle output appears in product tests.
