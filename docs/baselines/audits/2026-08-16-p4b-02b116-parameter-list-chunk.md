# P4B-02b116 Parameter List Chunking Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b116 (fixed-size chunking on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_chunk_v1.rs` in `sipi-ami-text`:
`chunk_parameter_list_v1` chunks the trimmed items of a validated List-typed
`AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty) into consecutive fixed-size groups: returns the canonical list tokens of the trimmed
items in order, each holding at most `chunk_size` items (every chunk except the last is exactly
`chunk_size`; the last chunk holds the remainder, which is non-empty because the list itself is
non-empty), each re-joined with `", "`. This is the grouping companion of 02b109 slice and
02b114 split. Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); a zero chunk size yields
`InvalidChunkSize` (no valid chunking exists). An independent Python reference replicates the
chunking rule over 4 test cases.

## Result

- 6 Rust unit tests green (even chunks, remainder chunk, single chunk, zero chunk size,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (even chunks, remainder chunk, zero chunk size, non-list) driven
  through product runner `p4b_02b116_parameter_list_chunk_runner`; independent Python
  reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b116_parameter_list_chunk.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b116-parameter-list-chunk-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b116-parameter-list-chunk-stage.v1.yaml`; source map
  `p4b-02b116-mit-source-map.v1.yaml`.
- PLAN **P4B-02b116**; ledger note/gate P4B-02; coverage gates 285 -> 286.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Chunks list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
