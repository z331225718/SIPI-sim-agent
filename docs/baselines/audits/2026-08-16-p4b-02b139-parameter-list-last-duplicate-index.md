# P4B-02b139 Parameter List Last-Duplicate Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b139 (last repeating position on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_last_duplicate_index_v1.rs` in `sipi-ami-text`:
`parameter_list_last_duplicate_index_v1` locates the last repeating position of the trimmed
items of a validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the largest 0-based index whose
trimmed item equals some earlier trimmed item (raw byte equality, per the P4B-02b0 raw-byte
binding). This is the reverse-position companion of 02b138 first-duplicate-index and of 02b111
single-item last-index-of. Fail-closed: a non-List value yields `NotAList`; a token that does
not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); a list with no repeating
item yields `NoDuplicate` (never conflated with the valid index 0). An independent Python
reference replicates the repeat rule over 4 test cases.

## Result

- 6 Rust unit tests green (last repeat, adjacent repeat, all distinct, single item, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (last repeat, adjacent repeat, all distinct, non-list) driven
  through product runner `p4b_02b139_parameter_list_last_duplicate_index_runner`; independent
  Python reference matches 100% on indices and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b139_parameter_list_last_duplicate_index.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b139-parameter-list-last-duplicate-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b139-parameter-list-last-duplicate-index-stage.v1.yaml`; source map
  `p4b-02b139-mit-source-map.v1.yaml`.
- PLAN **P4B-02b139**; ledger note/gate P4B-02; coverage gates 308 -> 309.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Locates repeats on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
