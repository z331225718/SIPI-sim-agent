# PB-01 scoped legacy leaf immutable replay audit

## Decision

Two independent replays of candidate commit `8bcfd1d1bc511461615f19338e453f0148e5dcb1`
(tree `ed221a36f2d3325b0aac3f3336a9c8a14d13e99a`) passed against pinned PyBERT
commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`. Both sides were materialized
from Git archives and received the fixture bytes archived in the candidate commit.

The bounded claim is only the real legacy `sim` fixture implemented by the Rust leaf:
NRZ, PRBS-7, analytic metallic line, cursor-only TX/RX FFE, CTLE bypass, DFE bypass,
and disabled noise. Twelve reachable numeric arrays passed the declared absolute plus
relative tolerance. The Rust result was restricted-unpickled and proved to be the exact
23-name `sipi.pybert_data.v1` dictionary: `item_names` order is canonical and `arrays`
contains exactly the same key set. It is not an exact `PyBertData` class pickle.

## Custody

Each replay independently generated a 256-bit nonce. Reports bind distinct complete
report hashes, identical path-redacted cargo/rustc/uv executable and version identities,
pre-build archive inventories, candidate/upstream archive hashes, fixture bytes, build
binary hash, process facts, artifact hashes, and comparison facts. The build and upstream
oracle both used the recorded rustc with wrapper variables removed. No candidate working
tree fixture or externally built candidate executable was accepted.

Each report also embeds the content hashes and repository-relative paths of the actual
PB-01 runner and imported PB-02 custody runner helper. The comparison records, per array,
the finite scale and the exact `1e-7 + 1e-6 * scale` tolerance ingredients. Successful
build/candidate/oracle exits and non-empty content-addressed artifacts are required. The
two builds are not claimed bit-reproducible; `binary_bit_reproducible` is explicitly false.

The replay and aggregate tools reuse the already reviewed PB-02 custody helpers; the
formal evidence binds both helper file hashes. Report JSON contains no executable or
workspace absolute path.

## Boundary

This formal replay supersedes only the predecessor's pending immutable-replay status for
the scoped executable leaf. It does not supersede the PB-01 branch/default/error/artifact
inventory and does not elevate the boundary-only wrapper to upstream parity.

Imported S2P, `.pybert_cfg` pickle input, AMI/IBIS models, periodic/random noise,
adaptive DFE/Viterbi, jitter/eye/bathtub analysis, and exact `PyBertData` class pickle
compatibility remain open. License admission, redistribution, product capability, and
release approval also remain outside this result. This slice's implementation agent did
not directly edit shared PLAN, ledger, or P0 files; any later governance rebind is a
separate owner action and cannot broaden this claim.
