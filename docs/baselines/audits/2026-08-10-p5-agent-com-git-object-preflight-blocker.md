# P5 Agent-COM Git-Object Preflight Blocker

- Candidate commit: `54615c5`
- Reviewer: Orca independent read-only reviewer
- Review message: `msg_a341ea8a2d76`
- Conclusion: **1 P1 / 0 P2**

## Blocking Finding

The preflight manifest anchors `agent-com` to canonical origin
`https://github.com/z331225718/agent-com.git` at
`5272ffe74702cd585054d975559b06f8afae7b6e`. A fresh clone of that origin
instead resolves `main` to `034b21b2f293b2ef97cb8be269b1bf2be38e0086` and
cannot fetch or read `5272ffe`. The local COM worktree has the target object,
is clean, and is ahead of `origin/main` by the two license-only commits
`8c6ffa4` and `5272ffe`; that is insufficient for independent replay.

P5-01a therefore remains blocked as `blocked_unreachable_source_anchor`.
The local manifest is not accepted and cannot support any source or release
promotion until the source anchor is publicly reachable through the declared
canonical origin (or an owner-approved canonical source is recorded and
revalidated).

## Preserved Evidence

The reviewer found no P2 issues in the local-only preflight implementation:

- it enumerates 415 tracked Git objects and rechecks tree/blob/byte hashes;
- the root MIT marker is evidence-only, with `promotion_eligible: false`;
- MATLAB, data, workbook, benchmark, and unresolved paths remain
  `external_only` or quarantine;
- dirty trees, origin/hash drift, gitlinks, LFS pointers, coverage mismatch,
  and promotion attempts fail closed.

This record does not claim that `agent-com` is MIT-release-ready, that COM is
implemented, or that the local-only source anchor is independently available.

## Resolution Gate

An owner must explicitly authorize publication of the two verified
license-only commits to canonical `origin/main`, or name a different
canonical, independently reachable source. After that action, the preflight
must run from a fresh clone and receive a new 0 P1 / 0 P2 audit before P5-01a
can be accepted.
