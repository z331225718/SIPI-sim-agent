# P4B-02b60 Parameter Tree Token Frequencies Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b60 (global value-token frequency landscape)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_token_frequencies_v1.rs` in `sipi-ami-text`:
`compute_parameter_tree_token_frequencies_v1` computes the global value-token frequency landscape
of an `AmiParameterTreeV1` (P4B-02b7): every distinct leaf value token with its total occurrence
count across all leaves, plus the total token count. This complements the per-leaf token statistics
(P4B-02b31, which reports the distinct token set without frequencies). Result-based: any tree can be
analyzed. An independent Python reference replicates the tokenize/build/count pipeline over
4 test cases.

## Result

- 4 Rust unit tests green (shared tokens across leaves; repeated tokens in one leaf; unique
  tokens; root leaf without tokens is empty).
- Cross-check: 4 test cases (shared tokens, repeated in leaf, unique tokens, root leaf empty)
  driven through product runner `p4b_02b60_parameter_tree_token_frequencies_runner`; independent
  Python reference matches 100% on valid flags, total counts, and frequency maps;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b60_parameter_tree_token_frequencies.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b60-parameter-tree-token-frequencies-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b60-parameter-tree-token-frequencies-stage.v1.yaml`; source map
  `p4b-02b60-mit-source-map.v1.yaml`.
- PLAN **P4B-02b60**; ledger note/gate P4B-02; coverage gates 229 -> 230.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Frequency counting only; no token typing or semantic interpretation.
- No release certification, no acceptance evidence.
