# P4A-05a IBIS Conformance Matrix Audit

Date: 2026-08-11

## Scope

Commit `ffa1682` adds the versioned P4A matrix and verifier that distinguish
the accepted external Input/TYP DC profile, product-owned self-tested
primitives, unsupported capabilities, and unassessed general IBIS claims.

## Reviewer Result

Orca review `msg_5b1b8b9ae8ce` reported zero P1 and zero P2 findings.

## Verified Boundary

- The sole external acceptance is bound to the selected asset, selector,
  charter, and external report hashes. It remains a six-probe DC claim.
- Quasi-static `C_comp` and differential R-C entries are self-tested product
  relations, not external transient or termination evidence.
- Unsupported and not-assessed entries cannot expose a product route. The
  verifier rejects absolute or parent evidence paths and inconsistent status
  promotion.
- The matrix does not make a release, license, general IBIS, AMI, file, URL,
  CLI, or default-route claim.

## Verification

The matrix verifier and its three negative tests passed, as did the five P0
verifiers. The reviewer independently checked that all referenced tests and
specifications exist and that the external report hash matches the retained
external-only report.
