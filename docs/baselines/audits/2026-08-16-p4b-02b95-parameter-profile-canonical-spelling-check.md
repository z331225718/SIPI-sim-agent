# P4B-02b95 Parameter Profile Canonical Spelling Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b95 (canonical profile spelling check of assembled parameter profiles)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_canonical_spelling_check_v1.rs` in `sipi-ami-text`:
`check_parameter_profile_spellings_canonical_v1` checks whether every entry of an assembled
parameter profile (`BTreeMap<String, AmiParameterValueV1>`, e.g. produced by 02b44 assembly)
already carries its canonical value spelling (`canonicalize_parameter_value_spelling_v1`, 02b75):
compares each entry's raw value token to its canonical spelling (Integer `007` -> `7`, List
`(a,b,c)` -> `(a, b, c)`; Float and String stay raw and are never flagged) and reports each
non-canonical entry with its name, declared type, raw value, and canonical value. This is the
profile-level companion of 02b77 profile canonicalization (which rewrites) and the parallel of
02b94's tree leaf check: the gate before canonicalizing a profile. Fail-closed: the check is total
(no error path); issues come back in deterministic sorted (name) order; `canonical()` is true
exactly when no non-canonical entry was found. An independent Python reference replicates the
check over 4 test cases.

## Result

- 6 Rust unit tests green (canonical profile, non-canonical integer, non-canonical list, float and
  string never flagged, empty profile, mixed).
- Cross-check: 4 test cases (canonical profile, non-canonical integer, non-canonical list, empty
  profile) driven through product runner `p4b_02b95_parameter_profile_canonical_spelling_check_runner`;
  independent Python reference matches 100% on entry counts, canonical flags, and issue lists;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b95_parameter_profile_canonical_spelling_check.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b95-parameter-profile-canonical-spelling-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b95-parameter-profile-canonical-spelling-check-stage.v1.yaml`; source map
  `p4b-02b95-mit-source-map.v1.yaml`.
- PLAN **P4B-02b95**; ledger note/gate P4B-02; coverage gates 264 -> 265.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks canonical spelling of validated profile entries only; Float/String never flagged.
- No release certification, no acceptance evidence.
