# Modal Z-Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build and evaluate an isolated reduced-basis Z-domain rational fitting prototype for 30-port PDN S-parameter data.

**Architecture:** Add a new `agent_spice.sparam.modal` module for reduced-basis construction, fixed-pole scalar rational fitting, Z reconstruction, and metrics. Add `agent_spice.sparam.modal_report` for JSON/HTML artifacts, and a CLI command `fit-modal-z` that writes report-only optimization artifacts without touching the existing `fit-sparam` SPICE path.

**Tech Stack:** Python, NumPy, scikit-rf, pytest, existing Agent-Spice CLI/report patterns.

---

### Task 1: Modal Z Core

**Files:**
- Create: `src/agent_spice/sparam/modal.py`
- Test: `tests/test_sparam_modal.py`

- [x] **Step 1: Write failing tests for core metrics and basis reconstruction**

Add tests:

```python
def test_z_log_magnitude_rms_error_is_zero_for_identical_arrays():
    z = np.array([[[1.0 + 0j, 0.1 + 0j], [0.1 + 0j, 2.0 + 0j]]])
    assert z_log_magnitude_rms_error(z, z) == 0.0
```

```python
def test_modal_projection_reconstructs_rank_one_z_matrix():
    q = np.array([[1.0], [0.0]], dtype=complex)
    z = np.array([[[3.0 + 0j, 0.0 + 0j], [0.0 + 0j, 0.0 + 0j]]])
    basis = build_modal_basis(z, mode_count=1, decomposition="svd")
    reduced = project_z_to_basis(z, basis)
    reconstructed = reconstruct_z_from_basis(reduced, basis)
    assert z_log_magnitude_rms_error(z[:, :1, :1], reconstructed[:, :1, :1]) < 1e-12
```

- [x] **Step 2: Run red tests**

Run: `python -m pytest tests/test_sparam_modal.py -v`

Expected: FAIL because `agent_spice.sparam.modal` does not exist.

- [x] **Step 3: Implement core functions**

Implement:

- `ModalZFitConfig`
- `ModalZFitResult`
- `z_log_magnitude_rms_error(original_z, fitted_z)`
- `build_modal_basis(z_samples, mode_count, decomposition, basis_indices=None)`
- `project_z_to_basis(z_samples, basis)`
- `reconstruct_z_from_basis(reduced_z, basis)`

Validation:

- `mode_count >= 1`
- `mode_count <= nports`
- `decomposition in {"svd", "hermitian"}`
- input Z shape must be `(nfreq, nports, nports)`

- [x] **Step 4: Run core tests**

Run: `python -m pytest tests/test_sparam_modal.py -v`

Expected: PASS for metric and projection tests.

### Task 2: Fixed-Pole Reduced Matrix Fitting

**Files:**
- Modify: `src/agent_spice/sparam/modal.py`
- Test: `tests/test_sparam_modal.py`

- [x] **Step 1: Write failing tests for fixed-pole fitting**

Add tests:

```python
def test_fixed_pole_fit_preserves_constant_response():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    values = np.array([2.5 + 0.2j] * len(freqs))
    fitted = fit_fixed_pole_response(freqs, values, scalar_fit_order=4)
    assert np.max(np.abs(fitted - values)) < 1e-10
```

```python
def test_fit_reduced_modal_z_reports_basis_and_fit_error():
    freqs = np.array([0.0, 1e6, 2e6, 3e6])
    z = np.zeros((len(freqs), 2, 2), dtype=complex)
    z[:, 0, 0] = 2.0 + 0.1j
    result = fit_reduced_modal_z(freqs, z, ModalZFitConfig(mode_count=1, scalar_fit_order=4, decomposition="svd"))
    assert result.mode_count == 1
    assert result.z_log_magnitude_rms_error < 1e-10
    assert result.basis_projection_z_log_magnitude_rms_error < 1e-10
```

- [x] **Step 2: Run red tests**

Run: `python -m pytest tests/test_sparam_modal.py -v`

Expected: FAIL because fitting functions are missing.

- [x] **Step 3: Implement fixed-pole LS**

Implement:

- `stable_poles(freqs, scalar_fit_order, damping=0.05)`
- `fit_fixed_pole_response(freqs, values, scalar_fit_order, damping=0.05, fit_indices=None)`
- `fit_reduced_modal_z(freqs, z, config)`

Implementation details:

