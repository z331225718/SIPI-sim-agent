# P4A Official Pure-IBIS License and Identity Preflight Audit

## Scope

Commit `b7e3dc6` records a user-authorized, external-only retrieval of the
official pure-IBIS discovery candidate. The review covers transport identity,
bounded legal-marker observations, custody, fail-closed classification, and
P0 registration. No asset byte, temporary path, parser fixture, or runtime
route is in the repository.

## Independent Audit

Orca reviewer message `msg_674e3ea9824f` concludes **0 P1 / 0 P2**.

The reviewer confirmed that the record keeps rights `unverified`; a copyright
marker is only an observation, not a permission. It rejects legal or product
promotion, scans tracked files for the observed digest, and has no network
dependency in its verifier or tests. The external temporary materialization
could not be removed because the execution policy rejected the cleanup command;
the committed custody state accurately remains pending and blocks selection.

## Evidence

- `tools/verify_p4a_official_pure_ibis_license_identity_preflight.py`
- `tools/test_verify_p4a_official_pure_ibis_license_identity_preflight.py`
  (3 tests)
- P0 product-boundary, clean-room-register, release-license-preflight, and
  Rust candidate-source-map verifiers

## Accepted Boundary

The exact byte identity is known only as an external object. It remains
ineligible for required-profile selection, product use, parser fixtures,
oracle execution, and release input until an external cleanup is completed and
independent license/permission evidence is supplied. This acceptance does not
verify pure-IBIS content, model selection, parser compatibility, electrical
semantics, or numerical behavior.
