# P4B-02b129 Parameter List Last-Sublist Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b129 (last-position sublist lookup on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_last_sublist_index_v1.rs` in `sipi-ami-text`:
`last_sublist_index_parameter_list_v1` locates the last start index of a query sublist in the
trimmed items of a validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the 0-based start index of the latest
window equal to the query items element-wise (raw byte equality, per the P4B-02b0 raw-byte
binding; query items are not trimmed). An empty query sublist is vacuously contained at index 0.
This is the reverse-position companion of 02b128 first-sublist lookup and of 02b111 single-item
last-index-of. Fail-closed: a non-List value yields `NotAList`; a token that does not match the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); an absent sublist yields
`SublistNotFound` (never conflated with the valid index 0). An independent Python reference
replicates the position rule over 4 test cases.

## Result

- 6 Rust unit tests green (last start index, single match, absent sublist, empty sublist,
  non-list, raw query vs trimmed items).
- Cross-check: 4 test cases (last start index, single match, absent sublist, non-list) driven
  through product runner `p4b_02b129_parameter_list_last_sublist_index_runner`; independent
  Python reference matches 100% on indices and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b129_parameter_list_last_sublist_index.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b129-parameter-list-last-sublist-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b129-parameter-list-last-sublist-index-stage.v1.yaml`; source map
  `p4b-02b129-mit-source-map.v1.yaml`.
- PLAN **P4B-02b129**; ledger note/gate P4B-02; coverage gates 298 -> 299.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Locates sublists on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
