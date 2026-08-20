# P3C-03g Profile-Compare Decision-Surface Update — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-03 sub-slice 03g (profile-compare decision-surface update: oracle reference bound & C4 compare admitted)
- Status: delivered and mechanically bound; P3C-03 main item stays open
  (compare matrix pending full oracle artifact custody)

## Decision Surface Advance

Following owner C4 decision (2026-08-16: COM_dB / ICN_mV / ERL, 1% relative tolerance), P5-06e bound the authoritative MATLAB oracle metric reference values (digest-verified), and P3C-04y executed and verified the end-to-end C4-vs-oracle profile compare (2/2 matched_hash_bound). This slice advances the P3C-03 decision preflight from pending status to `c4_metric_profile_selected_oracle_reference_bound`.

## Deliverable

- Updated charter `docs/baselines/p3c-03-profile-compare-decision-preflight.v1.yaml`
  (schema `sipi.p3c-03.profile-compare-decision-preflight.v1`): status
  `c4_metric_profile_selected_oracle_reference_bound`, decision surface
  `reference_binding: bound_p5_06e_matlab_oracle`, admission
  `profile_compare_implementation: oracle_reference_bound_compare_executed`.
- Updated verifier `tools/verify_p3c_03_profile_compare_decision_preflight.py`
  cross-binds:
  - PLAN P3C-01 blocker token;
  - release publication compare row: `acceptance_state: specified` with
    blocker `metric_profile_semantics_not_implemented`;
  - sibling bathtub preflight charter (status must remain not-frozen);
  - PLAN `**P3C-03g` row.
- Updated tests `tools/test_verify_p3c_03_profile_compare_decision_preflight.py`,
  6 tests (valid charter, bound surface, exact linkage, plan rows,
  regression rejection, admission rejection).

## Bookkeeping

- PLAN P3C-03 row: added **P3C-03g**.
- Ledger P3C-03 note updated; gate list verified.
- Gate coverage P3C-03 entry verified.

## Non-claims

not_a_reference_value_choice; not_com_parity; not_oracle_invocation;
not_acceptance_evidence.
