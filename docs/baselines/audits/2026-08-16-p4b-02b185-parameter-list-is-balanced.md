# P4B-02b185 parameter-list is-balanced audit

**Slice**: `parameter_list_is_balanced_v1`
**Policy**: `sipi.p4b-02b185.parameter-list-is-balanced-v1.is-balanced`
**Status**: Delivered and verified.

## Semantics

Returns whether every maximal run of equal adjacent trimmed items has the
same length (`true`) or not (`false`).  A single run is always balanced;
a fully-distinct list of length > 1 is balanced (all runs have length 1).

## Cross-check

- 4/4 matched_hash_bound (balanced_two_runs, unbalanced_runs,
  all_equal_single_run, non_list)
- Evidence: `p4b-02b185-parameter-list-is-balanced-crosscheck-evidence.v1.yaml`

## Verifier

- Charter schema valid, admission claims verified
- Source map mapping length 2
- Rust implementation tokens bound
- PLAN row present
