# P3C Selected-S4P External Static Custody Observation v1

## Purpose

This external-only observer establishes whether the exact selected four-port
source can pass the existing sealed artifact intake and static `Hdiff`
reduction twice. It does not create a public command, add a waveform route, or
invoke the real-constrained fitter.

## Procedure

The observer rejects a source inside the worktree and requires the fixed
length/SHA-256 identity. It creates a clean Git archive, builds an ignored
test-only runner there, and passes the external source to that runner. The
runner reopens the source for each of two independent temporary `ArtifactRoot`
materializations, verifies source identity before staging and after sealing,
publishes exactly `channel.s4p`, and invokes
`admit_selected_p3c_sealed_s4p_v2`. The earlier v1 observation remains a
rejected historical lexical-profile mismatch.

Both runs must return positive equal record counts and distinct manifest
digests. Source drift, manifest drift, parse/reduction failure, root reuse, or
cleanup failure rejects the whole observation. The detailed report remains
outside the worktree; a later baseline may retain only its digest and aggregate
facts.

## Boundary

The temporary roots retain `ArtifactRoot` v1's no-hostile-concurrent-writer
assumption. The observer does not retain source bytes, absolute paths, matrix
values, or `Hdiff` values. A successful observation may establish only selected
external static custody and static admission. It cannot establish rational fit,
analytic stepping, candidate waveform/reference parity, metric or receiver
acceptance, AMI/IBIS/DLL execution, or release eligibility.
