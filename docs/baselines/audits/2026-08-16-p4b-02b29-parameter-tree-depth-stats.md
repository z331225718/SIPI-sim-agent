# P4B-02b29 AMI Parameter Tree Depth Statistics Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b29 (AMI parameter tree depth statistics core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_depth_stats_v1.rs` in `sipi-ami-text`: `compute_parameter_tree_depth_stats_v1`
computes depth statistics for a typed `AmiParameterTreeV1` hierarchy (P4B-02b7): maximum depth, minimum depth,
leaf count, and per-depth node and leaf histograms (root at depth 0).
Fail-closed: empty tree lists (`EmptyTreeList`) are strictly rejected.
An independent Python reference recomputes depth statistics over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; computes nested depth stats; single node depth stats).
- Cross-check: 3 test cases (nested depth stats, single node depth stats, deep depth stats)
  driven through product runner `p4b_02b29_parameter_tree_depth_stats_runner`; independent Python reference
  matches 100% on valid flags, max/min depth, leaf counts, and per-depth histograms; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b29_parameter_tree_depth_stats.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b29-parameter-tree-depth-stats-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b29-parameter-tree-depth-stats-stage.v1.yaml`; source map
  `p4b-02b29-mit-source-map.v1.yaml`.
- PLAN **P4B-02b29**; ledger note/gate P4B-02; coverage gates 195 -> 196.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
