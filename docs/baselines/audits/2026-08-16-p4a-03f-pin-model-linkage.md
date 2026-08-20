# P4A-03f Pin-to-Model Linkage Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03f (typed pin-to-model linkage resolution core)
- Status: delivered and cross-checked against an independent reference.
  Builds on the P4A-03d (Model declarations) and P4A-03e (Pin declarations)
  typed surfaces; profile-agnostic, no electrical/package/table semantics.

## Method

Implement pin_model_linkage_v1.rs on top of P4A-03d/03e:
resolve_pin_model_linkage_v1 joins typed pin declarations with typed model
declarations and resolves every pin's driving model against the declared
model names plus a caller-supplied allowed no-model marker set (e.g. NC). A
pin whose model is neither a declared model nor an allowed marker is a hard
error (fail closed; no silent fallback); resolved/marker lists preserve pin
input order (deterministic). Cross-check compares the product path (runner
binary: structural parse + lift_model_declarations_v1 +
lift_pin_declarations_v1 + resolve_pin_model_linkage_v1) against an
independent Python scanner across 8 scenarios, matching ok and the
resolved/marker partitions exactly.

## Result

- 8/8 matched_hash_bound, exercising BOTH happy paths (all-resolved,
  nc-marker-allowed, mixed-markers-resolved-order, markers-not-concealing-
  unknown) and failure paths (unknown-model-pin-order, nc-unresolved-without-
  allowance, empty-pins, empty-models).
- sipi-ibis unit suite 58 tests green (8 new pin_model_linkage tests).
- Profile-agnostic typed resolution only; no electrical semantics, no profile
  selection, no pin-parasitic RLC.

## Binding

- Verifier verify_p4a_03f_pin_model_linkage.py + 6 tests; crosscheck evidence
  docs/baselines/p4a-03f-pin-model-linkage-crosscheck-evidence.v1.yaml.
- Charter p4a-03f-pin-model-linkage-stage.v1.yaml; source map
  p4a-03f-mit-source-map.v1.yaml.
- PLAN **P4A-03f**; ledger note/gate P4A-03; coverage gates 108 -> 109.
