# Z-Domain PDN Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PDN S-parameter fit assessment order-aware and Z-domain-first, while adding a memory-bounded streaming passivity checker.

**Architecture:** Keep scikit-rf VectorFitting as the current fitting engine. Add Z-domain quality inputs to `agent_spice.sparam.quality`, add streaming passivity utilities in a focused module, and add order sweep orchestration to `agent_spice.sparam.benchmark` and the CLI.

**Tech Stack:** Python, NumPy, scikit-rf, pytest, existing `agent_spice.sparam` modules.

---

### Task 1: Z-Domain Quality Gate

**Files:**
- Modify: `src/agent_spice/sparam/quality.py`
- Modify: `src/agent_spice/sparam/fitting.py`
- Test: `tests/test_sparam_quality.py`
- Test: `tests/test_sparam_fitting.py`

- [x] **Step 1: Write failing quality tests**

Add tests proving `build_quality_report()` accepts `z_comparison_rms_error`, `z_comparison_rms_limit`, and `z_required_for_signoff`.

```python
def test_build_quality_report_signoff_uses_z_domain_threshold():
    report = build_quality_report(
        network=QualityNetwork(),
        frequency_points=3,
        fit_frequency_points=3,
        comparison_rms_error=0.2,
        z_comparison_rms_error=0.01,
        passive_after_enforce=True,
        passivity_violations_after=[],
        enforce_passivity=True,
        poles=np.array([-1e6 + 0j]),
        profile="signoff",
        comparison_rms_limit=0.05,
        z_comparison_rms_limit=0.05,
        z_required_for_signoff=True,
    )
    payload = report.to_dict()
    assert payload["status"] == "PASS"
    assert "comparison_rms_error" in payload["warnings"]
    assert "z_comparison_rms_error" not in payload["blocking_reasons"]
```

- [x] **Step 2: Run red test**

Run: `python -m pytest tests/test_sparam_quality.py::test_build_quality_report_signoff_uses_z_domain_threshold -v`

Expected: FAIL because `build_quality_report()` does not accept the new Z arguments.

- [x] **Step 3: Implement minimal Z diagnostics**

Add Z arguments to `build_quality_report()` and `_check_fit_metrics()`. Add a `z_comparison_rms_error` diagnostic. When `z_required_for_signoff=True`, signoff is blocked by missing or over-limit Z error. When Z is required, S-domain `comparison_rms_error` over limit should be WARN, not FAIL.

- [x] **Step 4: Wire fitting config**

Add `max_z_comparison_rms_error: float | None = None` and `z_required_for_signoff: bool = False` to `SParamFitConfig`. Pass `result.z_comparison_rms_error` to `build_quality_report()`.

- [x] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_sparam_quality.py tests/test_sparam_fitting.py -v`

Expected: PASS.

### Task 2: Streaming Passivity Checker

**Files:**
- Create: `src/agent_spice/sparam/passivity.py`
- Modify: `src/agent_spice/sparam/fitting.py`
- Test: `tests/test_sparam_passivity.py`

- [x] **Step 1: Write failing streaming checker tests**

Add tests for a function named `sample_streaming_singular_values(s_provider, freqs, nports, chunk_size, epsilon)` that returns `max_sigma`, `max_sigma_frequency_hz`, and sampled violation bands without storing all frequency matrices.

```python
def test_streaming_passivity_checker_chunks_frequency_samples():
    calls = []
    freqs = np.array([0.0, 1.0, 2.0, 3.0])

    def provider(chunk_freqs):
        calls.append(list(chunk_freqs))
        matrices = np.zeros((len(chunk_freqs), 2, 2), dtype=complex)
        matrices[:, 0, 0] = [0.5 if f != 2.0 else 1.2 for f in chunk_freqs]
        matrices[:, 1, 1] = 0.5
        return matrices

    result = sample_streaming_singular_values(provider, freqs, nports=2, chunk_size=2, epsilon=1e-6)

    assert calls == [[0.0, 1.0], [2.0, 3.0]]
    assert result.max_sigma == 1.2
    assert result.max_sigma_frequency_hz == 2.0
    assert result.violation_bands_hz == [[2.0, 2.0]]
```

- [x] **Step 2: Run red test**

Run: `python -m pytest tests/test_sparam_passivity.py::test_streaming_passivity_checker_chunks_frequency_samples -v`

Expected: FAIL because the module/function does not exist.

- [x] **Step 3: Implement streaming checker**

Create `PassivitySampleReport` dataclass and `sample_streaming_singular_values()`. Validate `chunk_size >= 1`, `freqs` non-empty, and provider output shape `(len(chunk_freqs), nports, nports)`.

- [x] **Step 4: Add vector-fit adapter**

Add `sample_vector_fit_passivity(vector_fit, freqs, nports, chunk_size, epsilon)` that builds S matrices by calling existing model response evaluation per chunk. Use it only for reporting; do not replace `VectorFitting.passivity_enforce()`.

- [x] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_sparam_passivity.py tests/test_sparam_fitting.py -v`

Expected: PASS.

### Task 3: Order Sweep Benchmark

**Files:**
- Modify: `src/agent_spice/sparam/benchmark.py`
- Modify: `src/agent_spice/cli.py`
- Test: `tests/test_sparam_benchmark.py`
- Test: `tests/test_cli_benchmark_sparam.py`

- [x] **Step 1: Write failing benchmark tests**

Add a unit test for `run_order_sweep()` using monkeypatched `fit_touchstone_to_spice()` and orders `[20, 40]`. Assert it produces per-order rows containing `model_order_max`, `z_comparison_rms_error`, `quality_status`, and artifacts under separate directories.

- [x] **Step 2: Run red test**

Run: `python -m pytest tests/test_sparam_benchmark.py::test_run_order_sweep_records_each_order -v`

Expected: FAIL because `run_order_sweep()` does not exist.

- [x] **Step 3: Implement sweep API**

Add `run_order_sweep(case, output_root, orders)` that clones `case.fit_config` with each `model_order_max`, runs fit, and returns normal benchmark result rows with `sweep_model_order_max`.

- [x] **Step 4: Add CLI flag**

Add `benchmark-sparam --order-sweep 20,40,60`. Reject use without `--run-fit`. Print rows as `case_id/order`.

- [x] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_sparam_benchmark.py tests/test_cli_benchmark_sparam.py -v`

Expected: PASS.

### Task 4: Documentation and Verification

**Files:**
- Modify: `docs/sparam-fit-performance.md`
- Modify: `docs/sparam-batch-fit-results.md`

- [x] **Step 1: Document new workflow**

Add the recommended PDN flow:

```powershell
python -m agent_spice.cli benchmark-sparam `
  --manifest benchmarks/sparam/cases.yaml `
  --case 5power_30port_wocap_bandpass_scaled `
  --run-fit `
  --order-sweep 20,40,60,80 `
  --output runs-sparam/order-sweep-30p.jsonl `
  --csv runs-sparam/order-sweep-30p.csv `
  --output-root runs-sparam/order-sweep-30p
```

- [x] **Step 2: Run full verification**

Run:

```powershell
python -m pytest -v
git diff --check
```

Expected: all tests pass; no whitespace errors.
