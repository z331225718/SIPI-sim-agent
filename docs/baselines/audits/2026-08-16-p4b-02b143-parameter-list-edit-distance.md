# P4B-02b143 Parameter List Edit Distance Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b143 (list-value edit distance on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_edit_distance_v1.rs` in `sipi-ami-text`:
`list_edit_distance_v1` computes the Levenshtein edit distance of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the minimum number of single-item insert, delete, or substitute operations
needed to transform one trimmed item sequence into the other (unit costs; equality by raw byte
equality, per the P4B-02b0 raw-byte binding). The edit distance equals `max(n, m) - lcs_length`
when one sequence is a subsequence of the other and otherwise is at least that bound. This is
the distance companion of 02b142 LCS length. Fail-closed: either value not declared List yields
`NotAList`; either token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the Levenshtein rule over 4 test cases.

## Result

- 6 Rust unit tests green (substitute, identical zero, disjoint max, insert/delete ops,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (substitute, identical, disjoint, non-list) driven through product
  runner `p4b_02b143_parameter_list_edit_distance_runner`; independent Python reference
  matches 100% on distances and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b143_parameter_list_edit_distance.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b143-parameter-list-edit-distance-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b143-parameter-list-edit-distance-stage.v1.yaml`; source map
  `p4b-02b143-mit-source-map.v1.yaml`.
- PLAN **P4B-02b143**; ledger note/gate P4B-02; coverage gates 312 -> 313.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes edit distances on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
