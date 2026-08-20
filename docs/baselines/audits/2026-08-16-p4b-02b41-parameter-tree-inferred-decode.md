# P4B-02b41 AMI Parameter Tree Inferred Decoding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b41 (infer-then-decode composition for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_inferred_decode_v1.rs` in `sipi-ami-text`:
`decode_parameter_tree_with_inferred_types_v1` composes the leaf value type inference core
(P4B-02b33) and the leaf value decoding core (P4B-02b37) into one fail-closed pass: infer one
`AmiParameterTypeV1` per leaf from its own value tokens (deterministic precedence Integer > Float >
Boolean > List > String), then decode every leaf's single value token into a typed Rust value
(`DecodedLeafValueV1`). No caller-supplied type map is needed — this is the end-to-end consumption
path for an untyped AMI parameter tree (parse -> tree -> infer -> decode). Both underlying cores are
reused verbatim; errors are wrapped by stage: `Inference(...)` (empty tokens, conflicting tokens,
duplicate leaf names) or `Decoding(...)` (only multi-token leaves, since inference already
guarantees single-token type validity). An independent Python reference replicates the
tokenize/build/infer/decode pipeline over 4 test cases.

## Result

- 6 Rust unit tests green (mixed types infer+decode; multi-token fails at decoding stage;
  conflicting tokens fail at inference stage; empty tokens fail at inference stage; duplicate leaf
  names fail at inference stage; List token infers and decodes).
- Cross-check: 4 test cases (infer and decode mixed, multi-token leaf, conflicting tokens,
  duplicate leaf names) driven through product runner `p4b_02b41_parameter_tree_inferred_decode_runner`;
  independent Python reference matches 100% on valid flags, decoded counts, type maps, value maps,
  and error contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b41_parameter_tree_inferred_decode.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b41-parameter-tree-inferred-decode-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b41-parameter-tree-inferred-decode-stage.v1.yaml`; source map
  `p4b-02b41-mit-source-map.v1.yaml`.
- PLAN **P4B-02b41**; ledger note/gate P4B-02; coverage gates 207 -> 208.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Composition only; no new value semantics beyond P4B-02b33/02b37.
- No release certification, no acceptance evidence.
