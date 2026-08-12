# P3C Agent-COM S-Parameter Source Authorization Preflight v1

## Scope

This preflight reads exactly three Git blobs from the pinned external
`agent-com` commit: the interpolation, frequency-to-time-domain, and
causality modules. It records identity, declared lineage markers, imports,
and direct-port blockers. It does not import Python, run a COM/MATLAB oracle,
read a workbook or fixture, generate an impulse, or create a product API.

## Conditional Direct-Port Decision

The owner has selected `direct_licensed_port_mixed_license` only after every
listed path has an affirmative upstream-provenance, copyright, license,
NOTICE, dependency, and distribution decision. An observed repository-level
MIT license is necessary evidence, but it is not a per-path relicense proof.

Until that decision is recorded, the candidate paths remain external review
material. No copied or translated implementation may enter a product crate,
test fixture, release archive, or default route.

## Required Review Facts

The observer must bind canonical origin, SHA-1 commit/tree, root MIT license
blob, each path/blob/content hash/length, and the static markers that declare
R4.80 lineage. It must also enumerate direct imports. Any source drift,
unexpected path, missing marker, unclean source worktree, or changed remote
rejects the record.

Each candidate must separately resolve whether it is original work, an
authorized public/standard implementation, or a derived MATLAB/R4.80 port;
its actual copyright holder; the exact redistributable license; required
NOTICE/attribution; and its dependency closure. The reviewer must not infer
those facts from the root `LICENSE` or `LICENSE-MANIFEST.md` alone.

## Product Policy Boundary

The observed functions expose competing choices for interpolation, DC and
out-of-band completion, Hermitian construction, IFFT scaling, delay handling,
causality repair, and impulse truncation. This preflight does not choose any
of them. Product policy must name each choice, its numeric limits, and its
failure behavior before a P3C candidate executor may consume it.

## Non-Claims

This is not a license opinion, a direct-port admission, a mixed-license
release change, an ADS equivalence claim, a causal/passive-channel admission,
or a P5 authoritative R480 reference. It does not relax historical source
drift, the rejected rational lane, or any release gate.