- Use stable complex poles `p = -damping*w + 1j*w` and conjugates.
- Include a constant term.
- Normalize LS columns before `np.linalg.lstsq()`.
- Fit each entry of `Zr(f)` independently.
- Evaluate fitted reduced traces at all frequencies.

- [x] **Step 4: Run fixed-pole tests**

Run: `python -m pytest tests/test_sparam_modal.py -v`

Expected: PASS.

### Task 3: Modal Z Reports and CLI

**Files:**
- Create: `src/agent_spice/sparam/modal_report.py`
- Modify: `src/agent_spice/cli.py`
- Test: `tests/test_cli_fit_modal_z.py`

- [x] **Step 1: Write failing CLI/report test**

Add a test using `tests/fixtures/sparam/simple_through.s2p`:

```python
def test_fit_modal_z_cli_writes_json_and_html_reports(tmp_path):
    report = tmp_path / "modal_report.json"
    html = tmp_path / "modal_report.html"
    exit_code = main([
        "fit-modal-z",
        "tests/fixtures/sparam/simple_through.s2p",
        "--report",
        str(report),
        "--html-report",
        str(html),
        "--mode-count",
        "1",
        "--scalar-fit-order",
        "4",
        "--decomposition",
        "svd",
    ])
    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["mode"] == "modal_z"
    assert payload["z_log_magnitude_rms_error"] >= 0.0
    assert "Modal Z-Fit Report" in html.read_text(encoding="utf-8")
```

- [x] **Step 2: Run red CLI test**

Run: `python -m pytest tests/test_cli_fit_modal_z.py -v`

Expected: FAIL because `fit-modal-z` does not exist.

- [x] **Step 3: Implement report writers and CLI**

Implement:

- `modal_report_to_dict(result, touchstone_path, config)`
- `write_modal_z_json_report(result, path, touchstone_path, config)`
- `write_modal_z_html_report(result, path, touchstone_path, config)`
- CLI command `fit-modal-z`

CLI must support:

- `--report`
- `--html-report`
- `--mode-count`
- `--scalar-fit-order`
- `--frequency-sample-count`
- `--decomposition svd|hermitian`
- `--pole-damping`

- [x] **Step 4: Run CLI/report tests**

Run: `python -m pytest tests/test_sparam_modal.py tests/test_cli_fit_modal_z.py -v`

Expected: PASS.

### Task 4: 30-Port Optimization Report

**Files:**
- Create: `docs/sparam-modal-z-optimization-report.md`

- [x] **Step 1: Run 30-port modal prototype**

Run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p/fit_report.json `
  --html-report runs-sparam/modal-z-30p/fit_report.html `
  --decomposition svd `
  --mode-count 8 `
  --scalar-fit-order 24 `
  --frequency-sample-count 256
```

Expected: exit code 0 and both reports written.

- [x] **Step 2: Write optimization report**

Write `docs/sparam-modal-z-optimization-report.md` with:

- current 20/40 element-VF baseline from `runs-sparam/order-sweep-30p-z/partial_summary.csv`
- modal prototype settings
- modal prototype metrics
- interpretation: continue, revise, or stop modal-Z
- next recommended algorithm step

- [x] **Step 3: Run full verification**

Run:

```powershell
python -m pytest -v
git diff --check
```

Expected: all tests pass; no whitespace errors.

### Task 5: Adaptive Reduced-Z Follow-Up

**Files:**
- Modify: `src/agent_spice/sparam/modal.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `src/agent_spice/sparam/modal_report.py`
- Modify: `tests/test_sparam_modal.py`
- Modify: `tests/test_cli_fit_modal_z.py`
- Modify: `docs/sparam-modal-z-optimization-report.md`

- [x] **Step 1: Add reduced vector fitting controls**

Add `reduced_fit_method="vector"` and CLI controls for reduced VF pole/init/iteration/target-error settings.

- [x] **Step 2: Test direct reduced multiport VF**

Result: 30-port `mode=4/order=12/sample=96` exceeded 180s and was terminated. Direct scikit-rf reduced multiport VF is too slow for this inner loop.

- [x] **Step 3: Add shared-poles surrogate path**

Add `shared-poles`: fit scalar modal surrogates with VF to identify common poles, then fit all reduced entries with LS.

Result: still exceeded 180s on 30-port diagnostic because scalar VF remained too slow.

- [x] **Step 4: Add peak-poles path**

Add `peak-poles`: select common poles directly from modal Z magnitude peaks, mix with full-band stable poles, and use relative-weighted LS.

- [x] **Step 5: Run 30-port diagnostics**

Initial best run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak16-hermitian/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak16-hermitian/fit_report.html `
  --decomposition hermitian `
  --mode-count 16 `
  --scalar-fit-order 32 `
  --frequency-sample-count 192 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 4 `
  --pole-damping 0.08
