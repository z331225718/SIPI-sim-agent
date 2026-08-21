# P5-05g COM parameter ingestion consumer

- Date: 2026-08-21
- Scope: one narrow product consumer for P5-05.
- Status: implemented and self-tested; no external oracle or profile acceptance
  is claimed.

The new `ingest_com_parameters_v1` composition consumes a
`ParameterSurfaceReportV1`, a caller-supplied selected-profile canonical key
list, and already-resolved defaults. It validates that the report describes
the same workbook surface, reads present values through the existing
case-insensitive workbook lookup, converts only to the existing
`ResolvedDefaultV1` categories, and delegates precedence/missing-value policy
to `merge_com_parameters_v1`.

The boundary also rejects case-folded duplicate keys, integers outside the
exact `f64` integer range, inconsistent array dimensions, and arrays above two
dimensions. Scalar, vector, and matrix shapes are retained explicitly rather
than flattening a matrix into a vector.

The result exposes a typed `ComParametersV1` plus a deterministic
`ComParameterConsumptionReportV1` with consumed, workbook-value, defaulted,
and unconsumed key sets. Unconsumed workbook fields remain in both the DTO and
the report. A missing workbook key is eligible for an explicitly supplied
resolved default; a missing default remains a hard error. No canonical key
set, COM profile, MATLAB oracle, or external acceptance is invented here.

Focused validation:

```text
cargo fmt -p sipi-com
cargo test -p sipi-com --lib com_parameter_ingestion_v1 --locked
8 passed
```

The implementation and charter are intended for a later machine gate after
the owner integrates the P5-05g plan/ledger entry.
