# P1-04B Legacy Fixture Boundary Gate

P1-04B requires legacy `sipi.*.v1` fixtures from the external migration
repositories (agent-spice, pybert, agent-com) to remain oracle-only:
they may be observed worktree-externally for Git-object provenance but
must not enter the Rust API, product fixtures, schemas, or implementation
side until the owner confirms the required profile. This audit records
the mechanical gate that keeps that boundary closed.

## Delivered Gate

- `tools/verify_p1_04b_legacy_fixture_boundary.py` — verifier for schema
  `sipi.p1-04b.legacy-fixture-boundary.v1`. It loads
  `fixtures/manifest.v1.json` and fails closed if:
  - any of the 14 external fixture assets materializes as a tracked path
    component anywhere in the repository (asset identity check, since
    the manifest `relative_path` is relative to the external repo root);
  - any legacy schema id present in the manifest appears in any product
    Rust source under `crates/` (excluding `target/`).
  The `engines/agent-spice` tree is deliberately out of scope: it is the
  retained external migration source registered as
  `retain_external_reference` in the P7-08 replacement map, not product.
- `tools/test_verify_p1_04b_legacy_fixture_boundary.py` — 6 tests: live
  validity, manifest schema, external-repo coverage, asset
  materialization rejection, no legacy schema ids in product Rust, and
  the product-owned `sipi.contract.v1` fixture remaining allowed.

## Verification

`python -B tools/verify_p1_04b_legacy_fixture_boundary.py` returned
`{"external_assets": 14, "legacy_schema_ids": 0, "tracked_paths": 1778, "valid": true}`.
`python -B -m unittest tools.test_verify_p1_04b_legacy_fixture_boundary` passed 6/6.
Investigation confirmed: the manifest lists 14 external asset collections
(47 agent-spice python fixtures, 69 native fixtures, pybert golden/models,
agent-com matlab/sparameter material, and two unresolved external
oracles), none of which materialize as tracked paths; and the legacy
fixture schemas (`sipi.run-request.v1`, `sipi.backend-execution-request.v1`,
`sipi.engine-capabilities.v1`, etc.) appear in zero product Rust sources.

## Artifact Hashes (SHA-256)

- verifier: `1D8886AF9A94CAAE2FF5C5B8DB3637A9D4F82C9FBA678515EDE34A8298B48E3D`
- tests: `8A5F598A322709EA3EA4A9FBF53FCB79A3BA489844CDCC60FED34CB880E408D3`

## Scope and Non-Claims

- This gate enforces the oracle-only boundary mechanically; it does not
  grant redistribution rights, certify any fixture, or decide whether a
  comparison is needed after the owner confirms a required profile.
- The owner decision on the required profile remains pending; until then
  the legacy fixtures stay worktree-external observation material only.
- Product-owned contract fixtures (`fixtures/contracts/...`,
  `crates/*/tests/fixtures/...`) are not legacy fixtures and remain
  allowed (P1-04A surface).
