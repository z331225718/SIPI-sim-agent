# AS-06 Agent-Spice Attribution Successor

This additive successor records the caller-custody execution branch for the
pinned Agent-Spice `run-rfm` workflow. It does not rewrite the immutable v1
notice or claim that an external ngspice runtime is portable or numerically
verified. The Rust route fails closed unless the caller supplies an absolute
ngspice executable and an exact SHA-256 for the caller-owned RFM code model.
The process receives only the explicitly staged `SPICE_SCRIPTS` directory and
a fresh empty user-init root; ambient `.spiceinit` and user configuration are
not admitted.

Upstream project: `agent-spice`
Commit: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
Tree: `b6bde97128030d6cea0d68b2f0a35d807be8c402`
License: MIT (`LICENSE`, Git blob `55aac2e4f8c36a978d315efb02815972579b8293`, 1067 bytes, raw-byte SHA-256 `d0807e4df7340fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`)

The upstream backend dispatch/staging source is pinned as follows:

* `src/agent_spice/backend/ngspice.py`: Git blob `e9d1952bf1b43ad9a89bae95f1724b893e8db6b8`, 2123 bytes, raw-byte SHA-256 `eca6a855df25f44169d13f576f2c169596cfc6de29ef45c4829150d20b740672`.
  Its role is the existing ngspice backend dispatch and caller-provided model
  staging boundary; it is not a claim that the solver itself is ported.
* `src/agent_spice/sparam/rfm.py`: Git blob `508e7ae8594fd25d5c2dc152b225c0cf84f61413`, raw-byte SHA-256 `af2e2e3ab1ed7e9ac458dc73f15aedfd9cd8292dc9e5a2430cd095bc21415df4`.
* `src/agent_spice/sparam/artifacts.py`: Git blob `ba7011f89c7fe0f6bf73fad13bce9248b96de9e5`, raw-byte SHA-256 `f3131cc5117c41ab13674aaf1dfba68ed7ebed332a8154994cd9907b31299948`.

Rust implementation: `crates/sipi-agent-spice-direct/src/as06_run_rfm.rs`,
with the shared bounded external-process custody helper in `src/lib.rs` and
the additive CLI in `src/bin/sipi-agent-spice-run-rfm.rs`.

The runtime writer has an explicit candidate-local grammar adaptation: the
pinned Python writer emits `CONST`, `C`, and `DELAY`, while the caller-attested
`rfm.cm` accepts the existing `Const`-only runtime form. This is not claimed as
byte-exact source parity; it is required for the actual external code-model
runtime and is covered by the real ngspice replay.

Scope remains `scoped_as06_ngspice_workflow_observed`; external-solver
correctness, numeric parity, release promotion, and SI S-parameter fitting
are not claimed.
