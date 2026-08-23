# PB-05 Current Immutable Evidence Audit

Status: **blocked / not evaluated**

Two fresh archive-only `sim-compare` replays (`pb-05-current-bound-archive-01` and `pb-05-current-bound-archive-02`) used candidate commit `64b783f66d7e986d0975be5ac3946b453b15c4ed` and the pinned PyBERT oracle, with distinct report IDs/nonces/digests and exact matching toolchain identity.

No independent external `BackendRunResult` reference was supplied. The candidate therefore returned `reference_unavailable` with `reason: not_evaluated`, `reference_required: external_python_reference_required`, and `status_only_comparison: false`. No same-crate Rust self-reference was generated and no parity passed. The row remains open.
