# P4B-02b52 AMI Parameter Tree Token Remap Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b52 (leaf value-token substitution for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_token_remap_v1.rs` in `sipi-ami-text`: `remap_parameter_tree_tokens_v1`
remaps leaf value tokens of an `AmiParameterTreeV1` (P4B-02b7) per a caller-supplied substitution
map (old token -> new token), returning a new tree with the number of replacements. Only leaf value
tokens are remapped; node names are never touched (a key matching only a name is reported as
`MissingToken`). Fail-closed: an empty remap map (`EmptyRemap`), a remap key that does not occur as
any leaf value token (`MissingToken`), and an empty remap value (`InvalidRemapValue`, invalid as a
leaf token downstream) are strictly rejected. An independent Python reference replicates the
tokenize/build/substitute pipeline over 4 test cases.

## Result

- 6 Rust unit tests green (remap leaf tokens; multi-occurrence all replaced; empty remap; missing
  token; empty remap value; node names not remapped).
- Cross-check: 4 test cases (simple remap, multi occurrence, missing token, empty remap) driven
  through product runner `p4b_02b52_parameter_tree_token_remap_runner`; independent Python
  reference matches 100% on valid flags, replacement counts, resulting tree structures, and error
  contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b52_parameter_tree_token_remap.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b52-parameter-tree-token-remap-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b52-parameter-tree-token-remap-stage.v1.yaml`; source map
  `p4b-02b52-mit-source-map.v1.yaml`.
- PLAN **P4B-02b52**; ledger note/gate P4B-02; coverage gates 218 -> 219.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Remaps leaf value tokens only; node names and branch structure are untouched.
- No release certification, no acceptance evidence.
