# P5-06c Normalized Input Surface — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06c (normalized input surface)
- Status: delivered and mechanically bound; compare matrix pending

## Method

Read the authorized 120g C2M TP1a config sheet (COM_Settings sheet,
block-start detection across Table 93A-1 / I/O control / Table 93A-3
columns) and cross-referenced all 214 canonical R480 parameter keys
(P5-02h v2) against config values; recorded the port-order fact.

## Result

- 82 / 214 canonical keys have config values (e.g. f_b=53.125 GBd,
  A_ft=0.6 V - a config override of the default-chain 0.5).
- Port Order observed: [ 1 3 2 4 ].
- Surface `p5-06-normalized-input-surface.v1.yaml`, hash-bound to the
  config sheet.

## Scope discipline

No comparison, default resolution, or warning contract; the surface is
the normalized-input reference for the future compare matrix.

## Binding

- Verifier `verify_p5_06c_normalized_input_surface.py` + 5 tests;
- PLAN **P5-06c**; ledger note/gate; coverage gates 85 -> 86.
