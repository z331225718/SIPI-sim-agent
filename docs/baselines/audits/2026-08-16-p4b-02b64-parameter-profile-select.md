# P4B-02b64 Parameter Profile Selection Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b64 (name-set sub-profile selection)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_select_v1.rs` in `sipi-ami-text`: `select_parameter_profile_v1`
selects a sub-profile from an assembled parameter map (leaf name -> `AmiParameterValueV1`, e.g.
produced by P4B-02b44) by a caller-supplied name set — the profile consumption step (pick which
parameters to pass on). Fail-closed: an empty selection (`EmptySelection`) and any requested name
absent from the map (`MissingParameter`) are strictly rejected. An independent Python reference
replicates the name-set selection over 4 test cases.

## Result

- 4 Rust unit tests green (subset selection; selecting all returns identical map; empty selection;
  missing parameter).
- Cross-check: 4 test cases (select subset, select all, missing parameter, empty selection) driven
  through product runner `p4b_02b64_parameter_profile_select_runner`; independent Python reference
  matches 100% on valid flags, counts, selected maps, and error contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b64_parameter_profile_select.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b64-parameter-profile-select-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b64-parameter-profile-select-stage.v1.yaml`; source map
  `p4b-02b64-mit-source-map.v1.yaml`.
- PLAN **P4B-02b64**; ledger note/gate P4B-02; coverage gates 233 -> 234.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Selection by name only; values are carried as-is.
- No release certification, no acceptance evidence.
