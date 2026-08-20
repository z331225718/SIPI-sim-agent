# P4B-02b28 AMI Parameter Tree Path Toposort Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b28 (AMI parameter tree topological path ordering core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_toposort_v1.rs` in `sipi-ami-text`: `toposort_parameter_tree_paths_v1`
produces a deterministic topological ordering of canonical node paths inside a typed `AmiParameterTreeV1` hierarchy (P4B-02b7),
parents always before children, siblings in sorted key order (BTreeMap iteration order).
Fail-closed: empty tree lists (`EmptyTreeList`) are strictly rejected.
An independent Python reference recomputes the path toposort over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; parents precede children; single node paths).
- Cross-check: 3 test cases (nested toposort, single node toposort, wide toposort)
  driven through product runner `p4b_02b28_parameter_tree_toposort_runner`; independent Python reference
  matches 100% on valid flags, path counts, and ordered path lists; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b28_parameter_tree_toposort.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b28-parameter-tree-toposort-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b28-parameter-tree-toposort-stage.v1.yaml`; source map
  `p4b-02b28-mit-source-map.v1.yaml`.
- PLAN **P4B-02b28**; ledger note/gate P4B-02; coverage gates 194 -> 195.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
