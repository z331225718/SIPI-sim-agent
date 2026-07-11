# MFT-NNLS Python Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent Python MFT-NNLS vector-fitting and passivity-enforcement backend, preserve native as the default, and compare both on a validated six-file auto-mode promotion corpus.

**Architecture:** Implement the MATLAB-equivalent mathematics in a focused `agent_spice.sparam.mft_nnls` package, expose it through a thin adapter, and reuse the existing target-fit scheduler and quality contract. Run promotion cases in isolated child processes so minimum passing order, process-tree peak RSS, and wall-clock time are comparable.

**Tech Stack:** Python 3.11+, NumPy 1.26+, SciPy 1.11+, scikit-rf 1.6+, PyYAML 6+, pytest.

## Global Constraints

- Existing `native` behavior and default selection must not change.
- Promotion workload is `mode=auto`, `target_error=0.001`, `enforce_passivity=true`, raw response, and full frequency grid.
- The promotion corpus contains six unique inputs: 19, 30, 60, 91, 163, and 166 ports.
- No fitting starts unless every promotion input passes preflight.
- Do not copy or depend on GPL-3 `tntnn.m`; use SciPy solvers.
- MFT-NNLS cannot become the default in this plan.
- Every production behavior begins with a failing test and an observed expected failure.

---

### Task 1: Freeze And Validate The Promotion Corpus

**Files:**
- Create: `benchmarks/sparam/promotion-auto.yaml`
- Create: `src/agent_spice/sparam/corpus_preflight.py`
- Create: `tests/test_sparam_corpus_preflight.py`
- Modify: `src/agent_spice/cli.py`

**Interfaces:**
- Produces: `preflight_promotion_corpus(manifest: Path, report_path: Path) -> PromotionCorpusReport`.
- Produces: CLI `agent-spice preflight-sparam-corpus --manifest ... --report ...`.

- [ ] **Step 1: Write failing manifest and validation tests** covering six unique resolved paths, missing files, duplicate SHA-256, extension/parsed-port mismatch, non-finite samples, non-monotonic or duplicate frequencies, and an atomic JSON report with hashes and metadata.
- [ ] **Step 2: Run `python -m pytest tests/test_sparam_corpus_preflight.py -q`** and verify failures are caused by the missing module and CLI command.
- [ ] **Step 3: Implement immutable dataclasses and preflight validation** using `yaml.safe_load`, `hashlib.sha256`, and `skrf.Network`; never load more than one corpus file at once.
- [ ] **Step 4: Add the six-case manifest** with exactly `mode: auto`, `target_error: 0.001`, `enforce_passivity: true`, and no response scaling, frequency truncation, preview sampling, or duplicated path.
- [ ] **Step 5: Run `python -m pytest tests/test_sparam_corpus_preflight.py tests/test_cli_benchmark_sparam.py -q`** and expect all tests to pass.
- [ ] **Step 6: Run preflight against the private corpus** and inspect the report before any fit benchmark. If it fails, stop implementation runs and fix the manifest or data issue without weakening validation.
- [ ] **Step 7: Commit** with `git commit -m "feat(sparam): add promotion corpus preflight"`.

### Task 2: Define MFT-NNLS Models And MATLAB Fixture Provenance

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/__init__.py`
- Create: `src/agent_spice/sparam/mft_nnls/types.py`
- Create: `src/agent_spice/sparam/mft_nnls/model.py`
- Create: `tests/fixtures/mft_nnls/README.md`
- Create: `tests/fixtures/mft_nnls/generate_reference.m`
- Create: `tests/fixtures/mft_nnls/ex4_s_small.npz`
- Create: `tests/test_mft_nnls_model.py`

**Interfaces:**
- Produces: `MFTConfig`, `PoleResidueModel`, `MFTDiagnostics`, and `MFTResult` dataclasses.
- Produces: `evaluate(model: PoleResidueModel, s: NDArray) -> NDArray` and canonical pole-pair helpers.

- [ ] **Step 1: Write failing tests** for shape validation, stable pole reflection, conjugate-pair canonicalization, symmetric residue reconstruction, and `D + sE + sum(R_k/(s-a_k))` evaluation.
- [ ] **Step 2: Run `python -m pytest tests/test_mft_nnls_model.py -q`** and observe import failures.
- [ ] **Step 3: Implement minimal typed model primitives** with explicit `(responses, poles)` and `(ports, ports, frequencies)` conventions.
- [ ] **Step 4: Create a deterministic MATLAB fixture generator** that records toolbox source hashes and exports small ex4-derived poles, residues, weights, responses, and intermediate systems; commit only the compact `.npz`, not private large `.mat` files.
- [ ] **Step 5: Run the model tests and `python -m pytest tests/test_sparam_imports.py -q`** and expect pass.
- [ ] **Step 6: Commit** with `git commit -m "feat(sparam): add MFT-NNLS model contracts"`.

### Task 3: Port Weighting And Pole Initialization

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/weights.py`
- Create: `src/agent_spice/sparam/mft_nnls/poles.py`
- Create: `tests/test_mft_nnls_weights.py`
- Create: `tests/test_mft_nnls_poles.py`

