# P1 Legacy Fixture Required-Profile Facts

## Result

This is a read-only source and manifest fact audit. It records the exact Git
objects and deterministic `git archive --format=tar` identities available for
the three external migration repositories. It does not select a profile,
authorize distribution, or turn a fixture into a product input.

## Exact source/archive identity

The source snapshot commits and trees declared by `fixtures/manifest.v1.json`
are present in the local Git objects. The corresponding full Git archive
identities are:

| Source | Commit | Tree | Archive SHA-256 | Archive bytes |
| --- | --- | --- | --- | ---: |
| agent-spice | `90f0374bc9987e9197d4dcaa3912432fbd766a5e` | `b5db1cb9a1a989459dffe7db885790abeaf47290` | `ed28cedfae54baf961c599eedbf8327a47bf6f82314c7752c494bc8b7ae192d4` | 124753920 |
| pybert | `5bf6d7ea0ace261891aaeb611ffc1c267e160afe` | `5faef6bdb341d444ad65d82a11c0018b15805e24` | `ffe693b13b598e7c365adeda4bb46cc776ffbd8135b3ac0c8f7568ed8b5d6c92` | 133396480 |
| agent-com | `034b21b2f293b2ef97cb8be269b1bf2be38e0086` | `dc6e5529612d7272f23547a796b53e1456cc49cb` | `6f8eda32959ff15e712f7b0de7c64d45ce1cd44fcdbabc2aee74302eaaa63662` | 43939840 |

The archive hashes are computed from the Git object at each pinned commit,
not from the dirty working trees. No external bytes were copied into this
repository.

## Required-profile clues actually present

The manifest has 14 assets. Nine carry `required_by[].requirement=required`:
agent-spice circuit fixtures (Python and native), pybert models and golden
fixtures, agent-com MATLAB/workbook and synthetic S-parameter material, the
agent-com local partial MATLAB oracle, the unresolved authoritative MATLAB
golden, and the unresolved ADS solver. The remaining five are labelled
optional documentation/benchmark/tool material.

All 14 assets remain `distribution.status=blocked_unknown`. The manifest has
no `required_profile` field or selected profile value. Therefore the observed
`required_by` labels are gate demand labels only; they are not an owner
selection, acceptance profile, or license decision. The existing P1-04B
boundary verifier remains the authority for keeping these legacy assets out
of product Rust sources and tracked product fixtures.

## Gate state

Source Git objects and archive identities are observed, but
`required_profile_selected=false`, `required_profile_accepted=false`, and
`owner_decision_required=true`. The next non-mechanical input is an explicit
owner decision identifying the required legacy profile and its permitted
comparison/consumption boundary. Until then, legacy fixtures remain
worktree-external oracle material only.
