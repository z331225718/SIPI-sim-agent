# PB-04 Current Immutable Evidence Audit

Status: **blocked / open**

Two fresh archive-only `sim-auto` replays (`pb-04-current-bound-archive-01` and `pb-04-current-bound-archive-02`) used candidate commit `64b783f66d7e986d0975be5ac3946b453b15c4ed` and the pinned PyBERT oracle. Both reports have distinct run IDs, nonces, report digests, and exact matching toolchain identity.

The candidate preserves upstream selection: `selected: python`, `implementation: external_python_reference_required`, `rust_only: false`, parity gate `blocked`. Rust does not silently substitute a portable reference. The row remains blocked and no promotion is claimed.
