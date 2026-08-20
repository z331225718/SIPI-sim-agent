# P3B-02 Link Kernel Singleton — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-02 gate `verify_p3b_02_link_kernel_singleton.py` (kernel
  singleton and bypass-only invariant)
- Status: gate delivered earlier; standalone audit record written in this
  round after the PLAN reference scan flagged the dangling link

## Gate semantics

The P3B-02 gate (schema `sipi.p3b-02.link-kernel-singleton.v1`) keeps the
link kernel single-source and bypass-only:

- the kernel library `crates/sipi-link/src/lib.rs` must exist and be
  git-tracked;
- every kernel convolution symbol must be defined exactly once;
- no consumer may copy a convolution symbol into another crate;
- any kernel reference outside `sipi-link` must come through an explicit
  import;
- `crates/sipi-link/src/lib.rs` and `receiver.rs` must expose only the
  bypass-only receiver surface (CTLE/FFE bypass), keeping the equalizer
  subset unclaimed pending the Link profile.

## Status

Equalizer subset semantics remain pending the owner-approved Link profile
(P3B-02 main item stays open, owner_decision). The gate prevents kernel
duplication and non-bypass stages from drifting in while that decision is
pending; it grants no equalizer, profile, or acceptance claim.
