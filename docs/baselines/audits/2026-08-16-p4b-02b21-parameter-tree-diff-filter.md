# P4B-02b21 AMI Parameter Tree Structural Diff Entry Filtering Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b21 (AMI parameter tree structural diff entry filtering core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_diff_filter_v1.rs` in `sipi-ami-text`: `filter_parameter_tree_diffs_v1`
filters sequences of atomic structural diff entries (`TreeDiffEntryV1`, P4B-02b11) by applying predicate closures
over diff entry properties and node paths.
Fail-closed: empty diff lists (`EmptyDiffList`) or empty filtered diff results (`EmptyFilteredResult`)
are strictly rejected. An independent Python reference recomputes diff entry filtering rules over 3 test cases.

## Result

- 4 Rust unit tests green (policy fixed; filters diffs by predicate; rejects empty diff list;
  rejects empty filtered result).
- Cross-check: 3 test cases (filter diff entry, empty filtered result, identical trees)
  driven through product runner `p4b_02b21_parameter_tree_diff_filter_runner`; independent Python reference
  matches 100% on valid flags, filtered diff counts, filtered diff entry lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b21_parameter_tree_diff_filter.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b21-parameter-tree-diff-filter-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b21-parameter-tree-diff-filter-stage.v1.yaml`; source map
  `p4b-02b21-mit-source-map.v1.yaml`.
- PLAN **P4B-02b21**; ledger note/gate P4B-02; coverage gates 147 -> 148.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
