# P4B-02b9 AMI Parameter Tree S-Expression Formatter Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b9 (AMI parameter tree S-expression formatter core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_formatter_v1.rs` in `sipi-ami-text`: `format_parameter_trees_v1`
formats typed `AmiParameterTreeV1` hierarchies (P4B-02b7) back into canonical parenthesized
S-expression string representations (`format_node` formats `Branch` with indentation and `Leaf`
with space-separated value tokens).
Fail-closed: empty tree lists (`EmptyTreeList`) are strictly rejected. An independent Python reference recomputes S-expression formatting over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; formats tree hierarchy; empty tree list rejection).
- Cross-check: 3 test cases (valid tree formatting, nested branches formatting, empty document)
  driven through product runner `p4b_02b9_parameter_tree_formatter_runner`; independent Python reference
  matches 100% on valid flags, formatted S-expression text strings, and error codes/messages; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b9_parameter_tree_formatter.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b9-parameter-tree-formatter-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b9-parameter-tree-formatter-stage.v1.yaml`; source map
  `p4b-02b9-mit-source-map.v1.yaml`.
- PLAN **P4B-02b9**; ledger note/gate P4B-02; coverage gates 135 -> 136.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
