# P5-05e COM Typed Parameter DTO Merge Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-05 sub-slice 05e (COM typed parameter DTO merge core)
- Status: delivered and cross-checked against an independent reference.
  Combines the P5-05d workbook surface with P5-02j/k resolved defaults.

## Method

Implement merge_com_parameters_v1 in sipi-com com_parameters_v1.rs: for each
consumed key, choose the workbook value if present, else the resolved default,
else a hard MissingValue error; retain unconsumed keys. Reuse ResolvedDefaultV1
from P5-02j/k. A cross-check compares the product merge against an independent
Python reference on fb/a_fext/ndfe + an unconsumed key.

## Result

- 1/1 matched_hash_bound: fb uses workbook value, a_fext and ndfe use defaults,
  unconsumed retained.
- sipi-com unit suite 165 tests green (7 new com_parameters tests).

## Binding

- Verifier verify_p5_05e_com_parameters.py + 6 tests; crosscheck evidence
  docs/baselines/p5-05e-com-parameters-crosscheck-evidence.v1.yaml.
- Charter p5-05e-com-parameters-stage.v1.yaml; source map
  p5-05e-mit-source-map.v1.yaml.
- PLAN **P5-05e**; ledger note/gate P5-05; coverage gates 96 -> 97.
