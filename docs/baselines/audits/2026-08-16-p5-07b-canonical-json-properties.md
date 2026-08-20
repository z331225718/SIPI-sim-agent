# P5-07b Canonical JSON Property Surface — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-07 sub-slice 07b (mechanical property checks over canonical
  JSON v2)
- Status: delivered and mechanically bound; negative fixtures pending

## Method

Property checks over all 229 xls_parameter calls in the canonical JSON
v2, independent of MATLAB: allowed kinds; literal defaults finite
(numbers) or well-formed (booleans/matrices); string literals quoted;
inf literals exactly inf/+inf/-inf; required flags in true/false/absent;
resolved references carry values and chains; needs-oracle entries carry
expressions.

## Result

- 0 failures across 229 calls after classifier corrections.
- The property pass found and fixed four real classifier defects:
  1. MATLAB string-literal defaults ('MM', '' etc.) were unclassified;
  2. inf defaults (EH_max -> inf) were unclassified;
  3. bare-default variant xls_parameter(KEY, VALUE) (e.g. M -> 32) was
     misread as required flag;
  4. comma inside matrix brackets ([50,50]) split arguments wrongly.
  The full chain 02f -> 02g -> 02h was rerun; literal count updated
  160 -> 163 (2 bare defaults + [50,50]); assertions synced.

## Scope discipline

No compare, no MATLAB cross-check; the property surface is the
anti-single-truth quality gate for the oracle-derived reference.

## Binding

- Surface `p5-07-canonical-json-property-surface.v1.yaml`;
- Verifier `verify_p5_07b_canonical_json_properties.py` + 5 tests;
- PLAN **P5-07b**; ledger note/gate; coverage gates 87 -> 88.
