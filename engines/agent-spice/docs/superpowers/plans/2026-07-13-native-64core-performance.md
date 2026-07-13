# Native 64-Core Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development task-by-task.

**Goal:** Make Native S-parameter fitting expose a reproducible thread contract and phase-level performance evidence on large, easy-to-fit cases before changing algorithms or rewriting language runtimes.

**Architecture:** Run each fit in a fresh child process with an explicit BLAS thread budget, capture phase timings and process CPU/RSS samples, and persist a machine-readable benchmark matrix. Keep all fit math and quality gates unchanged. Use the matrix to decide whether response-block parallelism or a compiled hot path is justified.

**Tech Stack:** Python 3, NumPy/SciPy BLAS, psutil, existing Native fitting/report pipeline, pytest.

## Global Constraints

- Cases: Test3 s166 primary, Test11 s163 replication, Test16 s91 regression; all use `passivity=enforce` and the existing signoff quality contract.
- Thread budgets: `1, 8, 16, 32, 64`; set `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `NUMEXPR_NUM_THREADS` only in the child process.
- No change to input samples, pole search, residue LS, passivity math, target/order policy, or output quality is allowed in the profiler phase.
- Every comparison records input SHA, code identity, requested/effective threads, per-phase wall time, CPU time/utilization, peak RSS, result quality, and command exit status.

### Task 1: Child-process thread and phase contract

**Files:**
- Create `src/agent_spice/sparam/performance.py`
- Modify `src/agent_spice/sparam/fitting.py`
- Test `tests/test_sparam_performance.py`

- [ ] Add a phase recorder for load, Native fitting, passivity check, enforcement, export and total elapsed time.
- [ ] Add a bounded CPU/RSS sampler that reports aggregate process CPU seconds and average/peak utilization without affecting fitting semantics.
- [ ] Add tests proving phase sums, JSON-safe serialization, and no semantic change with profiling disabled.

### Task 2: Benchmark runner and fixed matrix

**Files:**
- Create `scripts/sparam_native_thread_benchmark.py`
- Create `tests/test_sparam_native_thread_benchmark.py`
- Create `scripts/sparam_native_thread_cases.json`

- [ ] Spawn a fresh Python child per case/thread budget with explicit BLAS variables, timeout, process-tree RSS and captured stdout/stderr.
- [ ] Reject a result whose input SHA, quality outcome or selected effective order differs from the one-thread reference.
- [ ] Support resumable per-case/thread artifacts and render a Markdown matrix from JSON only.
- [ ] Test environment propagation, resume identity, quality mismatch rejection and result aggregation with fake child processes.

### Task 3: Evidence-driven optimization decision

**Files:**
- Create `docs/sparam-native-64core-performance.md`
- Modify `docs/sparam-fit-performance.md`

- [ ] Run the complete 1/8/16/32/64 matrix on available Test3/Test11/Test16 inputs.
- [ ] Identify the largest phase and scaling saturation point from artifacts; do not claim a speedup from a different quality result.
- [ ] Implement only the supported optimization: BLAS runtime policy if dense LS dominates; otherwise a separately reviewed response-block/compiled-kernel proposal.
- [ ] Record measured speedup, quality equality, CPU utilization, RSS and recommendation.
