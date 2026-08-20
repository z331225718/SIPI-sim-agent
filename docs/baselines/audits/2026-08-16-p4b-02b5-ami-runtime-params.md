# P4B-02b5 AMI Runtime Parameter Table Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b5 (AMI runtime parameter table core)
- Status: delivered and cross-checked against an independent reference.
  Complements P4B-02b3 (catalog compile + candidate validation) and
  P4B-02b4 (catalog-default validity / typed default materialization).

## Method

Implement ami_runtime_params_v1.rs on top of P4B-02b4/b3/b1:
build_ami_runtime_params_v1 merges a compiled parameter catalog with a
validated candidate value set into an ordered typed runtime table. Per
catalog entry: Usage=In resolves to the candidate value when supplied, else
to the validated typed default (materialize_default_v1); an Usage=In entry
with neither is a hard error (MissingRuntimeValue) - fail closed, no silent
default. Usage=Out/Info are model-populated roles: carried through only when
a candidate is supplied, omitted otherwise. The table is emitted in catalog
(sorted-name) order, deterministic. Cross-check compares the product path
(runner binary) against an independent Python merge reference across 8
scenarios, matching ok/error/param-triples exactly.

## Result

- 8/8 product_owned_self_crosscheck_unbound (candidate-overrides-default; default-fallback;
  mixed roles sorted order; Out/Info omission and carry-through; missing-In
  error; candidate type mismatch; Integer/Boolean types;
  unknown-candidate-ignored).
- sipi-ami-text unit suite 40 tests green (8 new ami_runtime_params tests).
- Profile-agnostic; no reserved-name catalog / no AMI runtime execution / no
  modeled DLL ABI.

## Binding

- Verifier verify_p4b_02b5_ami_runtime_params.py + 6 tests; crosscheck
  evidence docs/baselines/p4b-02b5-ami-runtime-params-crosscheck-evidence.v1.yaml.
- Charter p4b-02b5-ami-runtime-params-stage.v1.yaml; source map
  p4b-02b5-mit-source-map.v1.yaml.
- PLAN **P4B-02b5**; ledger note/gate P4B-02; coverage gates 106 -> 107 (open-item gate coverage valid 107/46); session health 6/6 green.