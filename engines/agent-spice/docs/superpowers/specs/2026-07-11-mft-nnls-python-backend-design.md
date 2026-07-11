# MFT-NNLS Python Backend Design

## Goal

Build a Python implementation of the MATLAB MFT-NNLS toolbox and integrate it as an independent S-parameter fitting backend without changing the existing `native` backend's behavior or default selection.

The intended user workflow is `auto` fitting with `target_error <= 0.001` and `enforce_passivity=true`. The new backend is eligible for promotion only when it reaches that target at lower model order and is also superior in peak memory and wall-clock time on the promotion corpus.

## Source And Licensing

The reference implementation is the local toolbox at `C:/Users/z3312/code/agent-spice/user_input/mft-nnls_1` (MFT-NNLS Toolbox v1, January 2026). The port covers the mathematical behavior of `VFdriver`, `vectfit4`, `RPdriver`, `RP_QRNNLS_Y`, `RP_QRNNLS_S`, passivity assessment, violation-extrema selection, and pole-residue/state-space conversion.

The implementation will use SciPy's bounded least-squares/NNLS facilities rather than copying the optional GPL-3 `tntnn.m`. If any code derived from Bill Whiten's BSD-licensed `nnls.m` is retained, its copyright and disclaimer must be reproduced in the repository. The preferred implementation avoids copying either optional solver and expresses the dual NNLS formulation directly with SciPy.

ATP, EMTP, and PSCAD exporters are not part of this backend milestone. Agent-Spice's existing model and SPICE export path remains authoritative.

## Architecture

Create an isolated `agent_spice.sparam.mft_nnls` package with four bounded responsibilities:

- `types.py`: immutable configuration, pole-residue model, diagnostics, and result types.
- `vector_fit.py`: matrix vector fitting equivalent to `VFdriver`/`vectfit4`, including pole initialization, relocation, stability reflection, weighting, symmetry, and real/complex pole pairing.
- `passivity.py`: Y- and S-parameter passivity assessment, violation-band extrema, robust outer/inner iteration control, and residue/D/E perturbation.
- `nnls.py`: QR-compressed least-distance/dual-NNLS systems and SciPy solver adapters.

`adapter.py` converts between MFT-NNLS models and the existing Agent-Spice fitting result contract. Existing `native_vf.py` and native passivity routines remain untouched except for a narrow backend dispatch point. The CLI and target-fit scheduler accept `backend="native" | "mft_nnls"`; `native` remains the default.

## Algorithm Equivalence

Equivalence is established at intermediate boundaries rather than only final RMS:

1. Load MATLAB `.mat` fixtures and normalize their array ordering.
2. Compare initialized poles and weighting matrices.
3. Compare one vector-fitting relocation step, fitted response, and RMS.
4. Compare Y positive-real eigenvalue bands and S maximum-singular-value bands.
5. Compare selected violation extrema and constructed QR/NNLS systems.
6. Compare one residue perturbation and the complete robust-iteration result.

Numerical comparisons use scale-aware tolerances. Pole sets are matched independent of ordering, conjugate pairs are canonicalized, and equivalent state-space realizations are compared by frequency response rather than raw eigenvector signs.

| Boundary | Acceptance rule |
| --- | --- |
| Poles | Conjugate/order canonicalization, then `abs(delta) <= max(1e-8 * max(abs(reference), 1.0), 2*pi*1e-3)` rad/s. |
| Fitted response and RMS | `rtol=1e-7`, `atol=1e-10` for normalized S values; use frequency-response comparison rather than realization coordinates. |
| Passivity bands | Matched band endpoints must agree within `max(1e-6 * f_endpoint, 1.0)` Hz; extrema must be in the matched bands. |
| NNLS solve | Primal residual norm within `1e-7` relative to MATLAB; KKT stationarity infinity norm at most `1e-8` after the same system scaling. |

Every fixture documents its source values, MATLAB release, toolbox-file SHA-256 values, and the applicable row in this table. A toolbox hash change invalidates the fixture until it is regenerated with `generate_reference.m` and its tolerance rationale is reviewed.

MATLAB `VFdriver` directly applies `log10(s(1)/i)` when constructing logarithmic initial poles. Its behavior at an exact DC first sample is non-finite and is therefore outside MATLAB parity scope. The Python backend uses the first positive frequency as its logarithmic lower bound. The supplied `ex4_S` reference begins at 10 Hz and is eligible for MATLAB parity; promotion inputs with an exact DC sample are validated Python-versus-native only, with this exception recorded in their report.

## Pole Collapse Gate

