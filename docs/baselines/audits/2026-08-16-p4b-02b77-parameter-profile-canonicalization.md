# P4B-02b77 Parameter Profile Canonicalization Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b77 (canonical spelling of every entry of an assembled parameter profile)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_canonicalization_v1.rs` in `sipi-ami-text`:
`canonicalize_parameter_profile_v1` produces the canonical form of an assembled parameter profile
(`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly) by applying
`canonicalize_parameter_value_spelling_v1` (02b75) to every entry: Integer spellings become the
parsed i64 in decimal (`007` -> `7`), List spellings get trimmed items joined with `", "`
(`(a,b,c)` -> `(a, b, c)`), and Boolean/Float/String stay raw. This is the profile-map-level
companion of 02b75: a stable spelling key for a whole profile without float formatting.
Fail-closed: canonical spellings are rebuilt through `AmiParameterValueV1::try_new` (always valid
for canonical Integer/List forms); a defensive fallback keeps the original entry rather than
panicking; the canonicalized count reports how many entries changed; canonicalization is idempotent.
An independent Python reference replicates the canonical rules over 4 test cases.

## Result

- 6 Rust unit tests green (integer canonicalization, list canonicalization, raw float/string/
  boolean, canonicalized count, empty profile, idempotence).
- Cross-check: 4 test cases (integer+list, raw types, already canonical, empty profile) driven
  through product runner `p4b_02b77_parameter_profile_canonicalization_runner`; independent Python
  reference matches 100% on entries/canonicalized counts and canonical maps; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b77_parameter_profile_canonicalization.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b77-parameter-profile-canonicalization-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b77-parameter-profile-canonicalization-stage.v1.yaml`; source map
  `p4b-02b77-mit-source-map.v1.yaml`.
- PLAN **P4B-02b77**; ledger note/gate P4B-02; coverage gates 246 -> 247.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Canonicalizes Integer/List spellings only; Float and String stay raw (no float formatting).
- No release certification, no acceptance evidence.
