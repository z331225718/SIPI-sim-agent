# PB-02 Pinned Native Source Corpus Preparation

This preparation freezes an additive acceptance lane for the Rust-portable,
source-owned PyBERT native simulation corpus. It does not alter the historical
PB-01/PB-02 matrix or reinterpret its blocked records.

The runner materializes the Rust candidate and PyBERT oracle from separate Git
archives. It builds the candidate from its archive and builds/runs the pinned
oracle with frozen, offline `uv`. Every successful configuration in pinned
`native/pybert-core/tests/simulation.rs` is replayed, as is the CLI-reachable
additive-noise length rejection.

For successful cases, the only comparison exclusions are the runtime input
path and engine build identity. Metadata, diagnostics, every NPZ member name,
dtype, shape, and numeric payload use `rtol=1e-9`, `atol=1e-12`. There is no
alignment, member whitelist, input mutation after binding, or case-specific
tolerance. The rejection must be nonzero on both sides and must not create
`meta.json` or `arrays.npz`.

The record remains limited to this finite corpus. It makes no claim about
AMI, IBIS, GetWave, S2P, vendor models, local extensions, Web/GUI families,
general Python compatibility, performance, release admission, or a license
decision.
