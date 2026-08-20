# P2-06 Stage-Compare Coverage Record

P2-06 asks for stage compare against the required Agent-Spice TRAN example:
parsed circuit, time grid, waveforms, measurements. This audit records
the honest coverage status of the CURRENT bounded product surface and
the mechanical verifier that keeps the record accurate.

## Coverage Record

- `docs/baselines/p2-06-stage-compare-coverage.v1.yaml` (schema
  `sipi.p2-06.stage-compare-coverage.v1`, provisional):
  - `parsed_circuit`: `not_applicable_current_surface` — the current
    surface accepts typed bounded one-node RC/PULSE/PWL requests only;
    no netlist parser exists (P2-03 freeze: arbitrary_netlist rejected);
  - `time_grid`: `covered` — by P2-06e v3 and P2-06f v4 evidence;
  - `waveforms`: `covered` — frozen indexed `time`/`v(in)`/`v(out)` gates
    through two fresh external oracle replays (v4);
  - `measurements`: `not_implemented` — frozen in the P2-03 freeze.
- `tools/verify_p2_06_stage_compare_coverage.py` — verifier. It fails
  closed if: the record schema/scope/status drifts; the four-stage set
  changes; parsed-circuit or measurement statuses are misclaimed as
  covered; waveform observables change; the current-evidence identity
  (archive `538b5dd`, oracle `2cc92316`, report `854e34fd...`, 2 replays)
  drifts; the v4 audit file is missing; or the historical entries lose
  their source-drift markers.
- `tools/test_verify_p2_06_stage_compare_coverage.py` — 10 tests: live
  validity, four-stage coverage, per-stage statuses, v4 evidence binding,
  historical drift markers, and negative probes for stage/evidence/
  drift-marker drift.

## Verification

`python -B tools/verify_p2_06_stage_compare_coverage.py` returned
`{"stages": 4, "schema": "sipi.p2-06.stage-compare-coverage.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p2_06_stage_compare_coverage` passed 10/10.

## Artifact Hashes (SHA-256)

- record: `89E36D125DEA35D1C14337F3EA03A1B72E370119184C30ACEB219FB2DDD67680`
- verifier: `525515690D882F2D92C42A9B700CF0D18A0B8575984B0507E005159FA8F09A84`
- tests: `E336ED1D4CF0EB226D524E2655C2E778FD1BD0F8BD9A036AD4F6EA5E380B5B07`

## Scope and Non-Claims

- This record documents current-surface coverage; it does not complete the
  generalized P2-06 stage compare. `parsed_circuit` coverage requires a
  future netlist surface and `measurements` requires the measurement
  semantics whose tolerance decision is owner-blocked (P2-04).
- The record does not certify general TRAN, netlist, OP/AC, cross-platform
  behavior, legal clearance, or release readiness.
- v1-v3 historical evidence keeps its source-drift markers; v4 is the only
  current external-compare binding for the fixed RC/PULSE profile.
