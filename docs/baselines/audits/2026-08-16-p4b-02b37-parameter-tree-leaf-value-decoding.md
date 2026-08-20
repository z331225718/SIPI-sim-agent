# P4B-02b37 AMI Parameter Tree Leaf Value Decoding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b37 (typed decode of AMI parameter tree leaf values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_decode_values_v1.rs` in `sipi-ami-text`: `decode_parameter_tree_leaf_values_v1`
walks an `AmiParameterTreeV1` (P4B-02b7) and decodes every leaf's single value token into a typed Rust
value (`DecodedLeafValueV1`: Float(f64)/Integer(i64)/Boolean(bool)/String/List(Vec<String>)) using a
caller-supplied type map (leaf name -> `AmiParameterTypeV1`). The P4B-02b1 `AmiParameterValueV1::try_new`
rule is reused verbatim per leaf token before decoding (single source of truth). Fail-closed: missing
type (`MissingType`), invalid leaf name (`InvalidLeafName`), value violating its type rule
(`InvalidValue` wrapping the P4B-02b1 error), empty value tokens (`EmptyValueTokens`), multi-token
leaves (`MultiTokenValue` with token count — decode requires the AMI single-value form), and duplicate
leaf names (`DuplicateLeafName`) are strictly rejected. Raw spellings are preserved (quoted tokens keep
their quotes; no normalization per P4B-02b0). An independent Python reference replicates the
tokenize/build/validate/decode pipeline over 4 test cases.

## Result

- 7 Rust unit tests green (mixed types decode; exact float precision; multi-token rejection; missing
  type; invalid value; empty tokens; duplicate leaf names).
- Cross-check: 4 test cases (mixed decode, multi-token value, missing type, invalid value for type)
  driven through product runner `p4b_02b37_parameter_tree_leaf_value_decoding_runner`; independent
  Python reference matches 100% on valid flags, decoded counts, value maps, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b37_parameter_tree_leaf_value_decoding.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b37-parameter-tree-leaf-value-decoding-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b37-parameter-tree-leaf-value-decoding-stage.v1.yaml`; source map
  `p4b-02b37-mit-source-map.v1.yaml`.
- PLAN **P4B-02b37**; ledger note/gate P4B-02; coverage gates 203 -> 204.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Decodes exactly one value token per leaf; multi-token leaves are rejected (use P4B-02b33/02b34 for
  type handling and P4B-02b32 for validation-only passes).
- No release certification, no acceptance evidence.
