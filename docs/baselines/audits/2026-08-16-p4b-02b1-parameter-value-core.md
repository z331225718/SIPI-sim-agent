# P4B-02b1 Typed .ami Parameter Value Validation Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b1 (typed parameter value validation)
- Status: delivered and mechanically bound; P4B-02 main item stays open
  (catalog/defaults semantics pending profile)

## Deliverable

`crates/sipi-ami-text/src/parameter_value_v1.rs` (wired into `sipi-ami-text`,
re-exported):

- `AmiParameterTypeV1` — exact type tokens Float/Integer/Boolean/String/List.
- `AmiParameterValueV1::try_new` — validates one caller-supplied
  (name, type_token, value_token) triple against explicit product-owned
  syntax rules:
  - name: non-empty ASCII `[A-Za-z_][A-Za-z0-9_]*`;
  - type token: exact match of the five tokens;
  - value per type: Float parses as finite f64; Integer parses as i64;
    Boolean is exactly True/False; String is non-empty; List is
    `(item, item, ...)` with non-empty trimmed items.
- `PARAMETER_VALUE_POLICY_V1` — fixed policy string
  `sipi.p4b-02b1.parameter-value-v1.syntax-only-no-catalog-no-defaults`.

## Scope discipline

- Syntax-only: no reserved-name catalog, no default inference, no
  document decoding, no model-specific semantics, no IBIS-AMI parameter
  catalog coverage claim.
- Connection to the raw-byte binding (`parse_and_bind_v1`/`verify_binding_v1`,
  delivered 02b0) is explicitly `pending_later_slice`.
- P4B-02 main item remains open: catalog/defaults semantics still pending
  profile; blocker class unchanged.

## Mechanical binding

- Charter `docs/baselines/p4b-02b1-parameter-value-core.v1.yaml` (schema
  `sipi.p4b-02b1.parameter-value-core.v1`).
- Verifier `tools/verify_p4b_02b1_parameter_value_core.py` cross-binds
  charter fields (name rule, type tokens, value rules, scope policy,
  implementation, admission, non_claims) against the Rust source tokens
  and the PLAN `**P4B-02b1` row; any drift fails closed.
- Tests `tools/test_verify_p4b_02b1_parameter_value_core.py`: 7 tests.
- Rust unit tests in `parameter_value_v1.rs`: accepted types, invalid
  names, unknown type, per-type invalid values, fixed policy string.
  `cargo test -p sipi-ami-text`: all passed.

## Non-claims (unchanged for P4B-02 main item)

not_ibis_ami_catalog; not_reserved_names; not_defaults;
not_model_specific_semantics; not_document_decoding; not_profile_acceptance.
