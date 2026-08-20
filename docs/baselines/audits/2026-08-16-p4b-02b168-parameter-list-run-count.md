# P4B-02b168 Parameter List Run Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b168 (value-level adjacent-run count on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_run_count_v1.rs` in `sipi-ami-text`:
`parameter_list_run_count_v1` returns the number of maximal runs of equal adjacent trimmed
items of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty), counting maximal runs by raw byte equality
(per the P4B-02b0 raw-byte binding); the list is non-empty by rule so the run count is at
least 1. This is the run-count companion of 02b119 run-length-encode (the run count equals
the number of RLE entries) and of 02b120 longest-run (the longest run length is at most the
run count in the all-distinct case, exactly 1). Fail-closed: the value not declared List
yields `NotAList`; the token not matching the List shape yields `MalformedList`
(unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive instead of
panicking). An independent Python reference replicates the run-count rule over 4 test cases.

## Result

- 6 Rust unit tests green (single run, multiple runs, all distinct, single item, spacing
  canonicalized, non-list).
- Cross-check: 4 test cases (single run, multiple runs, all distinct, non-list) driven
  through product runner `p4b_02b168_parameter_list_run_count_runner`; independent Python
  reference matches 100% on counts and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b168_parameter_list_run_count.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b168-parameter-list-run-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b168-parameter-list-run-count-stage.v1.yaml`; source map
  `p4b-02b168-mit-source-map.v1.yaml`.
- PLAN **P4B-02b168**; ledger note/gate P4B-02; coverage gates 337 -> 338.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes run count on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
