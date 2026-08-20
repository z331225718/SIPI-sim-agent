# P4B-02b96 Parameter Profile Canonical Fingerprint Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b96 (FNV-1a 64 fingerprint of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_fingerprint_v1.rs` in `sipi-ami-text`:
`hash_parameter_profile_v1` computes a deterministic 64-bit fingerprint of an assembled parameter
profile (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly): hashes the
canonical compact JSON produced by `serialize_parameter_profile_v1` (02b81, sorted names, raw
value tokens) with the FNV-1a 64-bit algorithm. This is a stable change detection and caching key
for profiles: identical canonical serializations hash identically, any spelling/name/value change
changes the hash, and the algorithm is trivially reproducible in any language. Fail-closed: the
hash is total (no error path); FNV-1a 64 uses wrapping arithmetic with the standard offset basis
(14695981039346656037) and prime (1099511628211); the empty profile hashes the empty object `{}`.
An independent Python reference replicates the serialization and FNV-1a 64 over 4 test cases.

## Result

- 6 Rust unit tests green (deterministic, changes with value, changes with name, order
  independent, empty profile equals hash of `{}`, float spelling changes hash).
- Cross-check: 4 test cases (simple profile, sorted order, empty profile, spelling differs) driven
  through product runner `p4b_02b96_parameter_profile_fingerprint_runner`; independent Python
  reference matches 100% on the exact 64-bit hashes; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b96_parameter_profile_fingerprint.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b96-parameter-profile-fingerprint-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b96-parameter-profile-fingerprint-stage.v1.yaml`; source map
  `p4b-02b96-mit-source-map.v1.yaml`.
- PLAN **P4B-02b96**; ledger note/gate P4B-02; coverage gates 265 -> 266.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Fingerprints the 02b81 canonical serialization only; raw tokens hashed as-is.
- No release certification, no acceptance evidence.
