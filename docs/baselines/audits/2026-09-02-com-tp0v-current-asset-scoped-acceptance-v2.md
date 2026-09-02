# TP0V Current-Asset Scoped Acceptance v2 Preparation

This is a preparation contract, not an acceptance record. It fixes the original
Agent-COM `5272ffe74702cd585054d975559b06f8afae7b6e` archive, the TP0V workbook,
and the same THRU/FEXT/NEXT payloads from that archive. The candidate is
intentionally null until this harness can be committed from a clean worktree.
The committed preparation receipt is `2f5b4d99a4a567e9ecf2938c0e90f20e6190c181`
(tree `88b06c59c5ae098e3a7e917c63866abcf4059e34`, parent
`e2a6ed7c5bd48dbd1ea91bcf2a545ab5420cfbed`). A future candidate must be its
direct child and be created from a clean worktree; this receipt is its required
parent, not an assertion that a candidate already exists.

The future run has exactly four isolated executions: two MATLAB R2026a and two
Rust runs. Each gets a separate archive, build, output, and nonce root. Rust uses
the public root workflow `sipi com run`; no direct-only command is an acceptance
substitute. MATLAB has an uninstrumented semantic/exit run and an instrumented
trace capture. Instrumentation is diagnostic only and is never used for timing.

The comparison key is workbook/case/port/checkpoint. Both TP0V cases require all
21 named scalar values and both normal-ERL ports require `time_s`,
`impedance_ohm`, `ptdr`, and `gated`. The protocol prohibits alignment,
interpolation, resampling, truncation, and delay correction. Rust/time repeats
are exact f64. Anti-causal warnings must be captured, but warning equivalence is
explicitly false and cannot decide numerical parity.

Performance is an acceptance gate: on the same machine and with build excluded,
Rust must be strictly faster than MATLAB for each TP0V case. A tie or loss is a
blocked/rejected record, never a reference-only observation.
