# P4A Example Rx Candidate Inventory v1

## Scope

This observer-only preflight reads the pinned external Git object for the
candidate `example_rx.ibs` asset. It records bounded inventory facts needed to
select an IBIS profile later: declared IBIS version, component, model and pin
selectors, corner-bearing sections, table-family names, and declared AMI
executable bindings.

## Boundary

The candidate remains external-only and not required. The inventory does not
copy source bytes, establish a product parser, or turn the asset into a test
fixture. Its implementation material is unavailable to product implementers.

## Rejection Rules

The verifier rejects Git-object or asset-hash drift, a changed candidate
profile state, malformed required metadata, unknown inventory scope, a
promotion flag, or an upgraded DLL binding result. It reports a declared
Windows x64 DLL filename mismatch as a blocker instead of attempting filename
or runtime resolution.

## Non-Claims

No IBIS parser, electrical table behavior, AMI host behavior, runtime loading,
or release capability is accepted by this inventory.
