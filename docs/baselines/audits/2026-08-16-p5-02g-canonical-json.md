# P5-02g Canonical Parameter JSON v1 — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02g (canonical parameter JSON v1)
- Status: delivered and mechanically bound; arithmetic default resolution
  and warning contract still pending MATLAB oracle

## Method

Pure reference defaults (`param.X` / `OP.X`) are resolved by identity
lookup over the observed LHS assignment targets, following chains to
literal defaults (depth <= 8, cycle detection). Arithmetic expressions
and cycles are never evaluated; they stay `needs_matlab_oracle`.

## Result

- 30 reference-default calls: 7 resolved to literal values via chains
  (e.g. A_ft -> param.a_fext -> A_fe = 0.5); 23 marked
  needs_matlab_oracle (arithmetic like param.fb/4, 2*param.specBER,
  or chains without a literal end).
- Canonical JSON v1 `p5-r480-canonical-parameter-json.v1.yaml`: 160
  literal + 7 resolved_reference + 23 needs_matlab_oracle + 39 none
  default calls across 214 keys.
- Draft literal classification was corrected this round: MATLAB
  leading-dot literals (.020, .6, .618, .7) were misclassified as
  references; the literal regex now accepts `[+-]?(\d+(\.\d+)?|\.\d+)`.
  Totals updated to 160 literal / 30 reference; 02f assertions synced.

## Binding

- Verifier `verify_p5_02g_canonical_json.py` + 5 tests;
- PLAN **P5-02g**; ledger note/gate; coverage gates 78 -> 79.
