# P4B-02b165 Parameter List Mode Items Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b165 (value-level multi-mode on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_mode_items_v1.rs` in `sipi-ami-text`:
`parameter_list_mode_items_v1` returns the canonical list token of the distinct trimmed
items whose occurrence count equals the maximum count (raw byte equality, per the P4B-02b0
raw-byte binding) of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1
list rule (`(item, item, ...)`, items trimmed, non-empty), ordered by first occurrence in
the value's trimmed item sequence. The list is non-empty by rule so at least one mode always
exists; a list where every item is distinct has all items as modes. This is the multi-mode
companion of 02b122 most-frequent (a single arbitrary tie-winner) and of 02b121 frequency
(the modes are the items at maximum count). Fail-closed: the value not declared List yields
`NotAList`; the token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the mode rule over 4 test cases.

## Result

- 6 Rust unit tests green (single mode, multiple modes, all distinct, single item, spacing
  canonicalized, non-list).
- Cross-check: 4 test cases (single mode, multiple modes, all distinct, non-list) driven
  through product runner `p4b_02b165_parameter_list_mode_items_runner`; independent Python
  reference matches 100% on canonical tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b165_parameter_list_mode_items.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b165-parameter-list-mode-items-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b165-parameter-list-mode-items-stage.v1.yaml`; source map
  `p4b-02b165-mit-source-map.v1.yaml`.
- PLAN **P4B-02b165**; ledger note/gate P4B-02; coverage gates 334 -> 335.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes mode items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