```

Result: Z log-magnitude RMS = 0.6307 decades, better than element-VF order40 baseline 0.7582 decades.

- [x] **Step 6: Add tunable relative weighting**

Add `relative_weight_power` to `ModalZFitConfig`, CLI, JSON config, and HTML report. This keeps the log-oriented LS objective tunable instead of hard-coding `1 / |Z|`.

Updated best run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak-v2/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak-v2/fit_report.html `
  --decomposition hermitian `
  --mode-count 20 `
  --scalar-fit-order 44 `
  --frequency-sample-count 256 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.18 `
  --relative-weight-power 0.6
```

Result: Z log-magnitude RMS = 0.5549 decades and diagonal Z log-magnitude RMS = 0.3267 decades.

- [x] **Step 7: Add modal-Z HTML comparison plots**

Store original Z and frequencies in `ModalZFitResult`, then render worst-pair original-vs-fitted |Z| SVG charts on log frequency/log Ohm axes in the modal HTML report.

- [x] **Step 8: Add full-projected relative weighting**

Add `relative_weight_mode="full-projected"` so full-matrix Z log-oriented weights are projected back into reduced entries through the modal basis energy. This is cheaper than a fully coupled LS solve but better aligned with the final metric than per-trace weighting.

Result: `runs-sparam/modal-z-30p-peak-v3/fit_report.json` reaches Z log-magnitude RMS = 0.5184 decades.

- [x] **Step 9: Add configurable basis sampling**

Add `basis_frequency_sample_count` and `basis_frequency_sampling` to make basis construction reproducible from CLI.

Best current run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak-v4/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak-v4/fit_report.html `
  --decomposition hermitian `
  --mode-count 20 `
  --basis-frequency-sample-count 17 `
  --basis-frequency-sampling linear `
  --scalar-fit-order 44 `
  --frequency-sample-count 256 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.18 `
  --relative-weight-power 0.9 `
  --relative-weight-mode full-projected
```

Result: Z log-magnitude RMS = 0.4993 decades and diagonal Z log-magnitude RMS = 0.3218 decades.

- [x] **Step 10: Add iterative full-projected reweighting**

Add `relative_weight_iterations` and `relative_weight_update` to repeat reduced-entry LS with weights derived from the previous fitted Z. The best tested update rule is `max(original, fitted)`, which avoids over-weighting entries where the previous fit undershoots.

Best current run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak-v5/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak-v5/fit_report.html `
  --decomposition hermitian `
  --mode-count 28 `
  --basis-frequency-sample-count 21 `
  --basis-frequency-sampling linear `
  --scalar-fit-order 52 `
  --frequency-sample-count 256 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.18 `
  --relative-weight-power 1.0 `
  --relative-weight-mode full-projected `
  --relative-weight-iterations 2 `
  --relative-weight-update max
```

Result: Z log-magnitude RMS = 0.4770 decades and diagonal Z log-magnitude RMS = 0.1104 decades.

- [x] **Step 11: Evaluate targeted off-diagonal weighting**

Tested top-k off-diagonal pair weighting after the first full-projected iteration. The improvement was negligible: best targeted run was about 0.4768 decades and later iterations rebounded. Do not add targeted pair weighting yet.

The better V6 candidate came from local damping/power/order tuning:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak-v6/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak-v6/fit_report.html `
  --decomposition hermitian `
  --mode-count 28 `
  --basis-frequency-sample-count 21 `
  --basis-frequency-sampling linear `
  --scalar-fit-order 56 `
  --frequency-sample-count 256 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.12 `
  --relative-weight-power 0.9 `
  --relative-weight-mode full-projected `
  --relative-weight-iterations 2 `
  --relative-weight-update max
```

Result: Z log-magnitude RMS = 0.4729 decades and diagonal Z log-magnitude RMS = 0.1082 decades.

- [x] **Step 12: Include raw low-frequency points in the fit sample**

