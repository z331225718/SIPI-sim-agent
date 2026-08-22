# AS-05 `run-hspice` partial direct-port candidate

Date: 2026-08-22

## Authority and license

The only upstream authority is the exact Agent-Spice Git object
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`. The source is MIT-licensed. The
path-by-path record is in `docs/baselines/as-05-run-hspice-direct-port.v1.yaml`;
every listed Python/Rust source path inherits the upstream repository MIT
license and is explicitly marked `copied: false`. No upstream source, fixture,
solver binary, or generated waveform is added to SIPI.

The direct-port code is deliberately isolated in
`crates/sipi-agent-spice-direct`. It is a contract/admission model, not a
product crate and not a replacement solver. It has no external dependencies,
does not spawn a process, and does not claim runtime source authentication.
Its `UPSTREAM_COMMIT` constant is required to equal the pinned source commit in
both the evidence record and the verifier; a source/evidence/constant mismatch
is rejected before the admission record can pass.

## Migrated converter leaves

The pinned `run_hspice` entry point first reads UTF-8 deck text, hashes and
names it, splits a base case plus ordered `.alter` cases, audits directives and
dependencies, prepares backend-specific `case.cir`/reports, and only then
optionally executes one of four branches:

| Backend | Prepare branch | Execute branch | External dependency |
| --- | --- | --- | --- |
| `native` | preserve HSPICE text | native engine or apphost, optional RFM passthrough | Agent-Spice native engine |
| `ngspice` | `.inc`/`.probe`/`post` conversion and dependency conversion | batch run, waveform and measure extraction | ngspice |
| `xyce` | preserve HSPICE text | Xyce process and solver-owned waveform output | Xyce |
| `xyce-xdm` | preserve `case.sp` source for XDM | XDM conversion, generated-case admission, then Xyce | `xdm_bdl` + Xyce |

The admission model covers the case splitter, audit, include/lib admission,
conversion actions, all four backend selectors, execute/non-execute choice,
and backend-specific artifact plans. Unsupported directives and dependency
escape conditions remain visible; they are not silently deleted.

The current Rust slice also migrates the two converter leaves that were
missing from the earlier admission model. Include and library tokenization now
matches `shlex.split(..., posix=False)` for quoted path tokens, so whitespace
inside a leading single- or double-quoted path is preserved before quote
stripping. The ngspice converter recognizes the pinned current-source PWL
`R=<time>` form, emits the upstream behavioral-source wrapping expression, and
preserves `M=<value>`. A repeat point that is absent or a non-positive repeat
window is retained as input and reported as a blocked conversion with the
upstream reasons `current_pwl_repeat_point_not_found` or
`invalid_current_pwl_repeat_window`. The non-upstream `alter_label` field was
removed from the Rust `DeckCase`; case identity remains the upstream name/text
contract plus the explicit local case kind.

## Pinned differential corpus

The Rust integration test `pinned_differential_corpus_covers_quotes_repeat_rejections_backends_alter_and_missing_end`
freezes five focused cases: quoted include/lib paths; valid current-PWL repeat
with multiplicity; each current-PWL rejection reason; all four backend plans;
and ordered ALTER splitting without a `.end`. This corpus is intentionally a
semantic leaf check, not a claim that the whole CLI workflow has been ported.

## Clean upstream replay

A clean archive materialized from the pinned Git object was used as the Python
runtime source. The focused upstream suite passed **52/52** tests, including
CLI preparation, `.alter` splitting, audit, conversion, corpus golden files,
and backend command construction.

The `alter_corners` fixture was replayed through all four prepare branches:
each returned exit code 0 and emitted three cases. Native, ngspice, and Xyce
execute replays returned 0 for all three cases using the locally available
solvers. The XDM replay reached the XDM stage and returned 1 at the base case;
it emitted the two-stage logs and generated-case artifact, and did not proceed
to later `.alter` cases. These are oracle observations, not Rust parity.

The frozen comparison contract is byte-exact prepared case text and
`compat_report.json`, exact case/branch exit codes, and exact required artifact
kinds. A numeric waveform tolerance is intentionally **not frozen** until an
independent Rust solver and backend implementation exist; setting a numeric
tolerance now would turn an external-process replay into a false parity claim.

## Remaining work

`AS-05` remains a `partial_admission_candidate`. The Rust crate still does not
read a deck file, compute the source hash/stable source path, recursively stage
dependencies, write `case.cir`/`case.source.sp`/`compat_report.json`, normalize
measure/output reports, or execute any backend process. It also lacks native
result/waveform extraction, ngspice waveform/measure extraction, Xyce output
handling, XDM's two-stage artifact lifecycle and failure codes, included-netlist
PWL rewriting, and runtime solver identity attestation. These branches remain
listed in the evidence record as missing; no product capability or release
claim is made by this candidate.
