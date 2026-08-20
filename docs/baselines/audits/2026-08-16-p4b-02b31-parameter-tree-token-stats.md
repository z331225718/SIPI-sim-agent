# P4B-02b31 AMI Parameter Tree Token Statistics Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b31 (AMI parameter tree value-token statistics core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_token_stats_v1.rs` in `sipi-ami-text`: `compute_parameter_tree_token_stats_v1`
computes value-token statistics for a typed `AmiParameterTreeV1` hierarchy (P4B-02b7):
leaf count, total value token count, max tokens per leaf, and sorted distinct token spellings.
Fail-closed: empty tree lists (`EmptyTreeList`) are strictly rejected.
An independent Python reference recomputes token statistics over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; computes token stats; single leaf token stats).
- Cross-check: 3 test cases (typed token stats, single leaf token stats, repeated token stats)
  driven through product runner `p4b_02b31_parameter_tree_token_stats_runner`; independent Python reference
  matches 100% on valid flags, leaf counts, token counts, max tokens per leaf, and distinct token lists; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b31_parameter_tree_token_stats.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b31-parameter-tree-token-stats-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b31-parameter-tree-token-stats-stage.v1.yaml`; source map
  `p4b-02b31-mit-source-map.v1.yaml`.
- PLAN **P4B-02b31**; ledger note/gate P4B-02; coverage gates 197 -> 198.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
