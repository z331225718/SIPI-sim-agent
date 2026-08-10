# P2 RC/PULSE Comparator v1

## Purpose

This observer-side gate compares the fixed, product-owned `tran-rc-pulse-v1`
result against the separately anchored external oracle. It is not a product
input format or a simulation capability.

## Product Export

The feature-gated `sipi-tran-rc-pulse-harness` has no arguments and emits one
JSON object containing only the fixed profile id plus its explicit time,
`v(in)`, and `v(out)` arrays. It has no legacy parser, engine, fixture, or
fallback dependency and is not reachable through `sipi`.

## Comparator Boundary

The comparator materializes the external deck from the contract's immutable
Git object into a new temporary directory for each oracle run. It verifies the
external executable hash and build identity, executes two fresh oracle runs,
and requires their f64le array hashes to match exactly before comparing the
product export.

The report contains only identities, array hashes, comparison metrics, and
scope-limited claims. It does not retain the deck or waveform arrays. It
rejects any grid, finite-value, length, identity, reproducibility, or tolerance
mismatch without changing a golden or widening the contract.

## Non-goals

This is not a netlist parser, `.op` or `.ac` check, general TRAN/Spice parity,
CLI route, release certification, or a claim about any profile other than the
specified four samples of `tran-rc-pulse-v1`.
