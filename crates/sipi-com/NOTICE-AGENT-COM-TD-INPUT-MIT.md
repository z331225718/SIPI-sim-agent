# Agent-COM TD input attribution

This crate contains a mechanical Rust port of the portable r4.80 TD input
and frequency-fill-in algorithms from Agent-COM. The upstream source is MIT
licensed and remains external; no Python, MATLAB, workbook, or vendor runtime
is bundled here.

Pinned upstream: commit `5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`.

The exact source role, raw Git-object byte lengths, blob IDs, content hashes,
and MIT license-object binding are recorded in
`SOURCE-MAP-COM-TD-INPUT.md` using the pinned repository objects, not a
working-tree checkout. This notice covers only the TD input library leaf; it
does not claim a direct CLI TDMODE route or numerical parity outside the
tested portable leaf.
