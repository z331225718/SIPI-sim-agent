# P4B-02b2 Typed Parameter Form Identity Binding — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b2 (identity binding between typed triples and
  structural forms)
- Status: delivered and mechanically bound; P4B-02 main item stays open
  (catalog/defaults semantics pending profile)

## Deliverable

`crates/sipi-ami-text/src/parameter_form_binding_v1.rs` (wired into
`sipi-ami-text`, re-exported):

- `bind_parameter_value_v1(binding, form_index, value)` — verifies
  byte-exact identity between a caller-selected structural form and a
  caller-declared typed (name, type token, value token) triple:
  - form index must be in range (`FormIndexOutOfRange`);
  - the form must have exactly three items (`FormNotThreeItems`);
  - every item must be an atom or quoted token, not a nested list
    (`FormItemIsNestedList`);
  - item spellings must equal the triple's name, type token, and value
    token respectively (`NameSpellingMismatch` /
    `TypeTokenSpellingMismatch` / `ValueTokenSpellingMismatch`).
- `PARAMETER_FORM_BINDING_POLICY_V1` — fixed policy string
  `sipi.p4b-02b2.parameter-form-binding-v1.identity-only`.

## Scope discipline

- Identity only: the API never interprets a form as a parameter, never
  recognizes two-item forms, carries no catalog/reserved names/defaults,
  and never interprets a whole document.
- Composes with 02b1 (`AmiParameterValueV1` typed validation) and 02b0
  (raw-byte binding); the three slices form the parameter identity/
  validation surface of P4B-02.
- P4B-02 main item remains open: catalog/defaults semantics still pending
  profile; blocker class unchanged.

## Mechanical binding

- Charter `docs/baselines/p4b-02b2-parameter-form-binding.v1.yaml` (schema
  `sipi.p4b-02b2.parameter-form-binding.v1`).
- Verifier `tools/verify_p4b_02b2_parameter_form_binding.py` cross-binds
  charter fields (identity rules, scope policy, implementation, admission,
  non_claims) against the Rust source tokens and the PLAN `**P4B-02b2`
  row; any drift fails closed.
- Tests `tools/test_verify_p4b_02b2_parameter_form_binding.py`: 7 tests.
- Rust unit tests in `parameter_form_binding_v1.rs`: exact binding, out of
  range, two-item forms, nested list, spelling mismatches, invalid triple
  pre-flight, fixed policy string. `cargo test -p sipi-ami-text`: 16
  passed, 0 failed.

## Non-claims (unchanged for P4B-02 main item)

not_parameter_grammar; not_ibis_ami_catalog; not_reserved_names;
not_defaults; not_document_wide_interpretation; not_profile_acceptance.
