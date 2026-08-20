# P3B-05b Seed/Noise/Jitter Decision-Surface Preflight — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-05 sub-slice 05b (seed/noise/jitter decision-surface freeze)
- Status: delivered and mechanically bound; P3B-05 main item stays open
  (semantics pending owner decision)

## Why a preflight

P3B-05's remaining semantics (deterministic seed, noise/jitter profile,
receiver-stage behavior) require owner decisions on required profile,
injection position, units/random-vs-timewarp model, seed replay,
observables and tolerance. P3B-05a already rejects every such request at
the causal-FIR wire boundary; this preflight freezes the unselected
decision surface so no implementation can be admitted silently before the
owner decision, and cross-binds the 05a rejection gate so the two layers
cannot drift apart.

## Deliverable

- Charter `docs/baselines/p3b-05-seed-noise-jitter-decision-preflight.v1.yaml`
  (schema `sipi.p3b-05.seed-noise-jitter-decision-preflight.v1`): six-item
  decision surface all `unselected_pending_owner_decision`; admission
  prohibits deterministic-seed, noise/jitter-profile and receiver-stage
  implementations without the owner decision.
- Verifier `tools/verify_p3b_05b_seed_noise_jitter_decision_preflight.py`
  cross-binds: PLAN `**P3B-05b` and `**P3B-05a 已完成` rows, the 05a
  rejection gate file, and the `sipi.link.causal-fir-request.v1` schema id
  in the contracts source.
- Tests `tools/test_verify_p3b_05b_seed_noise_jitter_decision_preflight.py`,
  6 tests.

## Bookkeeping

- PLAN P3B-05 row: added **P3B-05b**.
- Ledger P3B-05 note updated; gate list extended.
- Gate coverage P3B-05 entry extended; coverage gates 72 → 73.

## Non-claims

not_a_profile_choice; not_an_injection_choice; not_a_units_model_choice;
not_a_seed_replay_choice; not_a_tolerance_choice; not_acceptance_evidence.
The preflight selects nothing, implements nothing, and promotes nothing.
