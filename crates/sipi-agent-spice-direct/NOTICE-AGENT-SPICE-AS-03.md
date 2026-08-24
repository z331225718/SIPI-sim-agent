# Agent-Spice AS-03 source boundary

This AS-03 direct-port slice follows the pinned MIT Agent-Spice `fit-yparam`
path. It fits Y parameters and may deliver the existing exact Y-to-S path; it
does not connect S-parameter fitting to the SI channel and does not claim
global numeric parity. The governing AS-03 v2 direct-port evidence remains
open for its larger/global mismatch; the later v3 numeric-bound document is
only a fixed-line-fixture observation (approximately 4e-17, evaluated under
its scoped 1e-12 policy), does not supersede v2, and does not close the row.

- Upstream commit: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
- Upstream tree: `b6bde97128030d6cea0d68b2f0a35d807be8c402`
- License object: `LICENSE`, Git blob `55aac2e4f8c36a978d315efb02815972579b8293`, 1067 bytes, SHA-256 `d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`
- Exact path/blob/bytes/SHA-256 bindings are recorded in `docs/baselines/as-03-fit-yparam-source-map.v1.yaml`.

The audit-local mismatch location is the real residue least-squares solver
implementation divergence: Rust uses bounded `faer` column-pivoted QR while
pinned Python uses `numpy.linalg.lstsq`. This is an audit-stage location, not
a sole causal proof; no tolerance or parity claim is used to close it.
