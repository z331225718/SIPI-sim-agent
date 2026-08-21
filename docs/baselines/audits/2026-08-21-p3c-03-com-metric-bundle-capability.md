# P3C-03 COM Metric Bundle Capability

## Result

`sipi-compare` now exposes a fixed typed scalar bundle containing exactly
`com_db`, `erl_db`, and `td_iln_db`, all in dB. The compare entrypoint requires
complete finite reference and candidate bundles plus three explicit
`ToleranceV1` values. It delegates comparison to the existing strict
profile-agnostic metric engine and rejects non-finite arithmetic.

The API has no map-shaped input, aliases, default tolerances, alignment, unit
conversion, CLI, or oracle access. In particular, it has no ICN field and does
not reinterpret `ICN_mV` as TD-ILN. The older C4 profile remains unchanged and
distinct.

## Boundary

This is a P5-06 prerequisite capability, not P3C-03 acceptance closure. The
authoritative reference artifact, TD-ILN value, clean input provenance,
checkpoint alignment, and required per-metric acceptance tolerances remain
external blockers. No product-vs-oracle compare or release promotion occurred.
