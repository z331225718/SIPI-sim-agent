# Target-Driven S-Parameter Fitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `fit-sparam TOUCHSTONE --rms-target TARGET --passivity off|check|enforce --max-order N`, selecting the smallest effective common-pole order whose final model meets the requested contract and producing auditable IdEM/native parity metrics.

**Architecture:** Add a small target-search domain module that owns target validation, trial records, and non-monotonic order scheduling. Keep single-order fitting in `fitting.py`, but expose pre/final metrics and phase timings so a target evaluator can apply the three passivity policies without duplicating fitting logic. The CLI becomes a thin target-driven entry point; a separate benchmark summarizer applies the fixed parity ratios to native and IdEM reports.

**Tech Stack:** Python 3.11+, dataclasses, NumPy/SciPy, existing native VF and Hamiltonian passivity engine, pytest, JSON/HTML reports, PowerShell benchmark commands.

## Global Constraints

- Production fitting backend remains `idem-fast`/native VF; no retired fitting algorithm returns to the public CLI.
- Mean RMS is `sqrt(mean(abs(S_fit - S_raw) ** 2))` over all original frequencies and all channels.
- Effective order is `real_poles + 2 * complex_pairs`.
- Production fitting uses the complete raw frequency grid.
- `enforce` accepts a trial only from post-enforcement RMS and fresh Hamiltonian/adaptive full-frequency validation.
- `check` non-passivity is a warning and does not force a higher order.
- Failed target search must not write a best-effort model to the requested production output path.
- No subagents are used for execution; each task receives an inline code review before the next task.

---

### Task 1: Target Domain Types and Non-Monotonic Scheduler

**Files:**
- Create: `src/agent_spice/sparam/target_fit.py`
- Create: `tests/test_sparam_target_fit.py`

**Interfaces:**
- Produces: `SParamFitTarget(mean_rms, passivity="check", max_order=40, passivity_epsilon=1e-6)`.
- Produces: `SParamOrderTrial` with phase metrics, target status, and optional in-memory payload.
- Produces: `SParamTargetSearchResult(target, trials, selected_trial, stop_reason)`.
- Produces: `run_target_order_search(target, evaluate_order) -> SParamTargetSearchResult`.

- [ ] **Step 1: Write failing validation and scheduler tests**

```python
def test_target_rejects_invalid_values():
    with pytest.raises(ValueError):
        SParamFitTarget(mean_rms=0.0)
    with pytest.raises(ValueError):
        SParamFitTarget(mean_rms=0.001, passivity="repair")


def test_scheduler_backfills_odd_order_after_first_even_pass():
    outcomes = {4: False, 6: False, 8: True, 7: True}
    calls = []

    def evaluate(order):
        calls.append(order)
        return make_trial(order, target_met=outcomes[order])

    result = run_target_order_search(
        SParamFitTarget(mean_rms=0.001, max_order=10),
        evaluate,
    )

    assert calls == [4, 6, 8, 7]
    assert result.selected_trial.requested_order == 7
    assert result.stop_reason == "target_met"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_sparam_target_fit.py -q`

Expected: import failure because `agent_spice.sparam.target_fit` does not exist.

- [ ] **Step 3: Implement immutable target, serializable trial, and scheduler**

The scheduler evaluates ascending even orders from 4, stops on the first passing even order, then evaluates untested integer orders between the last failed even order and the passing order. Cache trials by requested order and select the passing trial with the smallest `(effective_order, requested_order)` tuple.

For `max_order < 4`, evaluate each order from 1 through `max_order` so the API remains defined for small synthetic fixtures.

- [ ] **Step 4: Add tests for no duplicate evaluation and exhausted search**

```python
def test_scheduler_evaluates_each_order_once():
    result = run_target_order_search(target, evaluator)
    assert len(calls) == len(set(calls))


def test_scheduler_reports_target_not_met():
    result = run_target_order_search(target, lambda order: make_trial(order, target_met=False))
    assert result.selected_trial is None
    assert result.stop_reason == "target_not_met_before_max_order"
```

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_sparam_target_fit.py -q`

Expected: all tests pass.

- [ ] **Step 6: Review scheduler ordering and commit**

Review that non-monotonic outcomes cannot be binary-searched, every order is cached, and `to_dict()` excludes the in-memory model payload.

```powershell
git add src/agent_spice/sparam/target_fit.py tests/test_sparam_target_fit.py
git commit -m "feat: add target-driven order scheduler"
```

---

### Task 2: Exact Effective-Order Trials and Phase Metrics

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `tests/test_sparam_fitting.py`

**Interfaces:**
- Updates: `_native_manual_auto_order_config(base_config, order)` must request an exact topology.
- Adds to `SParamFitConfig`: `passivity_enforce_rms_target: float | None = None`.
- Adds to `SParamFitResult`: pre-enforcement mean RMS, phase timings, and enforcement-skip reason.

- [ ] **Step 1: Write failing exact-order topology tests**

```python
@pytest.mark.parametrize(
    ("order", "real_count", "complex_count"),
    [(4, 0, 2), (5, 1, 2), (6, 2, 2), (8, 4, 2), (10, 6, 2)],
)
def test_native_order_config_requests_exact_effective_order(order, real_count, complex_count):
    trial = _native_manual_auto_order_config(idem_fast_config(), order)
    assert trial.n_poles_real == real_count
    assert trial.n_poles_cmplx == complex_count
    assert trial.native_post_relocation_effective_order_max == order
