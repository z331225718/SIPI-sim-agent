# P4B-02b179 Parameter List Mode Frequency Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b179 (value-level mode frequency on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_mode_frequency_v1.rs` in `sipi-ami-text`:
`parameter_list_mode_frequency_v1` returns the maximum occurrence count over the distinct
trimmed items of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1 list
rule (`(item, item, ...)`, items trimmed, non-empty), by raw byte equality (per the P4B-02b0
raw-byte binding). The list is non-empty by rule so the mode frequency is at least 1; an
all-distinct list has mode frequency 1. This is the count companion of 02b165 mode items (the
modes are exactly the items at mode frequency) and of 02b121 frequency (the mode frequency is
the maximum entry count). Fail-closed: the value not declared List yields `NotAList`; the
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the rule over 4 test cases.

## Result

- 6 Rust unit tests green (mode frequency, all distinct one, all equal len, single item one,
  spacing canonicalized, non-list).
- Cross-check: 4 test cases (has mode, all distinct, all equal, non-list) driven through
  product runner `p4b_02b179_parameter_list_mode_frequency_runner`; independent Python
  reference matches 100% on counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b179_parameter_list_mode_frequency.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b179-parameter-list-mode-frequency-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b179-parameter-list-mode-frequency-stage.v1.yaml`; source map
  `p4b-02b179-mit-source-map.v1.yaml`.
- PLAN **P4B-02b179**; ledger note/gate P4B-02; coverage gates 348 -> 349.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes mode frequency on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
