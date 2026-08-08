# Target-Driven S-Parameter Fitting Design

## Objective

Build one production workflow that accepts a Touchstone S-parameter file, a mean S-RMS target such as `0.001`, and a passivity policy. The tool automatically selects the smallest effective common-pole order that satisfies the requested final-model criteria and reports enough evidence to compare order, elapsed time, and peak memory against IdEM under identical conditions.

The intended user interface is:

```powershell
agent-spice fit-sparam input.s91p `
  --rms-target 0.001 `
  --passivity check `
  --max-order 40 `
  --output model.sp
```

`idem-fast` remains the only production fitting algorithm. Historical and experimental algorithms remain available only through research scripts or hidden diagnostic controls.

## User Contract

### RMS Definition

The target uses mean S-RMS over every original frequency point and every `Nports x Nports` S-parameter channel:

```text
mean_s_rms = sqrt(mean(abs(S_fit - S_raw) ** 2))
```

The metric is independent of port count. Training and final evaluation use the complete raw frequency grid unless the user explicitly selects a diagnostic research mode outside the production CLI.

### Effective Order

Order is the common real-state model order:

```text
effective_order = real_pole_count + 2 * complex_pair_count
```

Reports record requested order, stored pole count, real-pole count, complex-pair count, and effective order separately. Only effective order participates in IdEM comparisons and the target-driven scheduler.

### Passivity Policies

The public `--passivity` option has three values and defaults to `check`.

#### `off`

- Fit and evaluate RMS.
- Do not run passivity checking or enforcement.
- Select the smallest tested effective order whose final RMS meets the target.

#### `check`

- Fit and evaluate RMS.
- Run the truthful Hamiltonian/adaptive full-frequency passivity checker.
- Do not alter the model and do not increase order solely because the model is non-passive.
- A model that meets the RMS target but is non-passive is emitted with status `PASS_WITH_PASSIVITY_WARNING` and a successful process exit status.

#### `enforce`

- Fit and evaluate pre-enforcement RMS.
- Skip enforcement when pre-enforcement RMS exceeds the target because unconstrained fixed-pole residue least squares is already the minimum-error point in that model space.
- If the model is already passive, use it as the final candidate.
- Otherwise run passivity enforcement, then recompute final mean S-RMS and perform a fresh Hamiltonian/adaptive full-frequency validation.
- A trial passes only when final mean S-RMS is at or below the target and final `max_sigma <= 1 + 1e-6`.
- Order selection always uses the post-enforcement model and metrics.

## CLI Behavior

The production options are:

```text
fit-sparam TOUCHSTONE
  --rms-target FLOAT
  --passivity {off,check,enforce}
  --max-order INTEGER
  --output PATH
  [--report PATH]
  [--html-report PATH]
  [--log PATH]
  [--quality-profile {explore,signoff}]
  [--fail-on-quality]
```

Defaults:

- `--passivity check`
- `--max-order 40` for up to 59 ports
- `--max-order 24` for 60 or more ports, because current large-port evidence places useful common-pole orders well below 24
- no default RMS target; omitting `--rms-target` is a usage error

The old public auto-order candidate and auto-target flags become hidden compatibility aliases. They must map into the new target-driven engine rather than maintain a second scheduler.

On success, the command writes the SPICE model, JSON report, HTML report, and log. When no order at or below `--max-order` meets the requested criteria, the command returns a non-zero exit status, writes the JSON/HTML audit reports and log, and does not write the best-effort candidate to the requested production output path.

## Architecture

### Target Specification

Introduce an immutable target object containing:

```python
@dataclass(frozen=True)
class SParamFitTarget:
    mean_rms: float
    passivity: Literal["off", "check", "enforce"] = "check"
    max_order: int = 40
    passivity_epsilon: float = 1e-6
```

It validates positive finite RMS, positive order, and a supported passivity policy.

### Trial Result

Each attempted order produces one structured result:

```python
@dataclass
class SParamOrderTrial:
    requested_order: int
    effective_order: int
    fit_frequency_points: int
    evaluation_frequency_points: int
    pre_mean_rms: float
    final_mean_rms: float
    pre_max_sigma: float | None
    final_max_sigma: float | None
    fit_seconds: float
    check_seconds: float
    enforce_seconds: float
    elapsed_seconds: float
    peak_memory_mb: float
    target_met: bool
    rejection_reason: str | None
```

The model arrays remain attached to the in-memory trial object but are not duplicated in JSON.

### Passivity Policy Runner

A policy runner receives one fitted model, its raw full-grid reference, and `SParamFitTarget`. It returns final model arrays plus the trial metrics. This isolates passivity semantics from order scheduling and ensures all three policies share the same fitting and RMS code.

For `enforce`, candidate acceptance continues to use the Hamiltonian full-frequency gate introduced during the Test16 peak-shifting correction. Sampled or holdout-only improvements cannot be committed.

### Target-Driven Order Scheduler

The scheduler owns order selection, caching, and stop reasons. It does not know the internals of vector fitting or passivity enforcement.

Vector-fit accuracy is not strictly monotonic in order, so binary search is prohibited. The scheduler uses:

1. An ascending even-order ladder beginning at order 4: `4, 6, 8, 10, ...` up to `max_order`.
2. Stop coarse search at the first passing order.
3. Backfill untested integer orders between the previous failed even order and the passing order, in ascending order.
4. Select the lowest effective order among all passing trials.
5. If no order passes, return `target_not_met_before_max_order`.

