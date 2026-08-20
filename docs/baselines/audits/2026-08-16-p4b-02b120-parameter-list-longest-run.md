# P4B-02b120 Parameter List Longest-Run Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b120 (longest consecutive run analysis on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_run_v1.rs` in `sipi-ami-text`:
`longest_run_parameter_list_v1` finds the longest run of consecutive equal trimmed items in a
validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty): returns the `(item, run_length)` pair of the longest consecutive
equal trimmed items (raw byte equality, per the P4B-02b0 raw-byte binding); ties are resolved to
the earliest run. This is the run-max companion of 02b119 run-length encoding (whose run list it
maximizes) and of 02b108 occurrence counting (a run never exceeds the total occurrence count of
its item). Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the run rule over 4 test cases.

## Result

- 6 Rust unit tests green (longest run, earliest tie, all distinct, single item, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (longest run, earliest tie, all distinct, non-list) driven through
  product runner `p4b_02b120_parameter_list_longest_run_runner`; independent Python reference
  matches 100% on item/length pairs and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b120_parameter_list_longest_run.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b120-parameter-list-longest-run-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b120-parameter-list-longest-run-stage.v1.yaml`; source map
  `p4b-02b120-mit-source-map.v1.yaml`.
- PLAN **P4B-02b120**; ledger note/gate P4B-02; coverage gates 289 -> 290.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Analyzes list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
