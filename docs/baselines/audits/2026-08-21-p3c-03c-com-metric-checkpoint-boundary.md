# P3C-03c same-checkpoint boundary

The product implementation adds a typed COM/ERL/TD-ILN scalar compare boundary.
Both sides must carry the same non-empty ASCII checkpoint string. A mismatch
is rejected before comparing values. There is no waveform alignment,
interpolation, ICN alias, unit conversion, or oracle lookup.

The three owner policy tolerances are fixed at absolute 0.1 dB with relative
tolerance 0.0. This is a product comparison policy only. It is not an Agent-
COM authority, external acceptance threshold, or release decision.

The implementation path, public export path, exact policy strings, and focused
test behavior are bound in the companion YAML. The compare accepts explicit
finite `COM_dB`, `ERL_dB`, and `TD_ILN_dB` values only. A caller must supply the
checkpoint and metric provenance; the module does not infer them.
