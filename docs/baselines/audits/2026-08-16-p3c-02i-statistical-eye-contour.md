# P3C-02i Statistical Eye Contour Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02i (statistical eye contour at a target Q)
- Status: delivered and cross-checked against an independent reference;
  P3C-02 main item stays open (eye folding/bins semantics still pending)

## Method

Implement `eye_contour_v1.rs` in `sipi-com`: `statistical_eye_contour_v1` computes the
Q-threshold contour of a statistical eye grid — for each time column (strictly ascending time
offsets in UI) with per-voltage-row Q-factors (strictly ascending voltage levels), it locates the
lower and upper voltage crossings where Q crosses the target Q, using linear interpolation in Q
between adjacent voltage rows and clamping at the grid edges. This is the boundary of the
statistical eye at the target BER-equivalent Q (the P3C-02 charter blocker
`statistical_eye_contour_semantics_missing` addressed as a profile-agnostic mechanism; the target
Q is caller-supplied). Fail-closed: empty grids (`EmptyGrid`), column/row count mismatches
(`ColumnCountMismatch`/`RowCountMismatch`), non-ascending time or voltage
(`TimeNotAscending`/`VoltageNotAscending`), non-finite or non-positive Q (`InvalidQ`), a
non-positive target Q (`InvalidTargetQ`), and any column without a Q >= target span
(`NoContourAtColumn`) are strictly rejected. An independent Python reference replicates the
per-column crossing logic with the identical interpolation formula over 4 test cases.

## Result

- 9 Rust unit tests green (exact crossings on linear segments; edge clamping; no-contour column;
  empty grid; column count mismatch; row count mismatch; non-ascending time; non-ascending
  voltage; invalid Q; invalid target Q).
- Cross-check: 4 test cases (parabola grid, clamped edges, no contour column, invalid Q) driven
  through product runner `p3c_02i_eye_contour_runner`; independent Python reference matches 100%
  on valid flags, target Q, per-column crossings (bit-exact), and error contexts; 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p3c_02i_eye_contour.py` + 6 tests; crosscheck evidence
  `docs/baselines/p3c-02i-statistical-eye-contour-crosscheck-evidence.v1.yaml`.
- Charter `p3c-02i-statistical-eye-contour-stage.v1.yaml`; source map
  `p3c-02i-mit-source-map.v1.yaml`.
- PLAN **P3C-02i**; ledger note/gate P3C-02; coverage gates 222 -> 223.

## Scope / Non-Claims

- Not eye folding/bins, no COM parity, no acceptance evidence.
- Mechanism only: the target Q and the eye grid are caller-supplied; no behavior profile.
