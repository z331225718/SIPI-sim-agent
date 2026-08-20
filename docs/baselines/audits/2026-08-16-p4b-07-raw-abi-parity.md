# P4B-07b TX Raw ABI Output Parity — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-07 sub-slice 07b (raw ABI output parity, TX fixture)
- Status: delivered and mechanically bound; P4B-07 main item stays open
  (RX surface and full compare matrix pending)

## Method

Same fixed probe surface as 07a (hash-pinned TX DLL + caller .ami text,
4x4 identity-like matrix, 1 ps / 31.25 ps timebase, init / single-1024 /
single-4096 / multi probes). Each fresh custody runs both the clean-room
Rust host and an independent ctypes observer
(`tools/p4b_07_ctypes_observer.py`, external-only, not product code)
with byte-identical inputs; per-probe raw output hashes and lengths must
match (host == observer), across two fresh custodies.

## Result

- TX: all four probes show `host == observer` on raw output waveform
  hash/length and clocks hash/length, in both custodies
  (`all_probes_host_equals_observer`).
- RX: excluded from this parity claim (`rx_surface:
  not_in_this_parity_claim`); the 07a crash observation stands.

## Debugging fixed during the run

- Observer hash function used `float.to_bytes` (AttributeError) - fixed
  to `struct.pack('<d', ...)` matching the Rust `to_le_bytes`.
- Parity comparison read the wrong report nesting (host report wraps
  probes under `probe`) - fixed.
- Init-only probe detection keyed on `phase` instead of `mode`.

## Binding

- Charter `p4b-07-raw-abi-parity.v1.yaml`; evidence
  `p4b-07-raw-abi-parity-evidence.v1.yaml` (hash-only);
- Verifier `verify_p4b_07_raw_abi_parity.py` + 5 tests;
- PLAN **P4B-07b**; ledger note/gate; coverage gates 74 -> 75.

## Non-claims

not_rx_parity; not_numerical_reference_parity; not_ibis_ami_compatibility;
not_tx_rx_composition; not_worker_admission; not_product_runtime;
not_release_evidence.
