# P4B-02b45 AMI Parameter Tree Path-String Parsing Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b45 (dotted path-string parsing)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_path_string_v1.rs` in `sipi-ami-text`: `parse_parameter_tree_path_string_v1`
parses a dotted path string (`"root.sub.deep"`) into path segments, the input form accepted by the
path-addressed tree APIs (P4B-02b8 query, P4B-02b23 subtree, P4B-02b26 compose, P4B-02b27 replace,
P4B-02b39 set). Raw bytes are preserved: segments are not trimmed and are not validated as
identifiers (resolution is the downstream APIs' job). Fail-closed: an empty path string
(`EmptyPath`) and any empty segment from leading, trailing, or doubled dots (`EmptySegment`) are
strictly rejected. An independent Python reference replicates the split rules over 4 test cases.

## Result

- 8 Rust unit tests green (basic path; single segment; empty path; leading dot; trailing dot;
  double dot; dots only; raw segments preserved).
- Cross-check: 4 test cases (basic, deep, empty path, double dot) driven through product runner
  `p4b_02b45_parameter_tree_path_string_runner`; independent Python reference matches 100% on
  valid flags, segment lists, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b45_parameter_tree_path_string.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b45-parameter-tree-path-string-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b45-parameter-tree-path-string-stage.v1.yaml`; source map
  `p4b-02b45-mit-source-map.v1.yaml`.
- PLAN **P4B-02b45**; ledger note/gate P4B-02; coverage gates 211 -> 212.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Parse-only: no resolution against a tree, no identifier validation.
- No release certification, no acceptance evidence.
