# P5-06 original-13 Rust-vs-MATLAB acceptance reclassification

Status: `pending_fresh_rust_vs_matlab_original_config_matrix`.

## Decision

P5-06 moves additively from the historical scoped result-surface and artificial
three-scalar `TD_ILN_dB` direction to the original-13 r4.80 corpus. Existing
P5-06k/q/r, P3C-03 and result-surface evidence remains immutable and is not
rewritten or deleted. This preparation record does not close P5-06.

Stage 1 compares the final public result surface from the current immutable
SIPI Rust candidate against fresh pinned MATLAB: 13 workbooks, ordered
THRU/FEXT/NEXT channels, 28 cases and 303 scalar slots. The metric surface is
the actual original-13 output, including COM, ERL, FOM, ICN, VEC, VEO, IL,
CTLE gain, `g_DC_HP` and `itick`; upstream-absent `TD_ILN_dB` is not required.
Fresh MATLAB repeatability uses a frozen absolute `1e-12` gate; Rust-to-MATLAB
finite values use the original runner's frozen absolute `1e-9` gate. Infinity
requires equal sign and position. NaN fails unless a case+field allowlist is
justified by both fresh MATLAB runs.

The historical benchmark records `implementation_commit=3257c2...` and is
only corpus/schema precedent. Its Python PASS values are not current Rust
parity and are not fresh replay at pinned `5272ffe`. The 13 workbook identities
still match the pinned Git objects; all three current pinned channel objects
differ from the historical declared hashes, so both identities are recorded
without substitution.

Stage 2 is diagnostic only. Instrumented MATLAB must first prove identical
final results to an uninstrumented run. Arrays require pre-frozen per-array
tolerances and exact shape, dtype, order and axis; alignment, resampling and
cropping are forbidden. No public API is added for evidence.

Formal custody later requires two independent MATLAB runs and two independent
Rust runs with separate roots, run IDs, nonces and report hashes, plus immutable
candidate commit/tree/archive. Assets remain external and are represented only
by repository-relative path, bytes and SHA-256.

S-parameter fitting remains forbidden. Channel conversion remains one final
FD-to-TD impulse.
