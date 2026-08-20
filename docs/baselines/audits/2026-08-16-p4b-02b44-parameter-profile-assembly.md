# P4B-02b44 AMI Parameter Profile Assembly Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b44 (strict parameter profile assembly)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_profile_assembly_v1.rs` in `sipi-ami-text`: `assemble_parameter_profile_v1`
assembles a strict parameter profile from a tree list, a defaults map, and a reserved-name set in
one fail-closed pass:
1. multi-tree typed-form extraction merged by name (P4B-02b42, reused verbatim; errors wrapped as
   `Extraction(...)`);
2. typed defaults fill for names missing from the merged map — each default must be an AMI form
   `[type, value]` validated per P4B-02b1 `AmiParameterValueV1::try_new` (`DefaultNotTypedForm` /
   `InvalidDefaultValue`); names already present are skipped (counted);
3. strict rejection of any assembled name in the reserved set (`ReservedNameUsed`), with an empty
   reserved set rejected as a caller error (`EmptyReservedSet`).
An empty defaults map is allowed (no filling). An independent Python reference replicates the
tokenize/build/extract/fill/reject pipeline over 4 test cases.

## Result

- 8 Rust unit tests green (full assembly; default skipped when present; malformed default tokens;
  invalid default value; reserved name used; empty reserved set; extraction error wrapped;
  empty defaults allowed).
- Cross-check: 4 test cases (assemble full, reserved used, malformed default, empty reserved)
  driven through product runner `p4b_02b44_parameter_profile_assembly_runner`; independent Python
  reference matches 100% on valid flags, counts, assembled parameter maps, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b44_parameter_profile_assembly.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b44-parameter-profile-assembly-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b44-parameter-profile-assembly-stage.v1.yaml`; source map
  `p4b-02b44-mit-source-map.v1.yaml`.
- PLAN **P4B-02b44**; ledger note/gate P4B-02; coverage gates 210 -> 211.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog (mechanism only), no document decoding.
- Assembly does not know the required parameter set; required-name checking lives in the P4B-02b3
  catalog layer.
- No release certification, no acceptance evidence.
