# P3C Sealed Selected-S4P Static Admission v1

## Purpose

This internal composition layer consumes exactly one sealed artifact payload
for the selected P3C four-port input. It binds the artifact identity and raw
bytes before reusing the existing strict lexical parser and fixed `Hdiff`
reduction. It is not a generic Touchstone, artifact, or CLI surface.

## Exact Intake

The caller supplies only an opaque `artifact_id` and lowercase manifest digest.
The artifact directory must contain exactly `success.json` and `channel.s4p`.
The existing `consume_exact_verified_v1` primitive reads, bounds, hashes, and
rechecks the manifest in the same consumption operation. The adapter then
requires payload length `1,834,156` and SHA-256
`25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47`.

No metadata sidecar exists: file identity, port map, lexical subset, parser
limits, and fixed bench are product facts rather than caller choices. The
payload is parsed only as `# Hz S RI R 50.0`, bound to the fixed port map, and
reduced as `Hdiff = (S21-S23-S41+S43)/4`. The returned wrapper carries opaque
artifact provenance, fixed raw identity, record count, and the typed transfer;
it does not return paths or raw bytes.

## Boundary

The caller-selected root still follows `ArtifactRoot` v1's no-hostile-
concurrent-writer assumption. Successful product code and synthetic tests are
not external custody evidence. Only two fresh external temporary roots using
the exact asset, each sealed and admitted through this API, may later establish
hash-only external static-custody observation. This module does not invoke the
real-constrained fitter, stepping, waveform generation, ADS, AMI, IBIS, DLL,
or a public command.
