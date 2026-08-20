# P4B-02b97 Parameter Tree Typed-Leaf Fingerprint Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b97 (FNV-1a 64 fingerprint of typed-form leaf content)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_typed_leaf_fingerprint_v1.rs` in `sipi-ami-text`:
`fingerprint_parameter_tree_typed_leaves_v1` computes a deterministic 64-bit fingerprint of the
typed-form leaf content of an `AmiParameterTreeV1`: walks every leaf, collects the canonical path
-> (declared type token, raw value token) of every typed-form leaf (exactly two value tokens whose
first token is a known type token Float/Integer/Boolean/String/List; value validity is not checked
— the declared content is fingerprinted as-is), serializes the sorted map to compact JSON, and
applies FNV-1a 64. This is the tree-level change detection fingerprint over declared typed content
(paths, types, and raw values), the companion of 02b96's profile fingerprint; non-typed leaves are
skipped and do not affect the hash. Fail-closed: the fingerprint is total (no error path); FNV-1a
64 uses wrapping arithmetic with the standard offset basis (14695981039346656037) and prime
(1099511628211); a tree with no typed-form leaves hashes the empty object `{}`. An independent
Python reference replicates the collection, serialization, and FNV-1a 64 over 4 test cases.

## Result

- 6 Rust unit tests green (deterministic, changes with value, changes with type, changes with
  path, skipped leaves ignored, no typed leaves hashes `{}`).
- Cross-check: 4 test cases (typed leaves, change value, skipped ignored, no typed) driven through
  product runner `p4b_02b97_parameter_tree_typed_leaf_fingerprint_runner`; independent Python
  reference matches 100% on the exact 64-bit hashes; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b97_parameter_tree_typed_leaf_fingerprint.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b97-parameter-tree-typed-leaf-fingerprint-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b97-parameter-tree-typed-leaf-fingerprint-stage.v1.yaml`; source map
  `p4b-02b97-mit-source-map.v1.yaml`.
- PLAN **P4B-02b97**; ledger note/gate P4B-02; coverage gates 266 -> 267.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Fingerprints typed-form leaf content only; non-typed leaves skipped; raw tokens hashed as-is.
- No release certification, no acceptance evidence.
