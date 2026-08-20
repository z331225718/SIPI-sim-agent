# P4B-02b38 AMI Parameter Tree Defaults Application Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b38 (fill-missing defaults application for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_apply_defaults_v1.rs` in `sipi-ami-text`: `apply_parameter_tree_defaults_v1`
applies a caller-supplied defaults map (leaf name -> value tokens) to an `AmiParameterTreeV1`
(P4B-02b7): every default whose name is not already a leaf anywhere in the tree is added as a new
root-level leaf with the default tokens; a default whose name already exists is skipped (defaults
fill only missing parameters). Result carries added/skipped counts and the new tree (root children
byte-wise ordered). Fail-closed: empty defaults map (`EmptyDefaults`), default with no value tokens
(`EmptyDefaultTokens`), and root-leaf trees (`RootNotBranch`) are strictly rejected. An independent
Python reference replicates the tokenize/build/apply pipeline over 4 test cases.

## Result

- 7 Rust unit tests green (fills missing at root; existing leaf skipped; deeper existing leaf
  skipped; empty defaults; empty default tokens; root-leaf tree fails closed; mixed add/skip counts).
- Cross-check: 4 test cases (fill missing, skip existing, empty defaults, empty default tokens)
  driven through product runner `p4b_02b38_parameter_tree_apply_defaults_runner`; independent Python
  reference matches 100% on valid flags, added/skipped counts, root names, resulting tree
  structures, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b38_parameter_tree_apply_defaults.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b38-parameter-tree-apply-defaults-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b38-parameter-tree-apply-defaults-stage.v1.yaml`; source map
  `p4b-02b38-mit-source-map.v1.yaml`.
- PLAN **P4B-02b38**; ledger note/gate P4B-02; coverage gates 204 -> 205.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Defaults are caller-supplied tokens; no type checking or default validity (P4B-02b4 catalog
  default validity applies at the catalog layer).
- No release certification, no acceptance evidence.
