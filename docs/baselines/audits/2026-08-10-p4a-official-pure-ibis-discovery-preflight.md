# P4A Official Pure-IBIS Discovery Preflight Audit

## Scope

Commit `3e66b68` adds an observer-only discovery and eligibility record for one
official IBIS-site candidate. The reviewed boundary is limited to URL and
directory-listing facts. It contains no downloaded asset, parser input, model
data, content digest, local path, runtime, or product API.

## Independent Audit

Orca reviewer message `msg_743dbc3bf90b` reviewed the committed manifest,
verifier, tests, and P0 registrations. The conclusion is **0 P1 / 0 P2**.

The reviewer verified that the exact schema keeps the candidate
`discovery_only`, `required: false`, and `url_only_unresolved`; it rejects
promotion, license upgrades, content hashes, and local asset paths. The P0
register scope has no implementer or comparator material, and no Rust parser
or external asset bytes were added.

## Evidence

- `tools/verify_p4a_official_pure_ibis_discovery_preflight.py`
- `tools/test_verify_p4a_official_pure_ibis_discovery_preflight.py` (3 tests)
- P0 verifiers: product boundary, clean-room register, release-license
  preflight, and Rust candidate source-map

## Accepted Boundary

The official URL is a discovery lead only. It remains ineligible for required
profile selection, parser tests, oracle execution, release input, or product
use until a separate review supplies explicit authorization and exact asset
identity. This acceptance does not establish pure-IBIS content, licensing,
parser compatibility, electrical behavior, or numerical accuracy.
