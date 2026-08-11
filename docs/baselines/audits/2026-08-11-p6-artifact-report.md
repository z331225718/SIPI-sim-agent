# P6-08a Artifact Report Audit

- Scope: staged `sipi report inspect --stdin`, verified artifact projection,
  request contract, schema inventory, and P6 protocol metadata.
- Reviewer: one Orca terminal reviewer, `term_ac58e303-f0a2-4fd5-b5b7-b8e7c119e832`.
- Initial result: `0 P1`, `2 P2`, and five non-blocking P3 observations.

The first P2 found that the new schema-inventory digest incorrectly included
the tracked final newline even though the inventory declares that final newline
is not exported. The inventory now uses the deterministic exported-schema
digest. The second P2 was the expected stale product-boundary inventory after
adding the report source and schema; the boundary is regenerated below before
acceptance.

The reviewer verified root/id and manifest-path traversal rejection, complete
manifest and payload rehashing before report construction, bounded metadata
work, no partial report payload, and no report path/payload/environment leak.
`verified=true` has been explicitly constrained to local manifest/content
integrity and is not an ownership, signature, authorization, or external
provenance claim. The P1-09 response/diagnostic and exit-code contract remains
unchanged; `report show` stays unavailable.

This audit accepts only the verified local artifact integrity projection. It
does not accept payload browsing, a provenance graph, project execution,
external comparison, Channel resolution, AMI, COM, or release readiness.
