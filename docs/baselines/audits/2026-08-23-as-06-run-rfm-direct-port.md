# AS-06 `run-rfm` direct-port audit

The source authority is the external MIT Agent-Spice object at commit
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`.

Reachable upstream entry paths are `src/agent_spice/cli.py`,
`src/agent_spice/sparam/rfm.py`, `rfm_ngspice.py`, `artifacts.py`, and the
native/ngspice backend paths. The authority depends on NumPy, an explicit
native runtime or ngspice XSPICE code model, and local deck dependencies; the
Rust leaf owns the bounded parser, deterministic deck conversion, and
preflight shown below.

The Rust leaf parses `VERSION 200600`, S-matrix Cadence Broadband RFM files,
promotes response-specific pole sets into a union basis with zero residues,
reconstructs the upstream pole-scaled 65-point response surface (or a finite
zero-pole fallback), stages the source RFM and deck with bounded recursive
dependencies through the deterministic deck converter, injects both
differential and common-ground wrappers, converts the injected deck before
dispatch, and writes the source/runtime SHA-256 input manifest. Native and
ngspice result contracts include explicit JSON validation and
measure/waveform extraction in the portable contract, but actual external
process execution is fail-closed before PATH or alias lookup. Preparation
writes only those local inputs and reports; external result files are never
fabricated locally. Non-zero delay/proportional terms, missing response
blocks, malformed data, conversion failures, and missing explicit backends
fail closed. Wrapper injection recognizes the pinned
terminal `.end*comment` form, including an unterminated final line, instead of
placing the include after the simulator terminator. Solver runtime identity
and numeric waveform/measure parity remain open. The v1 replay hashes are
unbound preparation observations, not immutable source binding; an additive v2
is reserved after the preparation commit.
