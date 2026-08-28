# COM-02/04 result surface continuation

This is an additive, worktree-scoped audit for the existing `run_com` and
`load_config -> run_com -> write_artifacts` paths. It does not change the
formal v5 manifest, the v13 ledger, the owner registry, or the license
records.

## Upstream anchor

The source is pinned to Agent-COM commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`, under its MIT license.

The result fields are source-derived from:

- `src/agent_com/_orchestration.py`: the selected search object owns
  `search.dfe_taps`, and diagnostics publish that field when diagnostics are
  enabled.
- `src/agent_com/reporting.py`: case diagnostics are part of the result
  payload.
- `src/agent_com/io/touchstone_r480.py`: the typed `snpPortsOrder` permutation
  is applied to the raw four-port matrix before mixed-mode conversion.

## Implemented result surface

`SearchLoopResultWithWinnerV2` now has one read-only
`selected_dfe_taps()` accessor. It returns the taps from the same private
winner context consumed by the final COM chain; it does not expose winner
construction, mutable state, bounds, or the context itself. The existing
direct search result builder publishes those exact taps at the pinned
diagnostics location:

- `cases[].diagnostics.portable_branches.search.dfe_taps`

Publication occurs only when the existing search path produced a real winner.
Fixed and floating DFE tests bind the published vector to that winner. Runs
without search, including the ordinary JSON/non-package, S2P, and JSON S4P
package paths, do not receive an empty or inferred DFE field. The historical
`SearchLoopResultV1` field set remains unchanged.

## Port-order boundary

The direct package path retains one source-exact `snpPortsOrder` parser shared
by validation and raw four-port matrix reordering. It is an execution
observation only. No `cases[].port_order`, `port_order_observed`, or other new
result-wire field is published because pinned Agent-COM does not publish one.
Tests cover the typed permutation, its trusted-workbook boundary, and its use
before mixed-mode conversion.

The channel remains one final FD-to-TD impulse and no S-parameter fit is
introduced.

## Formal replay status

No fresh external replay or aggregate is claimed here: the existing formal
v5 reports are bound to an immutable earlier candidate, while this production
slice is still uncommitted. The owner must create the preparation commit before
running two new immutable replays and an aggregate. Until that replay is
bound, this audit does not claim formal closure, numeric parity, release, or
promotion.
