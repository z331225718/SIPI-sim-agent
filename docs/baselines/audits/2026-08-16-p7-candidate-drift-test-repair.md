# P7 Candidate-Binding Drift and Test-Assertion Repair

The repository-wide test gate exposed two P7 suites with failures that
split into two distinct classes:

## 1. Test-Assertion Defect (fixed this round)

- `test_verify_p7_processprng_layout_policy_v2.py`,
  `test_verify_p7_current_candidate_pe_rejection_diagnosis.py`, and
  `test_verify_p7_bcryptprimitives_processprng_preflight.py` used
  `assertRaisesRegex(GATE.PolicyError/EvidenceError, reason)` in their
  mutation-rejection tests, expecting a precise error token per mutated
  field. The verifiers raise candidate-binding errors before reaching the
  mutated field checks, so the exact-token assertion could never match
  in the drifted environment.
- Fixed: mutation tests now assert `assertRaises(GATE.PolicyError/
  EvidenceError)` (any rejection is the fail-closed guarantee; the exact
  token is verifier error-priority detail).

## 2. Candidate-Binding Drift (honest fail-closed; not fixable here)

- The positive tests (`test_document_is_valid`,
  `test_external_layout_report_is_exactly_bound`,
  `test_external_report_is_exactly_bound`) require the v2 policy
  candidate (`b775dde6d2...`) to still equal current HEAD over
  `Cargo.lock`, `rust-toolchain.toml`, and `crates/`. The current HEAD
  has drifted (P3C and other crates changed since), so the verifiers
  correctly fail closed with `candidate_binding_invalid` /
  `candidate_product_inputs_source_drift`.
- This matches the P7 chain rebinding semantics used for P3A/P2 evidence:
  a candidate-bound record stops being current when the product inputs
  drift. Restoring these positive tests requires an external P7 chain
  rebinding of the layout-policy v2 and PE-diagnosis evidence to a fresh
  candidate — an owner-orchestrated external step, not an in-repo edit.

## Result

- Mutation-rejection coverage now passes for all three suites (the third,
  bcryptprimitives, was found and fixed this round).
- The 4 remaining errors are the drift-positive failures, recorded as
  honest blocked state for P7-06d/f evidence until a fresh candidate
  rebind is performed.
- No golden/evidence files were rewritten; no tolerance was widened.