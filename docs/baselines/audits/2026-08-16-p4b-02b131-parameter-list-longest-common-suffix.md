# P4B-02b131 Parameter List Longest Common Suffix Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b131 (list-value common suffix on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_common_suffix_v1.rs` in `sipi-ami-text`:
`list_longest_common_suffix_v1` computes the longest common suffix of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the canonical list token of the longest trailing run of trimmed items equal
element-wise between the two values, read from their ends toward their starts (raw byte
equality, per the P4B-02b0 raw-byte binding). An empty common suffix yields the structurally
empty token `()` (not a valid 02b1 List value; the operation is total on the token level and
does not re-validate, mirroring 02b100 sole-item removal). This is the end-aligned mirror of
02b130 longest-common-prefix and the list-value companion of 02b67 tree-path prefix relations.
Fail-closed: either value not declared List yields `NotAList`; either token not matching the
List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the suffix rule over 4 test cases.

## Result

- 6 Rust unit tests green (common suffix, one is suffix of other, empty suffix, equal values,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (common suffix, one is suffix, empty suffix, non-list) driven
  through product runner `p4b_02b131_parameter_list_longest_common_suffix_runner`; independent
  Python reference matches 100% on tokens and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b131_parameter_list_longest_common_suffix.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b131-parameter-list-longest-common-suffix-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b131-parameter-list-longest-common-suffix-stage.v1.yaml`; source map
  `p4b-02b131-mit-source-map.v1.yaml`.
- PLAN **P4B-02b131**; ledger note/gate P4B-02; coverage gates 300 -> 301.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes suffixes on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
