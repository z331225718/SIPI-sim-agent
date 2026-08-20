# P4B-02b109 Parameter List Range Slice Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b109 (half-open range slicing on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_slice_v1.rs` in `sipi-ami-text`:
`slice_parameter_list_items_v1` slices a validated List-typed `AmiParameterValueV1` under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical list
token whose items are the trimmed items at half-open indices `[start, end)` (0-based, end
exclusive, re-joined with `", "`). This is the range companion of the list-edit family (02b84
access, 02b100 remove, 02b102 insert, 02b103 swap, 02b104 reverse, 02b105 sort, 02b106 join).
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape
yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking); a bound violating `start <= end <= item_count` yields
`IndexOutOfRange` carrying the offending bound and the actual item count. An empty range
(`start == end`) yields the structurally empty token `()` (not a valid 02b1 List value; the
operation is total on the token level and does not re-validate, mirroring 02b100 sole-item
removal). An independent Python reference replicates the slice rule over 5 test cases.

## Result

- 6 Rust unit tests green (middle range, full range, empty range, out-of-range bounds, non-list,
  spacing canonicalized).
- Cross-check: 5 test cases (middle slice, full slice, empty slice, out-of-range, non-list) driven
  through product runner `p4b_02b109_parameter_list_slice_runner`; independent Python reference
  matches 100% on tokens and error keys; 5/5 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b109_parameter_list_slice.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b109-parameter-list-slice-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b109-parameter-list-slice-stage.v1.yaml`; source map
  `p4b-02b109-mit-source-map.v1.yaml`.
- PLAN **P4B-02b109**; ledger note/gate P4B-02; coverage gates 278 -> 279.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Slices list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
