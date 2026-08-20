# P4B-02b154 Parameter List Jaccard Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b154 (set-based Jaccard similarity on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_jaccard_index_v1.rs` in `sipi-ami-text`:
`list_jaccard_index_v1` computes the Jaccard index of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the ratio of the sizes of the distinct intersection and distinct union of
the two values' trimmed items (raw byte equality, per the P4B-02b0 raw-byte binding), as an f64
in [0, 1]: 0 for disjoint values, 1 for values with the same distinct set. This is the
set-similarity companion of 02b148 intersection and of 02b150 union. Fail-closed: either value
not declared List yields `NotAList`; either token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the similarity rule
over 4 test cases.

## Result

- 6 Rust unit tests green (identical distinct sets one, disjoint zero, partial overlap,
  duplicates ignored, non-list, spacing canonicalized).
- Cross-check: 4 test cases (identical sets, disjoint, partial overlap, non-list) driven through
  product runner `p4b_02b154_parameter_list_jaccard_index_runner`; independent Python
  reference matches 100% on formatted indices and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b154_parameter_list_jaccard_index.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b154-parameter-list-jaccard-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b154-parameter-list-jaccard-index-stage.v1.yaml`; source map
  `p4b-02b154-mit-source-map.v1.yaml`.
- PLAN **P4B-02b154**; ledger note/gate P4B-02; coverage gates 323 -> 324.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes Jaccard indices on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
