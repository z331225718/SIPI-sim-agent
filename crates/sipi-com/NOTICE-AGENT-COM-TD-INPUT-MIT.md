# Agent-COM TD input attribution

This crate contains a mechanical Rust port of the portable r4.80 TD input,
frequency-fill-in, and validated TD FEXT/NEXT outer-product consumption from
Agent-COM. The upstream source is MIT licensed and remains external; no
Python, MATLAB, workbook, or vendor runtime is bundled here.

Pinned upstream: commit `5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`.

The exact source role, raw Git-object byte lengths, blob IDs, content hashes,
and MIT license-object binding are recorded in
`SOURCE-MAP-COM-TD-INPUT.md` using the pinned repository objects, not a
working-tree checkout. The direct CLI scope is limited to the tested TDMODE
THRU plus TD FEXT/NEXT outer-product route. It does not claim full
TDMODE/S-parameter parity; the source map records the upstream search and
dispatch references for this bounded consumer.
