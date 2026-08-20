# P5-02h Canonical Parameter JSON v2 — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02h (bounded static arithmetic on defaults)
- Status: delivered and mechanically bound; caller-dependent defaults and
  warning contract remain for MATLAB oracle / caller config

## Method

Documented evaluation grammar: numbers (IEEE doubles, MATLAB leading-dot
literals), operators + - * /, parentheses, references param.X / OP.X
resolved to canonical values (literal or resolved chain); functions
forbidden; depth <= 8; NaN/inf rejected.

## Result

- 3 expressions statically evaluated: N_tc = param.trunc = 128.0;
  T_h = param.T_O = 0.0; QL = param.T_O/param.Qr/1000 = 0.0.
- 20 calls (11 unique expressions) stay needs_matlab_oracle: their
  operands (param.fb, param.ndfe, param.specBER, param.max_start_freq,
  OP.GET_FD, OP.PMD_type, OP.TDMODE) have no canonical default - these
  defaults depend on caller configuration or MATLAB-internal state.
- Canonical JSON v2 `p5-r480-canonical-parameter-json.v2.yaml`: 160
  literal + 7 resolved_reference + 3 statically_evaluated + 20
  needs_matlab_oracle + 39 none across 214 keys.

## Binding

- Verifier `verify_p5_02h_canonical_json_v2.py` + 5 tests (evaluated
  values asserted);
- PLAN **P5-02h**; ledger note/gate; coverage gates 79 -> 80.
