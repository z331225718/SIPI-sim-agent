# P5-06 Current Original-13 Acceptance

Status: `accepted_stage1_final_scalar_and_per_workbook_performance`.

Candidate `83e9cb6c` was replayed twice from its immutable archive against two
independent fresh pinned Agent-COM R2024b replays. The matrix covers the fixed
13 workbooks, ordered THRU/FEXT/NEXT inputs, 28 package cases, and 303 final
scalar slots. The replay tools and all five external reports are hash-bound by
`p5-06-original13-rust-matlab-r2024b-current-acceptance.v1.yaml`.

Both MATLAB runs use the pinned Engine launch mode with `-singleCompThread`.
Both Rust runs explicitly set `RAYON_NUM_THREADS=16`; this is a deployment
wall-clock comparison, not a claim about relative single-thread algorithms.

All scalar gates passed: MATLAB repeat tolerance `1e-12`, exact Rust repeat,
cross-engine finite scalar tolerance `1e-9`, matching signed infinities, and
Rust no slower than MATLAB for every workbook and in total. Rust worst total
was `149.7176113 s`, versus MATLAB best total `1566.7051462 s`. On the slowest
C2M workbook (index 2), Rust worst time was `82.5354424 s`, versus MATLAB best
time `664.0101237 s`.

This accepts only the final scalar surface and the stated performance policy.
It does not accept arrays/checkpoints, warnings beyond the 303 scalar slots,
S-parameter fitting, an IEEE conformance claim, release, or closure of P5-06.