```

- [ ] **Step 2: Verify RED and implement exact topology mapping**

Use two complex pairs whenever `order >= 4`, one pair for orders 2-3, and fill the remaining state order with real poles. Set both `native_post_relocation_effective_order_max=order` and `native_effective_complex_pole_count=complex_count`.

- [ ] **Step 3: Write failing enforcement cost-gate test**

Create a small fake vector-fit path whose pre-enforcement mean RMS is `0.01` and target is `0.001`. Assert passivity enforcement is not called, `pre_enforcement_mean_rms_error == final_mean_rms_error`, and `passivity_enforcement_skip_reason == "pre_rms_above_target"`.

- [ ] **Step 4: Instrument fit/check/enforce phases**

In `fit_touchstone_to_spice()`:

```python
fit_started = time.perf_counter()
_fit_model(vector_fit, config)
fit_seconds = time.perf_counter() - fit_started

pre_sum_rms = _comparison_rms_error(network, vector_fit, config.parameter_type)
pre_mean_rms = _mean_rms_error_from_sum_style(pre_sum_rms, network.nports)
should_enforce = config.enforce_passivity and not (
    config.passivity_enforce_rms_target is not None
    and pre_mean_rms is not None
    and pre_mean_rms > config.passivity_enforce_rms_target
)
```

Accumulate all passivity checker calls into `check_seconds` and all enforcement calls into `enforce_seconds`. Replace enforcement branch conditions with `should_enforce`, while preserving fresh final checking when `check_passivity=True`.

- [ ] **Step 5: Extend result/report serialization**

Add:

```text
pre_enforcement_mean_rms_error
fit_seconds
check_seconds
enforce_seconds
passivity_enforcement_skip_reason
```

Keep `comparison_mean_rms_error` as the final-model RMS.

- [ ] **Step 6: Run fitting regression tests**

Run: `python -m pytest tests/test_sparam_fitting.py tests/test_sparam_native_vf.py -q`

Expected: all tests pass.

- [ ] **Step 7: Review timing boundaries and commit**

```powershell
git add src/agent_spice/sparam/fitting.py tests/test_sparam_fitting.py tests/test_sparam_native_vf.py
git commit -m "feat: expose exact-order fitting trial metrics"
```

---

### Task 3: Unified Off, Check, and Enforce Trial Evaluator

**Files:**
- Modify: `src/agent_spice/sparam/target_fit.py`
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `tests/test_sparam_target_fit.py`
- Modify: `tests/test_sparam_fitting.py`

**Interfaces:**
- Produces: `fit_touchstone_to_spice_target(touchstone_path, output_path, *, target, config, report_path, html_report_path, log_path) -> SParamTargetSearchResult`.
- Consumes: `fit_touchstone_to_spice()` as the single-order evaluator.

- [ ] **Step 1: Write failing policy acceptance tests**

Use synthetic `SParamFitResult` payloads:

```python
def test_off_uses_final_rms_only():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="off"),
        make_fit_result(final_rms=0.0009, final_sigma=None),
        requested_order=8,
    )
    assert trial.target_met is True
    assert trial.rejection_reason is None


def test_check_accepts_nonpassive_rms_target_with_warning():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="check"),
        make_fit_result(final_rms=0.0009, final_sigma=1.02, passive_after=False),
        requested_order=8,
    )
    assert trial.target_met is True
    assert trial.status == "PASS_WITH_PASSIVITY_WARNING"


def test_enforce_requires_final_rms_and_final_sigma():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="enforce"),
        make_fit_result(final_rms=0.0009, final_sigma=1.02, passive_after=False),
        requested_order=8,
    )
    assert trial.target_met is False
    assert trial.rejection_reason == "passivity_enforcement_failed"


