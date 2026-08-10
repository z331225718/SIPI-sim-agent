# P4A Official Pure-IBIS License and Identity Preflight v1

## Scope

Under the user's limited authorization, this observer-only preflight retrieves
the official candidate outside the SIPI worktree and records only transport
metadata, byte identity, bounded legal-marker observations, and custody state.
It stores neither the asset nor a local path nor any source content.

## Identity and Legal Boundary

The manifest binds one HTTPS retrieval to a byte length and SHA-256 digest.
It records whether header-shaped copyright, license, and notice markers were
observed, with line spans and text hashes only. A marker is not interpreted as
a license or permission. The candidate remains external-only while rights are
`unverified`.

The first retrieval could not complete temporary-file cleanup because the
execution policy rejected the explicit external cleanup command. Its custody
state therefore blocks selection as well as licensing. The record does not
expose the residual temporary location; a later externally controlled cleanup
and independent license evidence are required before any selection review.

## Rejection Rules

The verifier rejects absent or malformed transport/identity data, redirects to
unapproved hosts, paths or content in the record, legal-status upgrades,
product or fixture flags, and any tracked SIPI file with the observed asset
digest. Network retrieval is not part of the verifier or its tests.

## Non-Claims

This preflight does not establish a license, reuse right, pure-IBIS scope,
model compatibility, parser behavior, electrical semantics, numerical
acceptance, or release eligibility.
