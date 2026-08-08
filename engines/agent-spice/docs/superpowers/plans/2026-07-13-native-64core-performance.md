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

- [x] Reuse Native report's fit/check/enforcement timings and add a total wall/CPU/RSS recorder in an external child-process harness; this intentionally avoids touching fitting semantics.
- [x] Add a bounded CPU/RSS sampler that reports aggregate process CPU seconds and peak utilization without affecting fitting semantics.
- [x] Add unit tests for phase primitives and environment validation.

### Task 2: Benchmark runner and fixed matrix

**Files:**
- Create `scripts/sparam_native_thread_benchmark.py`
- Create `tests/test_sparam_native_thread_benchmark.py`
- Create `scripts/sparam_native_thread_cases.json`

- [x] Spawn a fresh Python child per case/thread budget with explicit BLAS variables, timeout, RSS and captured stdout/stderr.
- [x] Reject a result whose input SHA, quality outcome, selected effective order or material RMS/passivity result differs from the one-thread reference.
- [x] Support resumable per-case/thread artifacts and render a Markdown matrix from JSON only.
- [x] Test environment propagation, resume identity, quality mismatch rejection and result aggregation with fake child processes.

### Task 3: Evidence-driven optimization decision

**Files:**
- Create `docs/sparam-native-64core-performance.md`
- Modify `docs/sparam-fit-performance.md`

- [x] Run the complete 1/8/16/32/64 matrix on available Test3/Test11/Test16 inputs.
- [x] Identify the largest phase and scaling saturation point from artifacts; do not claim a speedup from a different quality result.
- [x] Implement the evidence-supported BLAS runtime policy through `agent-spice-native --blas-threads` (default `1`).
- [x] Record measured speedup, bounded floating-point equality, CPU utilization, RSS and recommendation.