The raw Touchstone frequency axis includes `0.1 Hz`, but the previous 256-point linear fit sample skipped both `0.1 Hz` and `0.120226... Hz`. This meant the report evaluated a raw data point that was not part of the reduced LS training set.

Added `frequency_sample_head_count` and CLI option `--frequency-sample-head-count` to force the first N raw frequency points into the fit sample.

Best current run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-peak-v7/fit_report.json `
  --html-report runs-sparam/modal-z-30p-peak-v7/fit_report.html `
  --decomposition hermitian `
  --mode-count 28 `
  --basis-frequency-sample-count 21 `
  --basis-frequency-sampling linear `
  --scalar-fit-order 56 `
  --frequency-sample-count 256 `
  --frequency-sample-head-count 3 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.12 `
  --relative-weight-power 0.9 `
  --relative-weight-mode full-projected `
  --relative-weight-iterations 2 `
  --relative-weight-update max
```

Result: Z log-magnitude RMS = 0.4439 decades and diagonal Z log-magnitude RMS = 0.1081 decades. This confirms the low-frequency miss was a sampling issue, not an external interpolation issue.

- [x] **Step 13: Run cross-case modal-Z sanity checks**

Ran the same modal-Z/peak-poles family on the other `user_input/spara` Touchstone files:

| Case | Sampling | Z log RMS | Projection RMS | Diagnosis |
| --- | --- | ---: | ---: | --- |
| 19p withcap | 256 + head3 | 2.8056 | 0.2499 | fit-limited |
| 19p withcap | full raw | 2.9473 | 0.2499 | fit-limited, pole/weighting failure |
| 60p | 256 + head3 | 1.2496 | 0.5797 | sample-limited |
| 60p | full raw | 0.5812 | 0.5797 | basis-limited after full LS |
| 91p | full raw | 0.4790 | 0.4626 | basis-limited, acceptable exploratory result |
| 163p | full raw | 1.6603 | 1.6620 | basis projection failure |
| 166p | full raw | 1.4817 | 1.4816 | basis projection failure |

Conclusion: do not generalize 30p V7. The next algorithm step should split the cases into fit-limited and basis-limited tracks. 19p withcap is the best near-term pole/weighting debugging target because the basis projection floor is acceptable but the reduced rational fit fails badly.

- [x] **Step 14: Add bounded auto-order selection**

The previous modal-Z runs used fixed `scalar_fit_order` values. Added bounded auto-order support so the prototype can choose the smallest candidate order that meets a Z-domain threshold without reverting to scikit-rf's high-order full-matrix `auto_fit` path.

New CLI controls:

- `--auto-order`
- `--auto-order-candidates`
- `--auto-order-max-z-log-rms-error`
- `--auto-order-max-diag-z-log-rms-error`

Behavior:

- If a candidate passes the configured threshold, stop at the first passing order.
- If no candidate passes, return the best observed candidate.
- JSON/HTML reports include an `auto_order_trials` table.

30-port bounded auto run:

```powershell
python -m agent_spice.cli fit-modal-z `
  user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam/modal-z-30p-auto-v1/fit_report.json `
  --html-report runs-sparam/modal-z-30p-auto-v1/fit_report.html `
  --decomposition hermitian `
  --mode-count 28 `
  --basis-frequency-sample-count 21 `
  --basis-frequency-sampling linear `
  --scalar-fit-order 56 `
  --frequency-sample-count 256 `
  --frequency-sample-head-count 3 `
  --reduced-fit-method peak-poles `
  --shared-pole-trace-count 2 `
  --pole-damping 0.12 `
  --relative-weight-power 0.9 `
  --relative-weight-mode full-projected `
  --relative-weight-iterations 2 `
  --relative-weight-update max `
  --auto-order `
  --auto-order-max-z-log-rms-error 0.5
```

Result: candidates `8,12,16,24,32,44`; first passing order is `44`, with Z log RMS = 0.4870 decades and diagonal Z log RMS = 0.1355 decades.

19-port bounded auto run confirms the failure is not solved by automatic order selection: candidates `8,12,16,24,32,44,56` all fail the 0.5-decade target; best observed is order 56 with Z log RMS = 2.9473 decades.

## Self-Review

- Spec coverage: implements isolated modal-Z prototype, report-only CLI, 30-port optimization report, and a continue/stop decision.
- Placeholder scan: no TBD/TODO.
- Type consistency: plan uses `ModalZFitConfig`, `ModalZFitResult`, and `fit-modal-z` consistently.
