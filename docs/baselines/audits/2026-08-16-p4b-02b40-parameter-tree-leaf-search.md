# P4B-02b40 AMI Parameter Tree Leaf Search Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b40 (exact value-token search over an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_search_v1.rs` in `sipi-ami-text`: `find_parameter_tree_leaves_by_token_v1`
searches an `AmiParameterTreeV1` (P4B-02b7) for leaves whose value tokens contain an exact search
token (raw spelling equality), returning every matching canonical path
(`[root_name, ..., leaf_name]`) in canonical traversal order (branch children byte-wise, depth
first). Zero matches is a valid result (empty vector). Fail-closed: an empty search token
(`EmptyToken`) is strictly rejected. An independent Python reference replicates the
tokenize/build/search pipeline over 4 test cases.

## Result

- 5 Rust unit tests green (single match; multiple matches in canonical order; nested match;
  no match returns empty; empty token fails closed).
- Cross-check: 4 test cases (find single, find multiple, find nested, no match) driven through
  product runner `p4b_02b40_parameter_tree_leaf_search_runner`; independent Python reference
  matches 100% on valid flags and path lists; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b40_parameter_tree_leaf_search.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b40-parameter-tree-leaf-search-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b40-parameter-tree-leaf-search-stage.v1.yaml`; source map
  `p4b-02b40-mit-source-map.v1.yaml`.
- PLAN **P4B-02b40**; ledger note/gate P4B-02; coverage gates 206 -> 207.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Exact token match only; no substring, regex, or fuzzy search.
- No release certification, no acceptance evidence.
