# P4B-02b53 AMI Parameter Tree Batch Value Set Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b53 (name-addressed batch value set for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_set_values_batch_v1.rs` in `sipi-ami-text`:
`set_parameter_tree_leaf_values_v1` sets the value tokens of every leaf addressed by name per a
caller-supplied updates map (leaf name -> single value token), each token validated against the
leaf's declared type (caller-supplied type map keyed by leaf name) via the exact P4B-02b1
`AmiParameterValueV1::try_new` rules before any mutation. Returns a new tree and the number of leaf
occurrences updated. Fail-closed: empty updates (`EmptyUpdates`), a name with no leaf
(`MissingLeaf`), a name matching leaves at multiple depths (`AmbiguousName`), a missing type
(`MissingType`), an invalid value (`InvalidValue` wrapping the P4B-02b1 error), and an invalid leaf
name (`InvalidLeafName`) are strictly rejected. An independent Python reference replicates the
tokenize/build/count/validate/apply pipeline over 4 test cases.

## Result

- 6 Rust unit tests green (batch updates; ambiguous name; missing leaf; empty updates; missing
  type; invalid value).
- Cross-check: 4 test cases (batch update, ambiguous name, missing leaf, invalid value) driven
  through product runner `p4b_02b53_parameter_tree_batch_value_set_runner`; independent Python
  reference matches 100% on valid flags, updated counts, resulting tree structures, and error
  contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b53_parameter_tree_batch_value_set.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b53-parameter-tree-batch-value-set-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b53-parameter-tree-batch-value-set-stage.v1.yaml`; source map
  `p4b-02b53-mit-source-map.v1.yaml`.
- PLAN **P4B-02b53**; ledger note/gate P4B-02; coverage gates 219 -> 220.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Addresses leaves by name; ambiguous (multi-depth) names are rejected rather than partially
  updated.
- No release certification, no acceptance evidence.
