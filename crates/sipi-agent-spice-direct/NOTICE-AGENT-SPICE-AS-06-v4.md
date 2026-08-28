# AS-06 Agent-Spice result-contract successor

This additive notice records the direct port of the existing `run-rfm`
normalization RMS field. It does not add a solver, fit S-parameters, or change
the retained external ngspice boundary.

Upstream project: `agent-spice`
Commit: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
Tree: `b6bde97128030d6cea0d68b2f0a35d807be8c402`
License: MIT (`LICENSE`, Git blob `55aac2e4f8c36a978d315efb02815972579b8293`,
1067 bytes, raw-byte SHA-256
`d0807e4df7340fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`)

The pinned source is `src/agent_spice/sparam/rfm_ngspice.py`, Git blob
`6ac750e93ea9245d652be4c9ef1ca3c314e01dca`, 14946 bytes, raw-byte SHA-256
`7b26d8c02f575f4c52dccbdfddca3aa3fd2418774fac71f27d8cd66c84e147fc`.
It computes `reconstruction_rms` and `reconstruction_max` over the same
verification-frequency response matrix before publishing the run manifest.

The Rust port is in `src/as06_run_rfm.rs`. Existing maximum-error admission is
unchanged; RMS is now also finite-checked and emitted in
`rfm_run_manifest.json`. External-solver correctness, hostile-writer defense,
numeric acceptance, release promotion, SI S-parameter fitting, and AS-05
Xyce/XDM support are not claimed.
