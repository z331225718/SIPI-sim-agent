# P5-06 original-13 R2024b stage-1 acceptance

Status: `accepted_stage1_final_scalar_and_per_workbook_performance`.

The current Rust candidate `0e72786c` was replayed twice from its immutable
archive against two independent fresh pinned r4.80 MATLAB R2024b replays.
Every replay uses the fixed original-13 corpus: 13 workbooks, ordered
THRU/FEXT/NEXT channels, 28 package cases and 303 final scalar slots.

The checked aggregate binds four distinct root IDs, run IDs, nonces and report
hashes. It accepts only when both MATLAB replays agree at `1e-12`, Rust repeats
are exact, cross-engine finite scalars agree at `1e-9`, and the worst Rust run
is no slower than the best MATLAB run for every workbook and in total.

All gates passed. The slowest Rust workbook was 466.9311513 seconds versus the
best MATLAB value of 673.8809084 seconds. Total Rust worst-case time was
533.5983809 seconds versus MATLAB best-case 1596.5358199 seconds.

This is a P5-06s final-scalar and performance acceptance only. It neither
accepts arrays/checkpoints nor closes P5-06, releases the product, or makes an
IEEE certification claim. The no-fit and one-final-FD-to-TD-impulse constraints
remain asserted by the aggregate.
