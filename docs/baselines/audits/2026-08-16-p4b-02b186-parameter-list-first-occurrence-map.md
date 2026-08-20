# P4B-02b186 parameter-list first-occurrence map audit

**Slice**: `parameter_list_first_occurrence_map_v1`
**Policy**: `sipi.p4b-02b186.parameter-list-first-occurrence-map-v1.first-occurrence-map`
**Status**: Delivered and verified.

## Semantics

Returns a `BTreeMap<String, usize>` mapping each distinct trimmed item to
its first-occurrence 0-based index.  This is the map形态 companion of 02b182
first-occurrence-indices (same data as ordered Vec of pairs vs keyed map).

## Cross-check

- 4/4 matched_hash_bound (mixed, all_equal, all_distinct, non_list)
- Evidence: `p4b-02b186-parameter-list-first-occurrence-map-crosscheck-evidence.v1.yaml`

## Verifier

- Charter schema valid, admission claims verified
- Source map mapping length 2
- Rust implementation tokens bound
- PLAN row present
