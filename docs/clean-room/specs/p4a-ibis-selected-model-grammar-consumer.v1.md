# P4A Selected-Model Grammar and Consumer v1

## Scope

This slice closes only a bounded, caller-owned selected-model grammar.  It
does not claim a complete IBIS grammar, an external profile, or electrical
behavior.

Every request must provide all four fields below:

1. one terminal identity, expressed as an explicit `signal` or `pin` role;
2. either one direct model name or one selector name plus its branch model;
3. one corner name and finite voltage/temperature values;
4. one supported table family.

There are no defaults for signal, pin, model, selector branch, corner, PVT,
or table family.  A selector branch is named by its model spelling, never by
position or description.

## Complete-Document Gate

The consumer first invokes the existing typed inventory consumer.  The input
must be bounded ASCII, have one complete semantic envelope, and end with one
payload-free `[End]`.  Caller-owned marker names remain the only allowed
non-model pin references.  The tracked IBIS prefix therefore cannot enter this
consumer because it has no final `[End]`.

## Resolution

The explicit signal or pin role must resolve to exactly one pin row.  A direct
model must equal that row's direct model reference.  A selector target must
equal that row's selector reference and name exactly one declared branch.  A
missing, duplicate, disconnected, or unknown target rejects.

The requested table family must occur exactly once inside the resolved model
block and must contain at least one bounded opaque data row.  The result
returns only model/selector identity, role identity, caller PVT, model type,
and the selected table's family, model, row count, and source span.  Table
values are not interpreted or returned.

## Boundary

The consumer has no corner-column fallback, PVT inference, table-family
fallback, supply/reference inference, interpolation, waveform evaluation,
quasi-static state, transient integration, AMI execution, URL/file route, or
external oracle dependency.  A complete external official object can be
observed through the ignored operator runner, but it remains rejected until an
operator supplies the missing selected profile and separately verifies rights.
