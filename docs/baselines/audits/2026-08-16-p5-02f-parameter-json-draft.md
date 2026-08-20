# P5-02f Canonical Parameter JSON Draft — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02f (canonical parameter JSON draft)
- Status: delivered and mechanically bound; reference-default resolution
  and warning contract still pending MATLAB oracle

## Method

External-only classification of every observed xls_parameter call:
required flag (true/false/absent) and default expression category
(literal: number/boolean/matrix; reference: param.*/OP.*; none;
unclassified). Expressions are classified, never evaluated.

## Result

- 214 keys, 229 calls; 154 literal-default calls, 36 reference-default
  calls.
- Draft `docs/baselines/p5-r480-canonical-parameter-json-draft.v1.yaml`
  hash-bound to the reference source (642b2891...).
- Reference defaults (e.g. A_ft -> param.a_fext) stay unresolved for the
  MATLAB oracle slice.

## Binding

- Verifier `verify_p5_02f_parameter_json_draft.py` + 5 tests;
- PLAN **P5-02f**; ledger note/gate; coverage gates 77 -> 78.