**Interfaces:**
- Produces: `build_weights(response, mode, explicit=None) -> NDArray`.
- Produces: `initialize_poles(frequencies_hz, order, pole_type) -> NDArray`.

- [ ] **Step 1: Write failing parameterized tests** for all five MATLAB weighting modes, zero-magnitude floors, explicit weights, linear/log/mixed pole distributions, odd orders, stability, and conjugate adjacency.
- [ ] **Step 2: Run both new test files** and verify expected missing-function failures.
- [ ] **Step 3: Implement vectorized weighting and pole initialization** matching MATLAB fixture values within declared tolerances.
- [ ] **Step 4: Run both test files plus `tests/test_mft_nnls_model.py`** and expect pass.
- [ ] **Step 5: Commit** with `git commit -m "feat(sparam): port MFT weighting and pole initialization"`.

### Task 4a: Port And Prove One Relocation Step

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/vector_fit.py`
- Create: `tests/test_mft_nnls_vector_fit.py`

**Interfaces:**
- Consumes: model, weighting, and pole initialization APIs from Tasks 2-3.
- Produces: `fit_matrix(response, frequencies_hz, config, initial_poles=None) -> MFTResult`.

- [ ] **Step 1: Write failing tests** for one relocation iteration, stability reflection, relaxed/non-relaxed fitting, asymptotic `D/E` modes, symmetric matrix packing, deterministic output, and MATLAB fixture parity for poles, response, and RMS.
- [ ] **Step 2: Run `python -m pytest tests/test_mft_nnls_vector_fit.py -q`** and confirm failures identify absent fitting behavior.
- [ ] **Step 3: Implement one relocation step** with scaled least squares, QR elimination, eigenvalue pole update, conjugate normalization, and rank diagnostics.
- [ ] **Step 4: Run the single-step parity tests** and make them pass before adding iteration control.
- [ ] **Step 5: Commit** with `git commit -m "feat(sparam): port MFT relocation step"`.

### Task 4b: Add Relocation Iteration Control And Collapse Probe

**Files:**
- Modify: `src/agent_spice/sparam/mft_nnls/vector_fit.py`
- Modify: `tests/test_mft_nnls_vector_fit.py`
- Create: `scripts/sparam_mft_pole_trajectory.py`
- Create: `tests/test_sparam_mft_pole_trajectory.py`

**Interfaces:**
- Produces: `fit_matrix(..., relocation_iterations=N) -> MFTResult` with per-iteration trajectory diagnostics.
- Produces: `probe_mft_pole_trajectory(touchstone: Path, ...) -> dict[str, Any]`.

- [ ] **Step 1: Write failing tests** for deterministic multi-step relocation, stable-pole reflection, convergence stopping, and trajectory records containing pole frequencies, real parts, condition estimate, and complex-residue magnitudes.
- [ ] **Step 2: Run the focused tests** and verify they fail because iteration control and trajectory reporting are absent.
- [ ] **Step 3: Implement iteration control** without changing the verified one-step algebra, preserving MATLAB column scaling and QR elimination order.
- [ ] **Step 4: Run the full Test16 611-point trajectory probe** and explicitly classify 2 GHz behavior as avoided, reproduced, or mitigated relative to the native trajectory.
- [ ] **Step 5: Commit** with `git commit -m "feat(sparam): add MFT relocation trajectory diagnostics"`.

### Task 4c: Add Diagonal Prefit And Full Matrix Vector Fitting

**Files:**
- Modify: `src/agent_spice/sparam/mft_nnls/vector_fit.py`
- Modify: `tests/test_mft_nnls_vector_fit.py`

**Interfaces:**
- Produces: complete `fit_matrix(response, frequencies_hz, config, initial_poles=None) -> MFTResult`.

- [ ] **Step 1: Write failing tests** for diagonal prefit, full matrix iterations, factorization reuse, and MATLAB parity of final response and RMS.
- [ ] **Step 2: Run focused vector-fit tests** and confirm only the new full-fitting expectations fail.
- [ ] **Step 3: Implement diagonal prefit and full matrix iterations**, avoiding a full block-diagonal allocation.
- [ ] **Step 4: Run vector-fit tests and existing `tests/test_sparam_native_vf.py tests/test_sparam_fitting.py`**; both old and new suites must pass.
- [ ] **Step 5: Commit** with `git commit -m "feat(sparam): port MFT matrix vector fitting"`.

### Task 5: Port Y And S Passivity Assessment

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/passivity.py`
- Create: `tests/test_mft_nnls_passivity.py`

