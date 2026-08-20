# P4B-07 Range-Complete — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-07 main item closure by range fact (TX surface complete,
  RX surface blocked on all documented call surfaces)
- Status: closed; P4B-08 owns the S4P-derived call surface

## Evidence bound to this closure

- 07a: authorized fixture ABI observation - TX four probes (init, single-
  1024, single-4096, multi-1024) succeed and reproduce byte-exactly in
  two fresh custodies (hash-only evidence).
- 07b: TX raw ABI output parity - clean-room Rust host equals independent
  ctypes observer per probe (waveform/clocks hashes and lengths) in both
  custodies.
- 07c: RX AMI_Init probe-surface exploration - crash (0xC0000005)
  reproducible across four documented matrix variants x two custodies;
  independent of matrix content; not attributed to DLL internals.

## Closure rationale

The main item's required mode coverage (Init-only, single/multiple
GetWave, different legal lengths) and the raw ABI output compare are
fully exercised and mechanically bound on the TX fixture. The RX
fixture's AMI_Init fails on every documented call surface; a usable RX
call surface requires the S4P-derived channel matrix pipeline, which is
P4B-08's typed-edge scope, not P4B-07's. Closure is by range fact with
explicit non-claims, not by weakening any observation.

## Bookkeeping

- PLAN P4B-07 row: `[x]` with closure note.
- Ledger: P4B-07 removed, `total_open` 32 -> 31; ledger test updated.
- Owner-input request: P4B-07 removed (13 -> 12 entries; external_asset
  6 -> 5); verifier test updated.
- Gate coverage keeps P4B-07 mapped (completed-item convention, 81
  gates unchanged; the four P4B-07 gates stay swept).

## Non-claims (carried by the bound evidence)

not_numerical_parity; not_ibis_ami_compatibility; not_tx_rx_composition;
not_worker_admission; not_product_runtime; not_rx_init_stability;
not_release_evidence.
