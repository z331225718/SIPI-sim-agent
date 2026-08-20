# P4B-02b25 AMI Parameter Tree Cycle Detection Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b25 (AMI parameter tree cycle detection core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_detect_cycles_v1.rs` in `sipi-ami-text`: `detect_parameter_tree_cycles_v1`
detects structural cycles in typed `AmiParameterTreeV1` hierarchies (P4B-02b7) using a DFS white/gray/black
visited-state walk, returning `ParameterTreeCycleScanV1` with an acyclic flag and the first offending
canonical path when a cycle exists. Built trees are immutable and acyclic by construction, so valid trees
scan as acyclic; the scan is exposed as an explicit integrity check.
An independent Python reference recomputes the cycle scan over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; acyclic tree scan; single node tree is acyclic).
- Cross-check: 3 test cases (nested acyclic tree, single node tree, wide acyclic tree)
  driven through product runner `p4b_02b25_parameter_tree_detect_cycles_runner`; independent Python reference
  matches 100% on valid flags, is_acyclic flags, cycle paths, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b25_parameter_tree_detect_cycles.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b25-parameter-tree-detect-cycles-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b25-parameter-tree-detect-cycles-stage.v1.yaml`; source map
  `p4b-02b25-mit-source-map.v1.yaml`.
- PLAN **P4B-02b25**; ledger note/gate P4B-02; coverage gates 191 -> 192.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
