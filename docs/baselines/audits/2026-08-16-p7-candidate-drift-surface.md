# P7 Candidate-Drift Surface — Precise Rebind Checklist

- Date (UTC): 2026-08-16 (round 53 verification)
- Scope: precise quantification of the P7-06d/f candidate drift that keeps
  six positive tests in honest blocked state
- Status: blocked; rebind requires external custody observation, not an
  in-repo edit

## Failing tests (all positive, all candidate-binding drift)

| Suite | Tests | Error |
| --- | --- | --- |
| test_verify_p7_processprng_layout_policy_v2 | test_document_is_valid, test_external_layout_report_is_exactly_bound | candidate_binding_invalid |
| test_verify_p7_current_candidate_pe_rejection_diagnosis | test_document_is_valid, test_external_report_is_exactly_bound | candidate_product_inputs_source_drift |
| test_verify_p7_bcryptprimitives_processprng_preflight | test_document_is_valid, test_external_report_is_exactly_bound | candidate_binding_invalid |

## Drift surface (b775dde6d242e687eb71a30b9a83a87d8b31ba55..HEAD)

```text
crates/sipi-cli/src/main.rs                       | 633 +++++++++++++++++++--
crates/sipi-cli/tests/cli.rs                      | 252 ++++++++
crates/sipi-cli/schemas/schema-inventory.v1.json  |   2 +-
crates/sipi-cli/schemas/*.request.v1.schema.json  |   1 + (3 files)
crates/sipi-contracts/src/lib.rs                  | 471 ++++++++++++++-
crates/sipi-ibis/src/lib.rs                       | 174 ++++++
crates/sipi-tran/src/lib.rs                       | 386 +++++++++++++
9 files changed, 1872 insertions(+), 49 deletions(-)
```

All changes are product implementation evolution (P4A/P6/P7 work); no
evidence or golden file was modified.

## Document bindings involved

- `p7-processprng-layout-policy.v2.yaml` — bound to b775dde6d2 (stale)
- `p7-current-candidate-static-pe-rejection-diagnosis.v1.yaml` — bound to
  b775dde6d2 (stale)
- `p7-bcryptprimitives-processprng-preflight.v1.yaml` — bound to b775dde6d2
  (stale)
- `p7-evidence-anchor.v2.yaml` — already bound to f4984999 (P7-06g chain
  observation)
- `p7-candidate-build-license-material-observation-evidence.v1/v2.yaml` —
  bound to f4984999

## Rebind condition (external step, not in-repo)

A fresh external PE static-layout observation of candidate f4984999 must be
produced (or the three stale documents marked historical with new
candidate-scoped successors), then the positive tests rebind to the new
records' hashes. This is an owner-orchestrated external-custody step;
editing the record bindings or test expectations in-repo to make the
suites pass would be golden rewriting and is forbidden.