def test_enforce_rejects_pre_rms_pass_final_rms_fail():
    trial = trial_from_fit_result(
        SParamFitTarget(0.001, passivity="enforce"),
        make_fit_result(pre_rms=0.0008, final_rms=0.0011, final_sigma=0.999, passive_after=True),
        requested_order=8,
    )
    assert trial.target_met is False
    assert trial.rejection_reason == "final_rms_above_target"
```

Expected statuses:

```text
off pass: PASS
check non-passive RMS pass: PASS_WITH_PASSIVITY_WARNING
enforce final non-passive: target_met=False, passivity_enforcement_failed
enforce final RMS high: target_met=False, final_rms_above_target
```

- [ ] **Step 2: Implement `trial_from_fit_result()`**

Map the single-order result into `SParamOrderTrial`. Reject any trial whose `expanded_model_order` differs from the requested order with `effective_order_mismatch`.

- [ ] **Step 3: Implement target orchestration**

For each scheduler order:

1. Build an exact-order native config.
2. Set passivity booleans from the policy.
3. Set `passivity_enforce_rms_target=target.mean_rms` only for `enforce`.
4. Write trial artifacts under `<output_stem>_order<order>/`.
5. Convert the result to a trial and return it to the scheduler.

On success copy only the selected trial model to the requested output. On failure remove a pre-existing requested output and retain trial artifacts plus top-level reports.

- [ ] **Step 4: Add final top-level result serialization**

The top-level JSON must contain:

```text
rms_target
passivity_policy
max_order
selected_effective_order
target_met
target_stop_reason
order_trials
benchmark_contract_version = "sparam_target_v1"
```

- [ ] **Step 5: Test output absence on failure**

Pre-create the requested output, run an exhausted fake search, and assert the requested output does not exist afterward while JSON/HTML reports do exist.

- [ ] **Step 6: Run target and fitting tests**

Run: `python -m pytest tests/test_sparam_target_fit.py tests/test_sparam_fitting.py -q`

- [ ] **Step 7: Review final-vs-pre metric use and commit**

```powershell
git add src/agent_spice/sparam/target_fit.py src/agent_spice/sparam/fitting.py tests/test_sparam_target_fit.py tests/test_sparam_fitting.py
git commit -m "feat: evaluate target-driven passivity policies"
```

---

### Task 4: Public CLI and Compatibility Aliases

**Files:**
- Modify: `src/agent_spice/cli.py`
- Modify: `tests/test_cli_fit_sparam.py`
- Modify: `README.md`

**Interfaces:**
- Public: `--rms-target FLOAT` required.
- Public: `--passivity {off,check,enforce}`, default `check`.
- Public: `--max-order INTEGER`, dynamic default 40 below 60 ports and 24 at 60+ ports.
- Hidden compatibility: old auto-order options route into the target engine.

- [ ] **Step 1: Write failing CLI parsing tests**

Assert the normal large-port command creates `SParamFitTarget(0.001, "check", 24)`, and explicit `--passivity enforce --max-order 32` maps to enforcement config with truthful checking enabled.

- [ ] **Step 2: Replace public passivity flags**

Keep `--check-passivity`, `--enforce-passivity`, and skip flags as hidden compatibility aliases. Reject contradictory combinations with the new `--passivity` option.

- [ ] **Step 3: Route CLI through target orchestration**

Return zero for `PASS` and `PASS_WITH_PASSIVITY_WARNING`; return non-zero when `target_met=False`. Preserve the optional quality gate after target success.

- [ ] **Step 4: Test compatibility aliases**

Old `--auto-model-order-candidates` remains accepted for automation but only constrains the compatibility scheduler path. It cannot silently change RMS definition, passivity semantics, or full-grid evaluation.

- [ ] **Step 5: Rewrite README examples and defaults**

Remove claims that passivity and full-grid fitting are skipped by default. Document the three policies, final-RMS enforcement semantics, failure output behavior, and report fields.

- [ ] **Step 6: Run CLI tests and help smoke**

```powershell
python -m pytest tests/test_cli_fit_sparam.py -q
python -m agent_spice.cli fit-sparam --help
```

- [ ] **Step 7: Review public option count and commit**

```powershell
git add src/agent_spice/cli.py tests/test_cli_fit_sparam.py README.md
git commit -m "feat: simplify target-driven fitting CLI"
```

---

### Task 5: IdEM/Native Parity Summary Harness

**Files:**
- Create: `scripts/sparam_target_parity.py`
- Create: `tests/test_sparam_target_parity.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- CLI consumes paired native and IdEM target-search JSON reports.
- CLI writes one JSON summary and one CSV table.
- Produces per-cell gates for RMS, passivity, order ratio, time ratio, and memory ratio.

