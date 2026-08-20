# P5-02j Value Consumption / Default Resolution (scalar catalog) — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02j (scalar default-rule resolution, _resolve_default port)
- Status: delivered and cross-checked against the agent-com Python oracle
  (_resolve_default + literals._scalar); multi-element vector/matrix default
  layout and the caller-dependent default / warning contract remain separate
  scopes.

## Method

Port agent-com config/materialize.py _resolve_default and config/literals.py
_scalar/_evaluate into sipi-com value_consumption_v1.rs:
- DFE lower-limit special case (-1*param.bmax(2:param.ndfe));
- booleans, single-quoted string literals, [] empty literal;
- direct param.X / OP.X reference lookup;
- scalar-reference substitution then scalar-arithmetic evaluation
  (recursive-descent + - * / ^, unary +/- , parenthesised subexpressions,
  Inf/NaN constants).
An external-custody cross-check binds the product resolver to the oracle
through 20 real default expressions drawn from the canonical R480 parameter
reference. Scalar catalog only.

## Result

- 20/20 default expressions matched (_resolve_default hash-bound, tolerance
  1e-12): scalar literals, derived arithmetic (param.fb/4,
  param.max_start_freq/1e9, param.T_O/param.Qr/1000), direct references
  (param.fb, param.a_fext, param.ndfe), booleans, strings 'MM'/'A_DD',
  [] / '' and the DFE lower-limit special case.
- Multi-element array/matrix defaults ([1 3 2 4], [50,50], [0 0],
  string-matrix pkg_Z_c) asserted by the oracle to be multi-element arrays
  and excluded from the scalar comparison (fail-closed, no silent drop).
- sipi-com unit suite 144 tests green (includes the 7 value-consumption
  tests) plus the P5-02j external runner.

## Binding

- Verifier verify_p5_02j_value_consumption.py + 6 tests; crosscheck evidence
  docs/baselines/p5-02j-default-resolution-crosscheck-evidence.v1.yaml.
- Charter p5-02j-default-resolution-stage.v1.yaml; source map
  p5-02j-mit-source-map.v1.yaml.
- PLAN **P5-02j**; ledger note/gate; coverage gates 87 -> 88.
