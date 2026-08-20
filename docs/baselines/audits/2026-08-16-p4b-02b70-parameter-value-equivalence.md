# P4B-02b70 Parameter Value Semantic Equivalence Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b70 (typed semantic equality of validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_value_equivalence_v1.rs` in `sipi-ami-text`: `parameter_values_equivalent_v1`
compares two validated `AmiParameterValueV1` values by declared type and parsed typed value rather
than raw token spelling — the typed equality layer beneath profile diff/merge (02b47/02b48) and
duplicate consistency (02b54), which compare raw tokens. Numeric spellings that parse to the same
value (`0.5` vs `0.50`, `007` vs `7`, `1e0` vs `1.0`) are Equivalent; List compares trimmed item
sequences (`(a, b, c)` vs `(a,b,c)`); String keeps raw byte equality (P4B-02b0 raw-byte binding).
Fail-closed: cross-type values are never equivalent; Float/Integer compare on parsed finite values
(IEEE equality, so `0.0` and `-0.0` are equivalent); Boolean compares the exact `True`/`False` token;
List compares item-by-item with index reporting; any unparseable token yields `MalformedValue`
(unreachable for values built via `AmiParameterValueV1::try_new`, kept fail-closed instead of
panicking). An independent Python reference replicates the typed comparison over 4 test cases.

## Result

- 6 Rust unit tests green (float/integer spelling equivalence, raw string binding, list spacing
  equivalence, typed-value mismatch reasons, cross-type rejection).
- Cross-check: 4 test cases (float spelling, integer spelling, list spacing, cross type) driven
  through product runner `p4b_02b70_parameter_value_equivalence_runner`; independent Python
  reference matches 100% on equivalent flags and reason keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b70_parameter_value_equivalence.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b70-parameter-value-equivalence-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b70-parameter-value-equivalence-stage.v1.yaml`; source map
  `p4b-02b70-mit-source-map.v1.yaml`.
- PLAN **P4B-02b70**; ledger note/gate P4B-02; coverage gates 239 -> 240.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Compares validated typed values only; parameter names are identity and excluded from value
  equivalence (callers compare names at the profile-map level, as in 02b47).
- No release certification, no acceptance evidence.
