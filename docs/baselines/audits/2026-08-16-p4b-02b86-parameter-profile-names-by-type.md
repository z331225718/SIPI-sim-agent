# P4B-02b86 Parameter Profile Names-By-Type Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b86 (name listing by declared type in assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_names_by_type_v1.rs` in `sipi-ami-text`:
`list_parameter_profile_names_by_type_v1` lists every name in an assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) whose entry carries a
given declared type token: returns the sorted names for Float, Integer, Boolean, String, or List.
This is the name-list companion of 02b73 type statistics (which counts entries by type) and of
02b80 value lookup (which finds names by typed value). Fail-closed: a type token that is not one of
the five product variants yields `UnknownTypeToken`; names come back in deterministic sorted order
(BTreeMap iteration); an empty profile or a type with no matches yields an empty list. An
independent Python reference replicates the listing over 4 test cases.

## Result

- 6 Rust unit tests green (float names, sorted integer names, no matches, unknown type, boolean/
  string/list names, empty profile).
- Cross-check: 4 test cases (float names, integer names, no match, unknown type) driven through
  product runner `p4b_02b86_parameter_profile_names_by_type_runner`; independent Python reference
  matches 100% on sorted name lists and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b86_parameter_profile_names_by_type.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b86-parameter-profile-names-by-type-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b86-parameter-profile-names-by-type-stage.v1.yaml`; source map
  `p4b-02b86-mit-source-map.v1.yaml`.
- PLAN **P4B-02b86**; ledger note/gate P4B-02; coverage gates 255 -> 256.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Lists names by declared type on validated profiles only; unknown type tokens fail closed.
- No release certification, no acceptance evidence.
