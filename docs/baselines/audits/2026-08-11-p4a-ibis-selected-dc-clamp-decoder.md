# P4A-04c Selected IBIS DC Clamp Decoder Audit

Date: 2026-08-11

## Scope

Commit `f36358e` adds an in-memory, selected-profile decoder for one Typical
Input model. It produces the existing typed DC clamp model and `C_comp`
declaration only. It does not read files, external assets, URLs, package/pin,
PVT fallback, V-T, ramp, AMI, or a network.

## Reviewer Result

Orca review `msg_bca6241020e0` reported one P1 and zero P2 findings. The P1
was a stale `product-boundary.v1.yaml` inventory after adding the independent
spec. This acceptance update regenerates the inventory and updates both
boundary-hash consumers. No decoder correctness P1/P2 finding remained.

## Verified Boundary

- The selected scope ends at the next `[Model]`; model type, `C_comp`, and
  both clamp sections are exact and fail closed on missing or duplicate data.
- The decoder consumes only the Typical voltage/current columns. Extra columns
  are unconsumed. `C_comp` remains declaration metadata with zero DC current.
- Synthetic tests cover model/version mismatch, invalid model type, negative
  capacitance, invalid table order, duplicate declarations, and Algorithmic
  Model rejection.
- The product has no external IBIS fixture or network access. Two-fresh-custody
  external decoding and comparison remain P4A-04d.

## Verification

`cargo fmt --check -p sipi-ibis`, `cargo clippy -p sipi-ibis --all-targets
--locked -- -D warnings`, `cargo test -p sipi-ibis --locked`, and all five P0
verifiers pass after the acceptance update.
