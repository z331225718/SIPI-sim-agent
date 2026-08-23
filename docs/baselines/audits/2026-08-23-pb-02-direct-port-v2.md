# PB-02 Current Direct-Port Audit

Date: 2026-08-23  
Status: **open / current successor**

This additive successor binds the current PB-02 `sim-native` lane. The
historical `pb-02-direct-port.v1.yaml` manifest and its 2026-08-22 audit are
left byte-for-byte unchanged. The current lane directly reuses the pinned
native core where bytes remain copied and records the additive adaptations for
legacy jitter threshold, noise/DFE controls, Touchstone CTLE handling, and the
workflow/result-adapter exports.

Current adapted root SHA-256:
`c564bd0f976e40e605ed97aa36da0fa13e8a0eed7281746a4c1d30943d610e50`.
The adapted `error.rs`, `input.rs`, and `simulation.rs` bindings remain
content-addressed to their pinned source objects. The lane is still open for
immutable candidate replay and branch-complete promotion; no license,
redistribution, or product-capability decision is made here.
