# P4B-08a Authorized S4P Structure Observation — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-08 sub-slice 08a (authorized S4P structure observation)
- Status: delivered and mechanically bound; typed edge and S4P-derived
  AMI matrix pending

## Method

Structural observation (line-level, hash-bound) of the six owner-
authorized PCIe Gen5 S4P files (tx_drv / rx_fe x Fast/Slow/Typ):
touchstone option lines, record count (frequency-leading lines),
continuation structure, field layout, frequency endpoints.

## Observed facts

- All six files: 4-port RI format (`! Number of ports is 4`, `# Hz S RI R
  50.000000`), 9 fields + 3 continuation lines per record (4x4 complex).
- tx_drv: 10003 records, 0 -> 100 GHz; rx_fe: 8003 records, 0 -> 80 GHz.
- Distinct from the P3C pulse-bench record (40 GHz / 1024 points): the
  axis_note records the difference without assuming identity.
- Registry now carries all six S4P hashes (4 added this round).

## Scope discipline

No time-domain model, interpolation, channel resolution, or AMI matrix;
the S4P-derived AMI_Init matrix pipeline and the typed edge to Channel
are later P4B-08 slices.

## Binding

- Evidence `p4b-08-s4p-observation-evidence.v1.yaml`;
- Verifier `verify_p4b_08_s4p_observation.py` + 5 tests;
- PLAN **P4B-08a**; ledger note/gate; coverage gates 81 -> 82.
