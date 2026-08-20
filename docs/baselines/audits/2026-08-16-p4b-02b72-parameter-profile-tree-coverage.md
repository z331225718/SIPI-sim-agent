# P4B-02b72 Parameter Profile Tree Coverage Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b72 (profile-to-tree leaf coverage report)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_tree_coverage_v1.rs` in `sipi-ami-text`:
`check_parameter_profile_tree_coverage_v1` reports how an assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) covers the leaves of an
`AmiParameterTreeV1`: for every profile name, whether the tree holds exactly one leaf (covered),
more than one leaf at possibly different depths (ambiguous), or no leaf at all (missing). This is
the pre-flight planning report ahead of `apply_parameter_profile_to_tree_v1` (02b69), which fails
closed on the first missing or ambiguous name; this slice surfaces the complete picture up front
without failing. Fail-closed on tree shape: the exhaustive match over the product tree node
variants rejects any other shape; all lists come back in deterministic sorted order. An independent
Python reference replicates the tree build and leaf-name counting over 4 test cases.

## Result

- 6 Rust unit tests green (full coverage, missing names, ambiguous names, empty profile, tree
  without leaves, mixed coverage).
- Cross-check: 4 test cases (full coverage, missing name, ambiguous name, empty profile) driven
  through product runner `p4b_02b72_parameter_profile_tree_coverage_runner`; independent Python
  reference matches 100% on profile_names, covered/ambiguous/missing lists, complete and
  unambiguous flags; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b72_parameter_profile_tree_coverage.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b72-parameter-profile-tree-coverage-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b72-parameter-profile-tree-coverage-stage.v1.yaml`; source map
  `p4b-02b72-mit-source-map.v1.yaml`.
- PLAN **P4B-02b72**; ledger note/gate P4B-02; coverage gates 241 -> 242.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Reports coverage only; does not apply values, does not fail on missing/ambiguous names (02b69
  remains the fail-closed apply gate).
- No release certification, no acceptance evidence.
