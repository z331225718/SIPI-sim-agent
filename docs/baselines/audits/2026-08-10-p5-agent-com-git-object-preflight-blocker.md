# P5 Agent-COM Git-Object Preflight Audit

- Candidate commit: `54615c5`
- Reviewer: Orca independent read-only reviewer
- Review message: `msg_a341ea8a2d76`
- Conclusion: **1 P1 / 0 P2**

## Initial Blocking Finding

The preflight manifest anchors `agent-com` to canonical origin
`https://github.com/z331225718/agent-com.git` at
`5272ffe74702cd585054d975559b06f8afae7b6e`. A fresh clone of that origin
instead resolves `main` to `034b21b2f293b2ef97cb8be269b1bf2be38e0086` and
cannot fetch or read `5272ffe`. The local COM worktree has the target object,
is clean, and is ahead of `origin/main` by the two license-only commits
`8c6ffa4` and `5272ffe`; that is insufficient for independent replay.

P5-01a was initially blocked as `blocked_unreachable_source_anchor`. The
local manifest was not accepted while its source anchor was only locally
available.

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

## Resolution And Acceptance

The owner explicitly authorized publication of the two verified license-only
commits. Canonical `origin/main` was fast-forwarded from `034b21b` to
`5272ffe`, without rewriting history. A fresh clone of the declared origin
then resolved `HEAD` to `5272ffe`, remained clean, and passed the 415-path
preflight.

Orca re-audited this exact resolution in `msg_3b586b2f352a` and concluded
**0 P1 / 0 P2**. P5-01a is accepted only as a quarantine provenance/license
preflight; it neither promotes source nor grants release eligibility.
