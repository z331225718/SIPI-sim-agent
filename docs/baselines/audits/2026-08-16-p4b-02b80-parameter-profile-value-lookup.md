# P4B-02b80 Parameter Profile Value Lookup Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b80 (typed value reverse lookup in assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_value_lookup_v1.rs` in `sipi-ami-text`:
`find_parameter_profile_names_by_value_v1` finds every name in an assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) whose entry is
typed-equivalent to a caller-supplied query value under `parameter_values_equivalent_v1` (02b70):
the reverse direction of 02b69 profile apply (name -> value), value -> names, useful for detecting
semantically duplicate entries regardless of spelling (`0.5` vs `0.50`). The query name is
identity-only and never matched (names are compared at the map-key level elsewhere, as in
02b47/02b71). Fail-closed: a query that fails `AmiParameterValueV1::try_new` (02b1) yields
`InvalidQueryValue`; matches come back in deterministic sorted order (BTreeMap iteration). An
independent Python reference replicates the typed matching over 4 test cases.

## Result

- 6 Rust unit tests green (matching float spelling, no match, multiple matches sorted, cross-type
  never matches, invalid query fail-closed, empty profile).
- Cross-check: 4 test cases (match found, no match, multiple matches, invalid query) driven
  through product runner `p4b_02b80_parameter_profile_value_lookup_runner`; independent Python
  reference matches 100% on valid flags, sorted match lists, and error presence; 4/4
  product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b80_parameter_profile_value_lookup.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b80-parameter-profile-value-lookup-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b80-parameter-profile-value-lookup-stage.v1.yaml`; source map
  `p4b-02b80-mit-source-map.v1.yaml`.
- PLAN **P4B-02b80**; ledger note/gate P4B-02; coverage gates 249 -> 250.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Looks up validated typed profiles only; query name is identity-only; invalid queries fail closed.
- No release certification, no acceptance evidence.
