# P4A Official Pure-IBIS Structural-Scope Preflight Audit

## Scope

Commit `0ee067a` records an observer-only structural scan of the exact,
owner-authorized external IBIS byte object. The repository contains only
identity-bound counts and digests, the limited owner-policy record, and
fail-closed verifier evidence. It contains no asset bytes, model names,
numeric data, or local custody path.

## Independent Audit

Orca reviewer message `msg_5731be31b094` concludes **0 P1 / 0 P2**.

The reviewer confirmed that third-party rights remain `unverified`; the owner
policy permits only external oracle and acceptance-selection review. Required
profile, product asset, parser fixture, runtime, release input, and promotion
states remain false. The scanner is an independent stdlib observer and records
only bounded line/header facts. Its zero counts for AMI/DLL-related indicators
are explicitly limited to the declared scan scope.

## Evidence

- `tools/observe_p4a_external_pure_ibis_structural_scope.py`
- `tools/verify_p4a_official_pure_ibis_structural_scope_preflight.py`
- `tools/test_observe_p4a_external_pure_ibis_structural_scope.py` (3 tests)
- `tools/test_verify_p4a_official_pure_ibis_structural_scope_preflight.py`
  (4 tests)
- P0 product-boundary, clean-room-register, release-license-preflight, and
  Rust candidate-source-map verifiers

## Accepted Boundary

The exact external object is now eligible only for a later owner selection
review. That is not a third-party license decision or a selection of a required
IBIS profile. Selecting one still requires a model selector, terminal and PVT
binding, stimulus/timebase, observables, tolerances, environment, and permitted
external-oracle scope. No product parser compatibility, electrical behavior,
AMI absence, runtime capability, or numerical acceptance is established.
