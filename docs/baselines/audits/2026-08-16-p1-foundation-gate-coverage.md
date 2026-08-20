# P0/P1 Foundation Governance Gate Coverage

P1 exit criteria require the foundation governance verifiers to stay
runnable and consistent. This audit records the current verification of
all five foundation verifiers and the coverage gate that keeps them
present.

## Verification (this round)

- `verify_product_boundary.py`: `valid: true`, provisional,
  `tracked_path_count: 1778`, `product_candidate_count: 7`;
- `verify_clean_room_register.py`: `valid: true`, provisional,
  `scope_count: 143`, `material_count: 176`;
- `verify_release_license_preflight.py`: `valid: true`, provisional,
  `release_ready: false`, `dependency_count: 12` (release correctly
  remains blocked);
- `verify_rust_candidate_source_map.py`: `valid: true`,
  `native_entry_count: 36`, `unknown_count: 36`, no blockers;
- `verify_acceptance_profiles.py`: `valid: true`, `profile_count: 4`,
  `required_profile_count: 3`, `git_object_checked_count: 0` (external
  Git-object checks remain external-custody dependent).

## Delivered Gate

- `tools/verify_p1_foundation_gate_coverage.py` — verifier for schema
  `sipi.p1-foundation.gate-coverage.v1`. It fails closed if any of the
  five foundation verifiers disappears from the tools tree.
- `tools/test_verify_p1_foundation_gate_coverage.py` — 4 tests: live
  validity, mapping completeness, on-disk existence, git tracking.

## Artifact Hashes (SHA-256)

- verifier: `96A405C86058A24D6F4523783D7D8FDD4206E7187C465B40F902C076654F0BCE`
- tests: `37194E7925BF0048FD3B8F4E79BB0659C00D22C8827217AF903F5ADE90183DF0`

## Scope and Non-Claims

- This gate records presence of the foundation verifiers; the underlying
  verifiers themselves are the authority for boundary/clean-room/license/
  source-map/profile facts. It does not certify release readiness
  (license preflight keeps `release_ready: false`).
- `git_object_checked_count: 0` reflects external-custody dependence, not
  a license or profile acceptance.
