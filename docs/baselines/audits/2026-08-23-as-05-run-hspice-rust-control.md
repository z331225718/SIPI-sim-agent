# AS-05 `run-hspice` Rust control-path audit

The pinned authority is the external MIT Agent-Spice object
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`. No upstream source, solver
binary, waveform, or fixture is copied into SIPI.

Reachable upstream entry paths are `src/agent_spice/cli.py`,
`src/agent_spice/hspice/alter.py`, `audit.py`, `converter.py`, `results.py`,
`project.py`, and `src/agent_spice/backend/{native,ngspice,xyce}.py`. Their
runtime dependency is the selected external solver and any recursive deck
dependencies; neither is treated as a portable Rust implementation here.

The Rust leaf reads a bounded deck, preserves the source case, splits ordered
`.alter` cases, audits quote-aware logical lines, and treats `.model` and
`.endcomment` as auditable supported directives rather than hard blockers. It
converts `.inc`/`.probe` and `.option post` forms for ngspice, then recognizes
HSPICE Touchstone S-elements (including continued lines). Because the pinned
source has no portable S-domain exporter for this element, the Rust leaf
preserves the source record and reports it unsupported rather than substituting
an AS-03 Y SPICE compatibility subcircuit. It stages bounded recursive local
dependencies (with the same
deterministic conversion applied to nested ngspice decks), and emits
source/converted decks plus compatibility reports. The pinned source has no
portable S-domain exporter for an HSPICE `S` element, so that path is now
explicitly unsupported and preserves the original element; it never calls the
AS-03 Y fit as a substitute. Actual native/ngspice/Xyce/xdm execution is
fail-closed before PATH or alias lookup.
Project YAML is parsed with the upstream `name`, `inputs.hspice_deck`,
`backend`, and `outputs.root` contract; run directories retain the upstream
`<root>/<deck>/<case>` layout. It dispatches explicitly selected
native/ngspice/Xyce/xdm_bdl processes, parses ngspice measure/waveform
transcripts, and validates a successful native JSON result object.
Unsupported directives, missing or escaping dependencies, failed conversions,
unsupported S-element export, and non-zero backend results remain blocked
without fake artifacts. A successful portable preflight is not presented as a
solver waveform/result.

The selected solver executable/runtime identity and numerical parity remain
external blockers. The v1 runner records two independent unbound preparation
observations, not immutable content-addressed evidence; no solver result is
claimed without an explicit runtime. An additive v2 is reserved after the
preparation commit.
