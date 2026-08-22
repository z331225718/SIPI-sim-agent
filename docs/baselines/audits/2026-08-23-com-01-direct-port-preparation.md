# COM-01 Direct-Port Materialization Audit

Date: 2026-08-23

This audit covers the pinned Agent-COM config validate boundary and its Rust
source-schema materializer. The direct crate now parses and executes the
exact r4.80 schema/default catalog, profile preset catalog, and a derived
consumption registry. It does not execute the COM runtime.

## Source And Custody

Source is fixed to Agent-COM commit
5272ffe74702cd585054d975559b06f8afae7b6e, tree
7094ab6e84989b218730c52432c70da10261f8ea. The manifest records the pinned
Git object identities for CLI, schema, materializer, literals, derived rules,
consumption source, profile catalog, and fingerprint helper.

The lane quarantines the exact schema and behavior-preset blobs under the
upstream MIT notice. The consumption registry is mechanically derived from
the pinned consumption.py frozenset declarations and records that source
hash. Workbook and MAT bytes remain owner-supplied external fixtures; no
configuration payload is vendored.

## Executed Surface

The Rust implementation performs source-line-ordered param and OP
assignments, case-insensitive workbook lookup, required/default resolution,
MATLAB scalar/vector/matrix literals, units/scales, DFE limit assembly,
package-case transpose/expansion and selected package substitution, core
derived timing values, CTLE type/order, RxFFE aliases, floating DFE/RxFFE
flags, dynamic TXFFE cleanup, and duplicate-package warning/fix behavior.

The materializer now treats all allocation-driving values as bounded data:
`M`, `L`, `N_b`, `N_bg`, RxFFE tap counts, and every `z_p select` entry must
be finite integers in their admitted ranges. Input files, cell grids, numeric
payloads, materialized outputs, and broadcasts have explicit budgets; array
dimensions use checked multiplication. A NaN in an optional XLSX slot is
treated as the upstream reader's missing-cell representation and therefore
resolves through the pinned default, while consumed numeric inputs and array
payloads otherwise reject NaN/infinity. The pinned `EH_max` default remains
positive infinity, matching upstream semantics.

Override names are canonicalized to the exact schema key after
case-insensitive validation. Case-folded duplicates and dynamic names with no
materialized schema call fail closed instead of being accepted and then
silently ignored.

Before delegating semantic decoding to `sipi-com`, the direct crate performs
a pre-allocation container preflight. XLSX admission inventories every ZIP
member's declared uncompressed size with checked aggregate accounting, then
bounded-reads workbook relationships, sharedStrings, and the selected
COM_Settings sheet. It parses cell and dimension coordinates and rejects any
sheet whose `max_row * max_column` exceeds the cell budget, including a lone
`XFD1048576` cell. MAT admission uses a depth-, element-, byte-, and
dimension-count-bounded zlib scanner and checked dimension products for the
parameter grid and every nested matrix. These checks execute before either
shared reader can allocate
from hostile ZIP/XML/MAT metadata; the shared readers remain the only
semantic decoders.

The output envelope matches the upstream JSON/text shape: summary counts,
strict materialized JSON, source SHA-256, materialized fingerprint field,
warning codes, and exhaustive implemented/report-only/unimplemented/
obsolete/unverified consumption buckets with status counts. execution.performed
is false because this is validation/materialization, not a COM runtime run.

## Differential Procedure

tools/run_com_01_direct_oracle.py binds the upstream Git object, accepts an
owner-supplied primary XLSX and candidate Rust executable, derives a temporary
duplicate-package CSV from the same workbook, and runs the 14-case corpus
twice with fresh nonces. Reports contain only redacted summaries, fixture
hashes, exit codes, error categories, value-projection hashes, key/count
inventories, and bounded difference-key lists. Raw stdout/stderr, complete
materialized parameter values, and local paths are not stored. Error parity
requires both exit-code and error-category equality.

The pinned primary fixture currently has semantic parameter/options parity:
148 parameters and 90 options, with all materialized values matching the
Python oracle for the ported materialized value/status buckets. The four
upstream consumption provenance/trace sections remain outside the comparison
projection and explicitly open. The fingerprint byte serialization remains open
because Python preserves integer-vs-float source types and uses different
short-float formatting; this is reported as
values_equal_fingerprint_drift, not silently promoted to full parity.

## Open Items

- exact Python fingerprint serialization for all integer/float source kinds;
- selected package-block end-to-end differential fixture;
- full provenance/branch-trace sections of configuration_consumption;
- immutable candidate archive build and replay custody.

Status: implementation_materialized_open.

This work is not a COM runtime/product-capability promotion, migration-row
close, release claim, or license conclusion for unrelated upstream paths.
