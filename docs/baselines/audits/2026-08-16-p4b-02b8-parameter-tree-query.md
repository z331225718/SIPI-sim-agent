# P4B-02b8 AMI Parameter Tree Query Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b8 (AMI parameter tree query core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_query_v1.rs` in `sipi-ami-text`: `query_parameter_tree_v1`
performs deterministic path-based queries over typed `AmiParameterTreeV1` hierarchies (P4B-02b7).
Query results return `QueryResultV1::Branch(&node)` or `QueryResultV1::Leaf(&node)`.
Fail-closed: empty path queries (`EmptyPath`), root name mismatch (`RootMismatch`), or
path non-matches (`PathNotFound`) are strictly rejected. An independent Python reference recomputes path queries over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; queries existing branch and leaf; empty path rejection;
  root mismatch rejection; path not found rejection).
- Cross-check: 3 test cases (query existing leaf, query existing branch, path not found)
  driven through product runner `p4b_02b8_parameter_tree_query_runner`; independent Python reference
  matches 100% on valid flags, result kinds (branch/leaf), target node names, and error strings;
  3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b8_parameter_tree_query.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b8-parameter-tree-query-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b8-parameter-tree-query-stage.v1.yaml`; source map
  `p4b-02b8-mit-source-map.v1.yaml`.
- PLAN **P4B-02b8**; ledger note/gate P4B-02; coverage gates 134 -> 135.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
