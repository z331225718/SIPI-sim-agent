# P4A Selected DC Clamp Decoder V1

## Scope

This product-owned decoder converts an already parsed in-memory IBIS semantic
document into the narrow DC input-clamp model selected by a caller. It has no
file, URL, asset, runtime, package, pin, PVT fallback, V-T, ramp, AMI, or
network behavior.

## Selection

The caller supplies one lexical IBIS version token, one model selector, and
the only supported corner: `Typical`. The decoder requires exactly one
matching `[Model]` declaration. The selected model must contain exactly one
`Model_type Input` record, exactly one `C_comp` declaration, exactly one
`[GND_clamp]` table, and exactly one `[POWER_clamp]` table. An
`[Algorithmic Model]` record within the selected model is rejected.

## Decoded Values

`C_comp` is a finite, non-negative capacitance declaration in farads. It is
metadata only: the DC evaluator contributes exactly zero capacitor current.
Each clamp row consumes its first two columns only: voltage and Typical
current. Voltage and current must be finite and use an accepted SI suffix.
Extra columns are unconsumed and cannot affect the decoded model. Each table
must contain at least two rows with strictly increasing voltage.

## Rejections

The decoder rejects a mismatched version, missing or ambiguous model,
non-Input model type, missing/duplicate/invalid `C_comp`, duplicate or
missing clamp sections, invalid rows, invalid table ordering, and an
Algorithmic Model attachment. It never substitutes Min/Max, extrapolates,
normalizes, changes current sign, or infers terminals or a supply.

## External Exchange Protocol

An observer may materialize an authorized external asset outside the product
tree, parse and decode it, and pass temporary typed data to the DC evaluator.
The observer must bind the exact asset identity, selected model identity, and
profile charter before doing so. A separate observer-only raw-table evaluator
is required for external comparison. No external text, table, waveform, or
typed request becomes a tracked product fixture or release asset.

Actual two-fresh-custody external comparison is outside this decoder slice.