Every requested order is evaluated at most once. A later implementation may add warm-start pole expansion, but warm starts cannot change the scheduler's observable trial ordering or acceptance rules.

### Enforcement Cost Gate

In `enforce` mode, expensive enforcement runs only if pre-enforcement RMS already meets the target. The scheduler still records the skipped trial with rejection reason `pre_rms_above_target` and zero enforcement time.

This gate is mathematically valid for the fixed fitted pole space and prevents spending passivity time on an order that cannot meet the final RMS target.

## Reporting

The top-level report adds:

```text
rms_target
passivity_policy
max_order
selected_effective_order
target_met
target_stop_reason
order_trials
benchmark_contract_version
```

Each `order_trials` entry includes all fields from `SParamOrderTrial`, pole topology counts, fit/check/enforce status, and the exact rejection reason.

Allowed rejection reasons are:

```text
pre_rms_above_target
final_rms_above_target
passivity_check_failed
passivity_enforcement_failed
effective_order_mismatch
fit_failed
```

`check` mode uses `passivity_check_failed` only as a warning classification, not as `target_met=False`, when RMS passes.

The report records the exact original and evaluated frequency-point counts, RMS formula identifier `mean_s_rms_v1`, effective-order formula identifier `real_plus_twice_complex_v1`, command arguments, elapsed wall time, and whole-process peak RSS.

## Failure and Output Semantics

- Invalid target or max order: usage error before loading the Touchstone file.
- Individual order fit failure: record `fit_failed` and continue to the next order.
- All orders fail: non-zero exit, reports/log retained, requested SPICE output absent.
- `check` mode non-passive result with RMS met: output model, successful exit, status `PASS_WITH_PASSIVITY_WARNING`.
- `enforce` mode final non-passive result: trial failure regardless of RMS.
- No result may be labeled passive from crossover endpoints alone; interval sampling and final Hamiltonian validation are mandatory.

## IdEM Benchmark Contract

The fixed comparison corpus is:

- `Test13.s60p`
- `Test16.s91p`
- `Test11.s163p`
- `Test3.s166p`
- `5power_19port_withcap_122324_202459_11476_DCfitted.s19p`
- `5power_30port_wocap_121124_221036_4876_DCfitted.s30p`

The benchmark matrix contains RMS targets `0.002` and `0.001` for passivity policies `off`, `check`, and `enforce`.

Fairness requirements:

- Both tools consume the same Touchstone file and complete raw frequency grid.
- Both tools use `mean_s_rms_v1` for acceptance and reporting.
- IdEM order is converted to `real_plus_twice_complex_v1` when its report uses another representation.
- `enforce` comparisons use the final passive model's RMS.
- Elapsed time includes the complete automatic order search and all passivity work.
- Peak memory is whole-process peak RSS, measured by the same Windows process monitor.
- Commands, executable versions, thread counts, environment, and every per-order trial are retained.

The first-stage parity gate for each corpus/target/policy cell is:

```text
our_final_rms <= target
our_final_max_sigma <= 1 + 1e-6       # enforce only
our_order <= 1.25 * idem_order
our_elapsed_seconds <= 2.0 * idem_elapsed_seconds
our_peak_memory_mb <= 1.5 * idem_peak_memory_mb
```

`check` policy does not require either tool's model to be passive. It compares selected order and resources for reaching the RMS target while reporting passivity honestly.

## Verification Strategy

### Unit Tests

- Target validation rejects non-finite/non-positive RMS and order.
- Scheduler handles non-monotonic synthetic trial outcomes.
- Coarse even-order search backfills odd orders after the first pass.
- Every requested order is evaluated once.
- `off`, `check`, and `enforce` apply their distinct acceptance rules.
- `check` produces `PASS_WITH_PASSIVITY_WARNING` for an RMS-passing non-passive model.
- `enforce` uses final RMS and final max sigma, never pre-enforcement RMS.
- Enforcement is skipped when pre-RMS exceeds target.
- Failed target search does not write the requested SPICE output.

### Integration Tests

- Small checked-in Touchstone fixtures exercise all three policies through the public CLI.
- JSON and HTML reports carry identical selected order, target status, and trial metrics.
- Explicit compatibility aliases route through the new scheduler.
- Existing single-order fitting APIs remain available for research scripts.

### Large-Port Acceptance

- Test16 is the hard fit/passivity gate.
- Test13 prevents Test16-specific overfitting.
- Test11 and Test3 verify memory behavior at 163/166 ports.
- The 19/30-port cases protect medium-port accuracy and order behavior.
- Large files remain outside routine CI; a reproducible benchmark command writes one JSON summary and one CSV comparison table.

## Delivery Sequence

1. Introduce target, policy, and trial data structures without changing fitting algorithms.
2. Implement and test the target-driven non-monotonic order scheduler.
3. Route the three passivity policies through one trial evaluator.
4. Replace the public CLI's candidate-list UX with `--rms-target`, `--passivity`, and `--max-order` while retaining hidden compatibility aliases.
5. Add report and failure-output semantics.
6. Build the IdEM/native benchmark harness and run the fixed matrix.
7. Use benchmark attribution to improve fitting or enforcement only where a parity gate fails.

This sequence deliberately separates product correctness from algorithm tuning. A benchmark failure is evidence for the next algorithm change, not a reason to weaken the reporting or acceptance contract.