- [ ] **Step 1: Write failing report-normalization tests**

Create minimal native/IdEM JSON fixtures in `tmp_path` and assert normalization yields:

```python
{
    "final_rms": 0.0009,
    "final_max_sigma": 0.99999,
    "effective_order": 8,
    "elapsed_seconds": 20.0,
    "peak_memory_mb": 400.0,
}
```

- [ ] **Step 2: Implement fixed parity gates**

```python
rms_pass = our_rms <= target
passivity_pass = policy != "enforce" or our_sigma <= 1.0 + 1e-6
order_pass = our_order <= 1.25 * idem_order
time_pass = our_seconds <= 2.0 * idem_seconds
memory_pass = our_memory <= 1.5 * idem_memory
```

Missing metrics fail the affected gate rather than being ignored.

- [ ] **Step 3: Add corpus/matrix metadata validation**

Require matching Touchstone basename, RMS target, passivity policy, evaluation-point count, RMS formula identifier, and order formula identifier. Mismatches mark the cell `invalid_comparison`.

- [ ] **Step 4: Write JSON and CSV outputs**

CSV columns include corpus, target, policy, both tools' metrics, ratios, individual gates, and overall parity.

- [ ] **Step 5: Run tests and a synthetic CLI smoke**

Run: `python -m pytest tests/test_sparam_target_parity.py -q`.

- [ ] **Step 6: Document benchmark commands and commit**

```powershell
git add scripts/sparam_target_parity.py tests/test_sparam_target_parity.py docs/sparam-large-port-idem-benchmark.md
git commit -m "feat: add IdEM target parity reports"
```

---

### Task 6: End-to-End Verification and Initial Real Benchmark

**Files:**
- Modify only if verification finds defects in files owned by Tasks 1-5.
- Append verified rows to: `docs/sparam-large-port-idem-benchmark.md`.

**Interfaces:**
- Verifies the public CLI, report contract, model-output semantics, and one real native/IdEM comparison cell.

- [ ] **Step 1: Run the focused suite**

```powershell
python -m pytest `
  tests/test_sparam_target_fit.py `
  tests/test_sparam_fitting.py `
  tests/test_cli_fit_sparam.py `
  tests/test_sparam_passivity.py `
  tests/test_sparam_target_parity.py -q
```

- [ ] **Step 2: Run the complete S-parameter suite**

Run: `python -m pytest tests/test_sparam_*.py tests/test_cli_fit_sparam.py -q`.

- [ ] **Step 3: Execute public CLI fixture modes**

Run one checked-in small fixture through `off`, `check`, and `enforce`. Verify requested SPICE output exists only for successful target searches and every report contains `benchmark_contract_version="sparam_target_v1"`.

- [ ] **Step 4: Execute Test13 target smoke**

```powershell
python -m agent_spice.cli fit-sparam user_input\spara\Test13.s60p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 8 `
  --output runs-sparam\target-driven\Test13\model.sp `
  --report runs-sparam\target-driven\Test13\report.json
```

Expected from current evidence: effective order 8, final RMS below 0.001, final max sigma below 1, successful output.

- [ ] **Step 5: Execute Test16 truthful target probe**

Run `check` and `enforce` with target `0.001` and `max-order 8`. Current evidence predicts order 8 does not meet the target; verify the command fails, retains reports, and does not write the requested production SPICE output. This is a required correctness result, not a regression.

- [ ] **Step 6: Run IdEM/native parity summarizer on one available paired cell**

Use the existing IdEM Test16 order-8 reports only if their metadata matches the new contract. Otherwise mark the comparison invalid and record the missing IdEM target-search artifact explicitly.

- [ ] **Step 7: Final code review**

Review every task against the design spec: final-model metrics, exact effective order, full raw grid, non-monotonic search, check warning semantics, failure output absence, and parity ratios.

- [ ] **Step 8: Commit verification corrections and benchmark evidence**

```powershell
git add src/agent_spice/sparam/target_fit.py src/agent_spice/sparam/fitting.py src/agent_spice/cli.py tests/test_sparam_target_fit.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py scripts/sparam_target_parity.py tests/test_sparam_target_parity.py README.md docs/sparam-large-port-idem-benchmark.md
git commit -m "test: verify target-driven S-parameter workflow"
```

## Completion Gate

Implementation is complete only when Tasks 1-6 pass and the public Test13 command succeeds with a truthful passive target result. This plan does not claim IdEM parity merely because the product workflow exists: any corpus cell that fails the ratio gates remains an active algorithm gap, with Test16 passive final RMS currently expected to be the first such gap.
