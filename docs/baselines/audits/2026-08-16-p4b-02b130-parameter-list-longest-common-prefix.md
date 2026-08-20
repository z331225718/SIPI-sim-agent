# P4B-02b130 Parameter List Longest Common Prefix Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b130 (list-value common prefix on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_common_prefix_v1.rs` in `sipi-ami-text`:
`list_longest_common_prefix_v1` computes the longest common prefix of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token of the longest initial run of trimmed items equal
element-wise between the two values (raw byte equality, per the P4B-02b0 raw-byte binding). An
empty common prefix yields the structurally empty token `()` (not a valid 02b1 List value; the
operation is total on the token level and does not re-validate, mirroring 02b100 sole-item
removal). This is the list-value companion of 02b67 tree-path longest-common-prefix and of 02b106
join. Fail-closed: either value not declared List yields `NotAList`; either token not matching
the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the prefix rule over 4 test cases.

## Result

- 6 Rust unit tests green (common prefix, one is prefix of other, empty prefix, equal values,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (common prefix, one is prefix, empty prefix, non-list) driven
  through product runner `p4b_02b130_parameter_list_longest_common_prefix_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b130_parameter_list_longest_common_prefix.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b130-parameter-list-longest-common-prefix-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b130-parameter-list-longest-common-prefix-stage.v1.yaml`; source map
  `p4b-02b130-mit-source-map.v1.yaml`.
- PLAN **P4B-02b130**; ledger note/gate P4B-02; coverage gates 299 -> 300.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes prefixes on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
