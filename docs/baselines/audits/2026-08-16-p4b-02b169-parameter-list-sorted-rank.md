# P4B-02b169 Parameter List Sorted Rank Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b169 (value-level sorted rank on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_sorted_rank_v1.rs` in `sipi-ami-text`:
`parameter_list_sorted_rank_v1` returns the zero-based rank of a raw query item within a
validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): the first position of an item equal to the
query in ascending sorted order of the value's trimmed items (raw byte equality and byte
lexicographic order, per the P4B-02b0 raw-byte binding; for valid UTF-8 this order equals
code-point order), with duplicates counted as separate positions; the query item is compared
without trimming (raw query semantics, mirroring 02b110 index-of). This bridges 02b110
index-of (position in the original sequence) and the order statistics 02b162 nth-smallest /
02b163 nth-largest (rank maps to the nth-smallest item). Fail-closed: the value not declared
List yields `NotAList`; the token not matching the List shape yields `MalformedList`
(unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive instead of
panicking); no item equal to the query yields `ItemNotFound` (never confused with a legal
rank 0). An independent Python reference replicates the rank rule over 4 test cases.

## Result

- 6 Rust unit tests green (sorted rank, duplicates first rank, query not found, spacing
  canonicalized, non-list, raw query byte equality).
- Cross-check: 4 test cases (middle rank, duplicates first rank, query not found, non-list)
  driven through product runner `p4b_02b169_parameter_list_sorted_rank_runner`; independent
  Python reference matches 100% on ranks and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b169_parameter_list_sorted_rank.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b169-parameter-list-sorted-rank-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b169-parameter-list-sorted-rank-stage.v1.yaml`; source map
  `p4b-02b169-mit-source-map.v1.yaml`.
- PLAN **P4B-02b169**; ledger note/gate P4B-02; coverage gates 338 -> 339.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes sorted rank on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
