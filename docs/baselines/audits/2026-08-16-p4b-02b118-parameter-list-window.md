# P4B-02b118 Parameter List Sliding Windows Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b118 (sliding window enumeration on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_window_v1.rs` in `sipi-ami-text`:
`window_parameter_list_v1` enumerates the sliding windows of the trimmed items of a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the canonical list tokens of every consecutive run of exactly
`window_size` trimmed items, in order, each re-joined with `", "` (windows slide by one item;
when the list has fewer items than `window_size`, no window exists and the result is empty).
This is the overlapping companion of 02b116 fixed-size chunking and 02b109 slice. Fail-closed: a
non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking); a zero window size yields `InvalidWindowSize` (no valid window
exists). An independent Python reference replicates the window rule over 5 test cases.

## Result

- 6 Rust unit tests green (windows of three, single window, window larger than list, zero
  window size, non-list, spacing canonicalized).
- Cross-check: 5 test cases (windows of three, single window, window larger than list, zero
  window size, non-list) driven through product runner `p4b_02b118_parameter_list_window_runner`;
  independent Python reference matches 100% on tokens and error keys; 5/5 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b118_parameter_list_window.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b118-parameter-list-window-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b118-parameter-list-window-stage.v1.yaml`; source map
  `p4b-02b118-mit-source-map.v1.yaml`.
- PLAN **P4B-02b118**; ledger note/gate P4B-02; coverage gates 287 -> 288.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Windows list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
