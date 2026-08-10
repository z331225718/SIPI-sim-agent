# P2-07a Cooperative TRAN Checkpoints

Commits `104b988` and `55c6edc` add cooperative runtime checkpoints to the
fixed RC/PULSE solver at entry, each integration breakpoint, and result
construction. The CLI accounts for request plus bounded output bytes before
simulation. A pre-cancelled real `RunContext` test proves no success result is
returned. This is not hard timeout, RSS/OOM isolation, nonconvergence, or
device-model support.

`cargo fmt`, workspace tests, and workspace clippy passed. OMP request
`msg_f97b7a7cce09`; conclusion `msg_4c64b95c2672`: **0 P1 / 0 P2**.
