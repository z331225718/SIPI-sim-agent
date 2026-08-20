# P3C-02d Bathtub Decision-Surface Preflight — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02d (bathtub/BER decision-surface freeze)
- Status: delivered and mechanically bound; P3C-02 main item stays open
  (bathtub estimator/tolerance pending owner decision under P3C-01)

## Why a preflight

P3C-01 explicitly forbids introducing default PRBS, clock, bins, or metric
semantics on our own (PLAN P3C-01 row), and the bathtub/BER estimator and
tolerance are not frozen. Implementing a bathtub core would select an
estimator — an owner decision. This preflight mechanically freezes the
unselected decision surface so no bathtub implementation can be admitted
silently before that decision.

## Deliverable

- Charter `docs/baselines/p3c-02-bathtub-decision-preflight.v1.yaml`
  (schema `sipi.p3c-02.bathtub-decision-preflight.v1`): decision surface
  (estimator, tolerance, reference binding, eye folding/bins) all
  `unselected_pending_owner_decision`; admission
  `bathtub_implementation: prohibited_without_owner_decision`.
- Verifier `tools/verify_p3c_02_bathtub_decision_preflight.py` cross-binds:
  - PLAN P3C-01 blocker token
    `blocked_missing_metric_profile_semantics_and_accepted_receiver_stage`;
  - metric-core v2 charter blocker
    `statistical_eye_contour_semantics_missing`;
  - release publication compare row: `acceptance_state: specified` with
    blocker `metric_profile_semantics_not_implemented`;
  - PLAN `**P3C-02d` row.
- Tests `tools/test_verify_p3c_02_bathtub_decision_preflight.py`: 6 tests
  (valid charter, all-unselected surface, exact linkage, plan rows,
  estimator-selection rejection, implementation-admission rejection).

## Bookkeeping

- PLAN P3C-02 row: added **P3C-02d**.
- Ledger P3C-02 note updated; gate list extended with the preflight gate.
- Gate coverage P3C-02 entry extended; coverage gates 70 → 71.

## Non-claims

not_an_estimator_choice; not_a_tolerance_choice; not_com_parity;
not_acceptance_evidence. The preflight selects nothing, implements
nothing, and promotes nothing.
