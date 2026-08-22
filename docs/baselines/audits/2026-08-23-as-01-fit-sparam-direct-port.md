# AS-01 fit-sparam direct-port audit

## Scope

This lane ports the pinned Agent-Spice `fit-sparam` numerical workflow at
commit `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` and tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`. The upstream source inventory and
MIT license binding remain in the AS-01 manifest. This Rust candidate is lane
local and does not promote a product capability or close the migration row.

## Implemented numerical chain

The candidate now executes a real vertical slice:

1. `read_touchstone` reads ASCII Touchstone 1.x S-parameter data, infers the
   port count from `.sNp`, parses Hz/kHz/MHz/GHz and RI/MA/DB option formats,
   preserves Touchstone column-major response order, and rejects bracketed
   Touchstone 2.0 sections, incomplete rows, non-finite data, and descending
   frequencies.
2. `initial_poles` follows the pinned Native initialization shape: logarithmic
   or linear frequency placement, real poles at `-2*pi*f`, and damped complex
   pole pairs. Frequencies are normalized by the network mean before solving,
   matching the upstream conditioning boundary.
3. `fit_residues` builds the upstream rational basis for real poles, complex
   pairs, constant, and proportional terms, scales columns, solves a bounded
   real-equivalent least-squares system with `faer`, and applies the pinned
   DC-constant constraint when requested.
4. `next_search_order` and `fit_sparam` run bounded adaptive order trials, retain
   the best finite candidate, evaluate full-band and priority-band RMS, and
   apply explicit passivity policy gating. An unsolvable order propagates a
   numerical error; it is never retried indefinitely.
5. `observe_sampled_passivity` converts the fitted two-port samples to the
   existing bounded SIPI sampled singular-value diagnostic. It is an
   observation over the supplied grid, not a continuous passivity certificate.
6. The result writer emits only fitted Touchstone, diagnostic JSON, and a log.
   SPICE subcircuit, RFM, wrapper, and HTML output options fail closed because
   this slice has no verified circuit topology or report implementation for
   them. It does not publish placeholder models.

The public binary `sipi-agent-spice-fit-sparam` accepts only options consumed by
this numerical route and returns zero only when the selected candidate meets
the requested RMS/passivity gate. Explicit quality/tuning/HF/passivity-budget,
outside-band weighting, weighted priority-band, and unsupported artifact
options are rejected instead of being parsed and ignored.

## Resource bounds

Execution fails closed above 16 MiB per Touchstone input, 64 KiB per input
line, 8192 samples, 16 priority bands, order/step 100, 16384 real matrix rows,
204 real matrix columns, or 2,000,000 real matrix cells. Each published
artifact is limited to 4 MiB and each artifact path to 4096 bytes. The matrix
budgets are checked before `faer` allocation.

## Path identity and write boundary

Before the first artifact write, the input Touchstone and all three output
paths are checked pairwise. The preflight compares lexical absolute paths,
canonical paths through the nearest existing ancestor, and existing-file
identity through `same-file`. It therefore rejects direct equality, `..`
equivalence, file or parent-directory symlink aliases, hard-link aliases, and
every input/output or output/output pairing. Alias rejection occurs before
`write_fit_artifacts`; regression tests snapshot every existing file and
require exact byte equality after each rejected request. Since the bytes are
unchanged, their SHA-256 identities are unchanged as well.

## Support matrix

Supported in this slice: Touchstone 1.x two-port S data; Hz/kHz/MHz/GHz;
RI/MA/DB; full-band and unit-weight priority-band target selection;
explicit/legacy passivity resolution; fixed-pole residue fitting; bounded order
search; sampled passivity check/off; and fitted Touchstone plus diagnostic
JSON/log output.

Still open and deliberately fail-closed: n-port fitting above two ports;
Touchstone 2.0 bracket sections; Native pole relocation iterations; exact
upstream weighting/quality tuning profiles; continuous Hamiltonian passivity
check/enforcement; verified SPICE/RFM circuit topology; HTML report generation;
and exact artifact-content parity. `--passivity enforce` returns an explicit
unsupported error rather than silently acting as check.

## Oracle

`tools/run_as_01_fit_sparam_oracle.py` freezes ten scenarios, materializes a
deterministic two-port fixture, and can run two fresh isolated upstream and
candidate stages with nonce-bound reports. The default invocation remains a
preparation plan. No numeric tolerance, parity acceptance, or product release
claim is made by this audit.
