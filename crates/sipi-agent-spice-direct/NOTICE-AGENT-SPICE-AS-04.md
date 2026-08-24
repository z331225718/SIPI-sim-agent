# Agent-Spice AS-04 source boundary

This AS-04 direct-port slice is derived only from the pinned MIT Agent-Spice
tree below. It tunes residuals of an existing Y-derived S RFM for one explicit
transient signoff scenario; it does not fit SI S-parameters or replace HSPICE.

- Upstream commit: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
- Upstream tree: `b6bde97128030d6cea0d68b2f0a35d807be8c402`
- License object: `LICENSE`, Git blob `55aac2e4f8c36a978d315efb02815972579b8293`, 1067 bytes, SHA-256 `d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`
- Exact path/blob/bytes/SHA-256 bindings are recorded in `docs/baselines/as-04-tune-yparam-tran-source-map.v1.yaml`.

HSPICE remains an external runtime. Without caller-custodied executable
identity and a real listing, the Rust leaf fails closed and makes no parity or
release claim.
