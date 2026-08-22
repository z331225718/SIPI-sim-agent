# COM-01 Immutable Config Leaf Replay Audit

This additive audit binds the COM-01 configuration-validation leaf prepared in
candidate commit `8bcfd1d1bc511461615f19338e453f0148e5dcb1`. It does not update the
shared migration plan or ledger and does not close COM-01.

## Immutable custody

Each formal invocation independently materialized the candidate and pinned
Agent-COM source from Git archives into new temporary directories. The Rust
binary was rebuilt with an independent Cargo target directory. The corpus and
semantic comparison runner came from the candidate archive; the primary XLSX
fixture and Python oracle came from the upstream archive. No candidate or
upstream working-tree source was executed.

The direct crate's XLSX/MAT pre-allocation admission remains part of the
candidate commit. Evidence contains fixture hashes, counts, exit/error
categories, projection hashes, bounded difference-key lists, and consumption
counts only. It does not contain materialized parameter or option values.

## Outcome

Both independent invocations produced the same 14-scenario semantic summary:

- 6 success artifacts matched;
- 7 rejected scenarios matched in both exit code and error category;
- 1 materialized JSON scenario had equal value projection and an empty
  difference-key list, but retained the known Python/Rust fingerprint drift.

The aggregate therefore remains
`open_differential_mismatch_fingerprint_only`. It is not a complete COM parity,
migration-row close, product-capability promotion, or release-readiness claim.

The two Windows release binaries had different complete PE hashes despite the
same immutable source, toolchain identity, build policy, and semantic outputs.
Both binary hashes are retained and bound independently; the aggregate makes no
bit-reproducible binary claim.

## Covered leaf

The pinned corpus covers the default r480 XLSX JSON/text/materialized outputs,
experimental-corrected and custom reader selections, config-default fix and
override handling, duplicate-package warning behavior, mutually exclusive
output modes, invalid profile/reader/fix/override branches, unsupported input,
and missing input. The package-warning CSV is deterministically derived inside
each temporary run from the archived primary workbook.

The corpus does not isolate selected package-block consumption, complete
consumption provenance trace sections, MAT semantic differential parity, COM
channel execution, or any runtime metric.