**Interfaces:**
- Produces: `assess_y_passivity(model, f_max=None) -> PassivityAssessment`.
- Produces: `assess_s_passivity(model, f_max=None) -> PassivityAssessment`.
- Produces: `select_violation_extrema(model, assessment, local: bool) -> tuple[ViolationExtremum, ...]`.

- [ ] **Step 1: Write failing analytic tests** for passive and non-passive scalar Y/S models, exact crossover bands, D/E asymptotic violations, and finite sweep fallback.
- [ ] **Step 2: Write failing MATLAB parity tests** for Y eigenvalue and S singular-value violation bands, eigen/singular-vector continuity, and global/local extrema selection.
- [ ] **Step 3: Run the new tests** and observe missing assessment behavior.
- [ ] **Step 4: Implement half-size/state-space passivity tests and robust crossover filtering**, retaining a bounded sweep fallback and recording which path produced each band.
- [ ] **Step 5: Implement extrema selection and vector continuity** without relying on raw eigenvector sign; every returned band records `band_source="half_size"` or `"sweep"` for adapter diagnostics.
- [ ] **Step 6: Run new tests plus `tests/test_sparam_passivity.py -q`** and expect all pass.
- [ ] **Step 7: Commit** with `git commit -m "feat(sparam): port MFT passivity assessment"`.

### Task 6: Port QR-Compressed NNLS Perturbation

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/nnls.py`
- Create: `src/agent_spice/sparam/mft_nnls/perturb.py`
- Create: `tests/test_mft_nnls_nnls.py`
- Create: `tests/test_mft_nnls_perturb.py`

**Interfaces:**
- Produces: `solve_least_distance_nnls(A, b, *, tolerance) -> NNLSSolution`.
- Produces: `build_residue_perturbation_system(model, extrema, config) -> PerturbationSystem`.
- Produces: `enforce_passivity(model, frequencies_hz, config) -> MFTResult`.

- [ ] **Step 1: Write failing NNLS tests** against small convex reference solutions, KKT residuals, rank-deficient matrices, infeasible tolerance, and MATLAB QR-compressed systems.
- [ ] **Step 2: Run `tests/test_mft_nnls_nnls.py`** and confirm expected missing solver failures.
- [ ] **Step 3: Implement QR compression and the dual nonnegative least-squares transform** with `scipy.optimize.nnls`/`lsq_linear`, explicit scaling, KKT diagnostics, and no GPL dependency.
- [ ] **Step 4: Run NNLS tests** and require primal feasibility plus parity tolerances.
- [ ] **Step 5: Write failing perturbation tests** for Y/S residue coordinates, `D/E` bounds, bandwidth/subindex restrictions, auxiliary samples, outer/inner loops, line scaling, and non-regression rollback.
- [ ] **Step 6: Implement perturbation assembly and robust iteration control**, factorizing compressed systems and bounding diagnostic payloads.
- [ ] **Step 7: Run both new test files plus `tests/test_sparam_passivity_nnls.py`** and expect pass.
- [ ] **Step 8: Commit** with `git commit -m "feat(sparam): port MFT QR-NNLS passivity enforcement"`.

### Task 7: Add Backend Adapter Without Changing Native Defaults

**Files:**
- Create: `src/agent_spice/sparam/mft_nnls/adapter.py`
- Create: `tests/test_mft_nnls_adapter.py`
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/sparam/target_fit.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_sparam_target_fit.py`
- Modify: `tests/test_cli_fit_sparam.py`

**Interfaces:**
- Produces: `fit_touchstone_mft_nnls(...)` with the existing `SParamFitResult` contract.
- Extends: backend selection to literal values `native` and `mft_nnls`, defaulting to `native`.

- [ ] **Step 1: Write failing dispatch tests** proving omitted backend and `backend="native"` take the byte-for-byte existing path, while `backend="mft_nnls"` uses only the new adapter.
- [ ] **Step 2: Write failing failure-isolation tests** proving an MFT error is reported as MFT and never silently converted to a native success.
- [ ] **Step 3: Run the focused fitting, target-fit, and CLI tests** and observe only the new expectations fail.
- [ ] **Step 4: Implement the narrow dispatch and adapter**, translating model coefficients, diagnostics, full-grid metrics, passivity validation, and export inputs.
- [ ] **Step 5: Run all focused tests and snapshot native reports** to prove defaults and existing output keys are unchanged.
- [ ] **Step 6: Commit** with `git commit -m "feat(sparam): integrate optional MFT-NNLS backend"`.

### Task 7b: Meet Or Diagnose The S19 Gate B Milestone

