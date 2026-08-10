# P6-06a CLI Protocol Catalog Audit

- Scope: staged P6-06a command protocol catalog, product-owned examples, and
  request-schema baseline additions.
- Reviewer: one Orca terminal reviewer, `term_ac58e303-f0a2-4fd5-b5b7-b8e7c119e832`.
- Initial result: `0 P1`, `1 P2`, plus non-blocking test/usage observations.

The P2 finding was that `schema list --json` used an order different from
`schema-inventory.v1.json`; the locked Windows build verifier compares the
ordered list exactly. The implementation now uses the inventory order and a
regression test fixes that order. The incomplete `example --json` form now
returns the normal recognized-but-inapplicable error, and process tests cover
all four product-owned stdin examples.

Post-fix verification passed: workspace tests, formatting, clippy with warnings
denied, the P0 boundary/clean-room/license/source-map/acceptance verifiers, and
the staged-diff whitespace check. This audit accepts only the P6-06a
discoverable protocol scope. It does not accept project execution, generic file
or URL APIs, external comparison, Channel resolution, AMI, COM, or release
readiness.
