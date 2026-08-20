# P4B-02b114 Parameter List Split-At-Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b114 (split-at-index partitioning on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_split_v1.rs` in `sipi-ami-text`:
`split_parameter_list_at_index_v1` splits a validated List-typed `AmiParameterValueV1` under
the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty) at a 0-based index:
returns the pair of canonical list tokens whose items are the trimmed items before and at/after
the split point (`[0, index)` and `[index, item_count)`, each re-joined with `", "`). This is
the partition inverse of 02b106 join and the split companion of 02b109 slice. Fail-closed: a
non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking); an index beyond the item count (`index > item_count`) yields
`IndexOutOfRange` carrying the requested index and the actual item count. A split at 0 or at the
item count yields the structurally empty token `()` on the empty side (not a valid 02b1 List
value; the operation is total on the token level and does not re-validate, mirroring 02b100
sole-item removal). An independent Python reference replicates the split rule over 5 test cases.

## Result

- 6 Rust unit tests green (middle split, split at zero, split at end, out-of-range index,
  non-list, spacing canonicalized).
- Cross-check: 5 test cases (middle split, split at zero, split at end, out-of-range, non-list)
  driven through product runner `p4b_02b114_parameter_list_split_runner`; independent Python
  reference matches 100% on token pairs and error keys; 5/5 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b114_parameter_list_split.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b114-parameter-list-split-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b114-parameter-list-split-stage.v1.yaml`; source map
  `p4b-02b114-mit-source-map.v1.yaml`.
- PLAN **P4B-02b114**; ledger note/gate P4B-02; coverage gates 283 -> 284.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Splits list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