MFT-NNLS uses Gustavsen `vectfit4`, which is also a relaxed vector-fitting relocation method. This does not establish that it avoids the existing native 2 GHz complex-pair collapse. The implementation must retain the reference algorithm's column scaling, QR elimination order, and post-relocation stability logic exactly where they differ from native, then measure the difference rather than assume one exists.

After the single-step relocation parity work, run a Test16 trajectory probe on the full 611-point grid. It records each iteration's pole frequencies, real parts, relocation condition estimate, and complex-residue magnitude. The port cannot proceed to full-corpus promotion work until this probe states whether the MFT trajectory avoids, reproduces, or mitigates the native 2 GHz collapse.

## Auto Integration

The shared auto scheduler supplies the same order trial sequence, full input frequency grid, RMS threshold, and passivity policy to both backends. A backend trial is successful only when:

- full-grid mean RMS is at most `0.001`;
- the final full-band passivity check succeeds with the existing project epsilon;
- all poles are stable;
- exported-model audit matches the fitted model and original frequency grid;
- no non-finite model coefficient or response is present.

The first successful order is the backend's minimum passing order. Backend failures are isolated and reported; they never cause a fallback that is mislabeled as an MFT-NNLS success.

## Promotion Corpus Preflight

Add an immutable promotion manifest separate from `benchmarks/sparam/cases.yaml`. It contains the six unique local Touchstone inputs currently represented by that file: 19, 30, 60, 91, 163, and 166 ports. Every case uses raw response data, the complete frequency grid, `mode=auto`, `target_error=0.001`, and `enforce_passivity=true`.

Before a comparison run, preflight must:

- reject missing or unreadable files;
- verify filename extension port count against parsed port count;
- verify finite, strictly increasing, duplicate-free frequencies;
- verify finite S matrices and consistent reference impedance metadata;
- compute SHA-256, file size, frequency bounds, point count, and port count;
- reject duplicate hashes so an input cannot be counted twice;
- write a frozen preflight report consumed by both backend runs.

No fitting starts unless all six cases pass preflight.

The frozen manifest declares `reference_impedance_ohm: 0.1`. Each case must use this real, frequency-invariant impedance for every port; preflight rejects a mismatch. S-parameter passivity remains evaluated in the source Touchstone normalization, and MFT Y/S conversions must carry this impedance explicitly rather than assume 50 ohm.

## Benchmark And Promotion Rules

Each backend runs in a fresh child process per case/order. Measurements include wall-clock time and process-tree peak resident memory (RSS), not only Python allocation tracking. Inputs, order schedules, BLAS thread limits, process affinity policy, warm-up policy, and environment metadata are identical and recorded.

Comparison is lexicographic per case:

1. minimum passing order;
2. process-tree peak RSS at that order;
3. wall-clock time at that order.

MFT-NNLS is not promoted automatically. A promotion report may recommend changing the default only if all six cases pass both backends, MFT-NNLS has no higher minimum passing order on any case, has a lower order on at least one case, and geometric-mean peak RSS and wall-clock time are both lower. A later reviewed change is required to alter the default.

Additionally, no case may have peak RSS or wall time more than 20% above native at its selected passing order. This per-case guard prevents a small-input improvement from masking a large-port regression.

## Error Handling And Diagnostics

Public errors identify the stage (`preflight`, `vector_fit`, `passivity_assessment`, `nnls`, `validation`, or `export`) and preserve the attempted order and backend. Linear algebra failures include rank, condition estimate, matrix shape, solver status, and iteration without dumping large arrays. All diagnostic JSON remains bounded in size.

`PassivityAssessment` records `band_source` for every violation band (`half_size` or `sweep`). The adapter writes that field into its diagnostics JSON so a sweep fallback cannot be mistaken for an analytic half-size detection.

On Windows, Task 8 measures process-tree RSS with `psutil.Process(...).children(recursive=True)` polling and records the polling interval. Its child/grandchild test must prove peak capture and teardown before the metric can participate in promotion.

## Testing

Testing proceeds test-first at four levels:

- unit tests for pole pairing, weighting, model evaluation, QR compression, NNLS transforms, and Y/S passivity calculations;
- MATLAB parity tests using small checked-in numeric fixtures derived from the supplied examples;
- integration tests for backend dispatch, auto order search, failure isolation, reports, and CLI behavior;
- opt-in corpus tests for the six private files, including preflight and process-level performance capture.

The default test suite must not require private data or MATLAB. MATLAB-generated parity fixtures include provenance, source script, source hash, and tolerance rationale.

## Non-Goals

- Replacing or refactoring the existing native algorithm.
- Changing the default backend during this implementation.
- Claiming superiority from preview, scaled-response, band-limited, or duplicate cases.
- Requiring MATLAB at runtime.
- Porting plotting code or external simulator-specific exporters.
