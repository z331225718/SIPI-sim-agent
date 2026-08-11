# P6-08a Verified Artifact Report v1

This boundary exposes only a read-only, verified projection of one already
published SIPI artifact. It does not define a directory browser, payload
viewer, project report, provenance graph, or external-comparison workflow.

`sipi report inspect --stdin` accepts exactly one
`sipi.artifact-report-request.v1` document. The caller must explicitly supply
an artifact root and opaque artifact id. The request accepts neither a default
working directory nor a URL, file list, glob, payload selector, or external
asset reference.

The implementation opens the existing root without creating an entry, then
recomputes the P1 manifest and every payload hash before producing a report.
The fixed policy bounds manifest bytes, entry count, total payload bytes, and
serialized report bytes. A malformed, unsealed, incomplete, over-limit, or
hash-mismatched artifact produces no artifact report result.

`sipi.artifact-report.v1` contains only the opaque id, verified flag, manifest
schema and digest, entry count, total payload bytes, sorted content digests,
the fixed verifier-policy id, and `integrity_lineage=unavailable`. It never
contains an artifact root, a file name or internal relative path, payload
bytes, environment data, timestamps, external asset provenance, or an inferred
producer/edge relationship. The current writers do not publish explicit edge
lineage, so the report must not inspect payload names or contents to guess it.
`verified=true` means only that the current local directory exactly satisfies
the declared manifest and content digests under this policy. It is not a
signature, timestamp, ownership, authorization, or external provenance claim.

The existing P1 JSON/NDJSON process contract and exit mapping apply. A runtime
failure still has the ordinary response envelope with a null result and one
structured diagnostic; this is not a partial artifact report. The command is
an integrity metadata view only and does not claim project execution, artifact
authorization isolation, a general provenance graph, Channel resolution, AMI,
COM, or numerical/legacy comparison.
