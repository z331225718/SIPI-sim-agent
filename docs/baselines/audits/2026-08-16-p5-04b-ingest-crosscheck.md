# P5-04b Ingest Pipeline + Oracle Cross-Check — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 sub-slice 04b (network ingest pipeline and first
  product-vs-oracle cross-check)
- Status: delivered and mechanically bound

## Deliverable

- `crates/sipi-com/src/ingest_v1.rs`: file-to-internal port reorder
  ([1,3,2,4] per manifest file_port_order and config Port Order),
  mixed-mode sdd21 per row; 3 Rust tests (sipi-com now 12).
- Test-only runner `tests/p5_04b_ingest_runner.rs` (harness=false):
  product four-port parser -> ingest -> sdd21 at target; full-series
  hash.

## Cross-check result

Three authorized synthetic S4P fixtures at 26.56 GHz:

| fixture | product sdd21 | oracle sdd21 | delta dB |
| --- | --- | --- | --- |
| thru | -10.0 dB | -10.0 dB | 0.0 |
| fext | -40.0 dB | -40.0 dB | 0.0 |
| next | -40.0 dB | -40.0 dB | 0.0 |

max |delta| = 0.0 dB (tolerance 1.0 dB). This is the first
product-vs-MATLAB-oracle numerical agreement in the COM area.

## Scope discipline

Full-bandwidth parity, stage-chain parity, and release evidence remain
non-claims; channel selection / equalizer search / PDF / metrics stages
are still pending.

## Binding

- Evidence `p5-04b-ingest-crosscheck-evidence.v1.yaml`;
- Verifier `verify_p5_04b_ingest_crosscheck.py` + 5 tests;
- PLAN **P5-04b**; ledger note/gate; coverage gates 91 -> 92.
