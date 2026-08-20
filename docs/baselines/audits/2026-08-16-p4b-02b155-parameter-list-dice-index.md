# P4B-02b155 Parameter List Dice Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b155 (set-based Dice similarity on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_dice_index_v1.rs` in `sipi-ami-text`:
`list_dice_index_v1` computes the Sorensen-Dice index of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns `2 * distinct_intersection_size / (size_a + size_b)` over the distinct
trimmed item sets of the two values (raw byte equality, per the P4B-02b0 raw-byte binding), as
an f64 in [0, 1]: 0 for disjoint values, 1 for values with the same distinct set. This is the
set-similarity companion of 02b154 Jaccard index (Dice = 2*J/(1+J) for J > 0). Fail-closed:
either value not declared List yields `NotAList`; either token not matching the List shape
yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the similarity rule
over 4 test cases.

## Result

- 6 Rust unit tests green (identical distinct sets one, disjoint zero, partial overlap,
  duplicates ignored, non-list, spacing canonicalized).
- Cross-check: 4 test cases (identical sets, disjoint, partial overlap, non-list) driven through
  product runner `p4b_02b155_parameter_list_dice_index_runner`; independent Python reference
  matches 100% on formatted indices and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b155_parameter_list_dice_index.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b155-parameter-list-dice-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b155-parameter-list-dice-index-stage.v1.yaml`; source map
  `p4b-02b155-mit-source-map.v1.yaml`.
- PLAN **P4B-02b155**; ledger note/gate P4B-02; coverage gates 324 -> 325.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes Dice indices on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