**Files:**
- Create: `scripts/sparam_mft_s19_gate_b.py`
- Create: `tests/test_sparam_mft_s19_gate_b.py`
- Create: `docs/sparam-mft-nnls-s19-gate-b.md`

**Interfaces:**
- Produces: an S19 report stating `PASS`, `FIT_FAILURE`, `PASSIVITY_FAILURE`, or `COLLAPSE_DIAGNOSIS`.

- [ ] **Step 1: Write failing tests** for the Gate B contract: full-grid RMS at most `0.001`, authoritative `max_sigma <= 1 + 1e-6`, stable poles, and explicit failure classification.
- [ ] **Step 2: Run the Gate B tests** and verify they fail because the milestone runner is absent.
- [ ] **Step 3: Implement an isolated S19 runner** using the MFT backend and frozen promotion configuration, retaining the VF trajectory and RP-NNLS diagnostics.
- [ ] **Step 4: Execute Gate B before any full-corpus performance sweep**. On failure, publish the classified diagnosis and stop before Task 8; do not infer promotion potential from MATLAB parity alone.
- [ ] **Step 5: Commit** with `git commit -m "test(sparam): add MFT S19 Gate B milestone"`.

### Task 8: Build Isolated Performance Harness And Promotion Report

**Files:**
- Create: `scripts/sparam_backend_promotion.py`
- Create: `src/agent_spice/sparam/process_metrics.py`
- Create: `tests/test_sparam_backend_promotion.py`
- Create: `tests/test_sparam_process_metrics.py`
- Modify: `docs/sparam-batch-fit-results.md`

**Interfaces:**
- Produces: `run_isolated_trial(spec: TrialSpec) -> TrialMetrics`.
- Produces: JSON/CSV/Markdown reports with minimum passing order, process-tree peak RSS, wall time, RMS, passivity margin, hashes, and environment.

- [ ] **Step 1: Write failing process tests** using `psutil` and a child/grandchild allocator to prove process-tree RSS capture and timeout cleanup on Windows.
- [ ] **Step 2: Implement and verify process-tree polling** before any benchmark: use `psutil.Process(pid).children(recursive=True)`, sample parent plus descendants at a recorded interval, and terminate the tree on timeout.
- [ ] **Step 3: Write failing scheduler tests** for identical order ladders, cold/warm policy, BLAS thread limits, resumable artifacts at `runs-sparam/mft-nnls-promotion/<input-sha256>/<backend>/<order>/<config-sha256>/`, retained failure diagnostics, and no cross-backend cache reuse. Config hash must include target error, passivity policy, BLAS thread limit, SciPy version, and MFT configuration.
- [ ] **Step 4: Write failing promotion-rule tests** requiring six-six success, no order regression, at least one lower order, lower geometric-mean RSS and time, and no single-case RSS or time regression above 20%; ties and missing metrics must not promote.
- [ ] **Step 5: Implement isolated trial execution and metrics capture** with bounded polling overhead and explicit process-tree termination on timeout.
- [ ] **Step 6: Implement report generation and the lexicographic comparator** without changing any runtime default.
- [ ] **Step 7: Run `python -m pytest tests/test_sparam_process_metrics.py tests/test_sparam_backend_promotion.py -q`** and expect pass.
- [ ] **Step 8: Commit** with `git commit -m "feat(sparam): add backend promotion benchmark"`.

### Task 9: Verify MATLAB Parity, Full Regression, And Corpus Results

**Files:**
- Modify: `tests/fixtures/mft_nnls/README.md`
- Create: `docs/sparam-mft-nnls-parity.md`
- Create: `docs/sparam-mft-nnls-promotion.md`

**Interfaces:**
- Consumes all prior task interfaces.
- Produces reproducible parity and promotion evidence; does not change backend defaults.

- [ ] **Step 1: Run all compact parity tests** with `python -m pytest tests/test_mft_nnls_*.py -q` and record fixture hashes, tolerances, and results.
- [ ] **Step 2: Run the complete regression suite** with `python -m pytest -q`; require zero failures and no new warnings attributable to this change compared with the recorded baseline.
- [ ] **Step 3: Run promotion preflight** and require all six unique hashes to pass before launching fits.
- [ ] **Step 4: Run the isolated native and MFT-NNLS promotion benchmark** using the same frozen preflight report and environment.
- [ ] **Step 5: Audit every passing model** on the full frequency grid for RMS, passivity, stability, non-finite values, and exported response consistency.
- [ ] **Step 6: Write parity and promotion reports** containing raw artifact links, failures, minimum orders, RSS, time, geometric means, and the rule-derived recommendation.
- [ ] **Step 7: Verify `native` remains the default** through CLI help, config defaults, dispatch tests, and an omitted-backend smoke run.
- [ ] **Step 8: Commit** with `git commit -m "docs(sparam): report MFT-NNLS parity and promotion results"`.
