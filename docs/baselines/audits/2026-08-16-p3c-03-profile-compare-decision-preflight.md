# P3C-03b Profile-Compare Decision-Surface Preflight — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-03 sub-slice 03b (profile-compare decision-surface freeze)
- Status: delivered and mechanically bound; P3C-03 main item stays open
  (profile compare pending the P3C-01 metric profile decision)

## Why a preflight

P3C-03's remaining semantic is compare-against-profile. A profile compare
implementation would presuppose the metric profile, reference binding and
tolerance policy, all of which are unselected pending P3C-01 (the PLAN row
forbids introducing default metric semantics). This preflight freezes the
unselected decision surface so no profile-compare implementation can be
admitted silently before that decision.

## Deliverable

- Charter `docs/baselines/p3c-03-profile-compare-decision-preflight.v1.yaml`
  (schema `sipi.p3c-03.profile-compare-decision-preflight.v1`): decision
  surface (metric profile, reference binding, tolerance policy) all
  `unselected_pending_owner_decision`; admission
  `profile_compare_implementation: prohibited_without_owner_profile`.
- Verifier `tools/verify_p3c_03_profile_compare_decision_preflight.py`
  cross-binds:
  - PLAN P3C-01 blocker token;
  - release publication compare row: `acceptance_state: specified` with
    blocker `metric_profile_semantics_not_implemented`;
  - sibling bathtub preflight charter (status must remain not-frozen);
  - PLAN `**P3C-03b` row.
- Tests `tools/test_verify_p3c_03_profile_compare_decision_preflight.py`,
  6 tests (valid charter, all-unselected surface, exact linkage, plan
  rows, profile-selection rejection, implementation-admission rejection).

## Also this round

The classified coverage sweep is now a committed operational tool,
`tools/sweep_coverage_gates.py`, replacing the temporary script; the
BAD=0 claim is reproducible from the repo.

## Bookkeeping

- PLAN P3C-03 row: added **P3C-03b**.
- Ledger P3C-03 note updated; gate list extended.
- Gate coverage P3C-03 entry extended; coverage gates 71 → 72.

## Non-claims

not_a_profile_choice; not_a_reference_binding_choice; not_a_tolerance_choice;
not_com_parity; not_acceptance_evidence. The preflight selects nothing,
implements nothing, and promotes nothing.
