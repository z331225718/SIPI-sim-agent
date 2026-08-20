# P5-08a COM Run-Request Admission Preflight Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-08 sub-slice 08a (COM run-request admission preflight core)
- Status: delivered and cross-checked against an independent reference.
  This is the minimal P5-08 slice the owner authorized (owner-decision
  checklist P5-08: integrate in smaller slices after the conformance-stack
  revert); it is strictly a request-side admission gate, not a COM run.

## Method

Implement com_run_admission_v1.rs: validates the structural contract of a
sipi.com.run-request.v1 request (schema id match, non-empty artifact_root /
artifact_id caller bindings, non-empty params object of scalar values)
without executing any COM computation, conformance admission, or artifact
consumption. Fail-closed: invalid JSON, schema mismatch, and non-scalar
params are errors; missing params / empty params / unbound artifacts yield a
not-admitted verdict with a stable reason. Cross-check compares the product
path (runner binary) against an independent Python reference across 8
scenarios, matching the full verdict (ok/error or admitted/schema/artifact/
consumed-count/reason) exactly.

## Result

- 8/8 matched_hash_bound, exercising ALL paths: admitted (valid x2),
  structural-but-not-admitted (missing-artifacts/unbound, empty-params,
  missing-params), and hard-reject (schema-mismatch, invalid-json,
  nested-non-scalar).
- sipi-com unit suite 223 tests green (8 new com_run_admission tests).
- Strictly non-conformance: no COM execution, no conformance admission, no
  artifact consumption, no profile selection.

## Binding

- Verifier verify_p5_08a_com_run_admission.py + 6 tests; crosscheck evidence
  docs/baselines/p5-08a-com-run-admission-crosscheck-evidence.v1.yaml.
- Charter p5-08a-com-run-admission-stage.v1.yaml; source map
  p5-08a-mit-source-map.v1.yaml.
- PLAN **P5-08a**; ledger note/gate P5-08; coverage gates 111 -> 112.
