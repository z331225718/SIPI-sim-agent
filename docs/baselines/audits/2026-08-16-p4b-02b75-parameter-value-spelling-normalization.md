# P4B-02b75 Parameter Value Spelling Normalization Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b75 (canonical non-float spelling of validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_value_spelling_normalization_v1.rs` in `sipi-ami-text`:
`canonicalize_parameter_value_spelling_v1` produces the deterministic canonical spelling of a
validated `AmiParameterValueV1` value token for the types where a canonical form is well-defined
without float formatting hazards: Integer renders the parsed i64 in decimal (`007` -> `7`,
`-0` -> `0`); List trims items and joins them with `", "` inside the parens (`(a,b,c)` ->
`(a, b, c)`), mirroring the P4B-02b1 list item rule; Boolean is already canonical; Float and
String stay raw (no normalization, per the P4B-02b0 raw-byte binding; float formatting explicitly
out of scope). This is the canonical-string companion of 02b70 typed equivalence (a boolean
predicate) for callers needing a stable spelling key for non-float values. Fail-closed: inputs are
validated values, so Integer/List parses cannot fail; a defensive fallback returns the raw token
rather than panicking. An independent Python reference replicates the canonical rules over 4 test
cases.

## Result

- 6 Rust unit tests green (integer decimal normalization, list item spacing normalization, boolean
  canonical, float raw, string raw, idempotence for non-float types).
- Cross-check: 4 test cases (integer normalization, list normalization, float raw, string raw)
  driven through product runner `p4b_02b75_parameter_value_spelling_normalization_runner`;
  independent Python reference matches 100% on canonical spellings; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b75_parameter_value_spelling_normalization.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b75-parameter-value-spelling-normalization-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b75-parameter-value-spelling-normalization-stage.v1.yaml`; source map
  `p4b-02b75-mit-source-map.v1.yaml`.
- PLAN **P4B-02b75**; ledger note/gate P4B-02; coverage gates 244 -> 245.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Normalizes Integer/List only; Float and String stay raw (no float formatting, no String trimming).
- No release certification, no acceptance evidence.
