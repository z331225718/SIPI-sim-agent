# Data-Driven Full Pole Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an IdEM-competitive low-order public-pole S-parameter model by discovering the complete stable pole set from raw frequency data, then jointly refining pole locations through variable projection while reusing the existing residue LS and passivity enforcement paths.

**Architecture:** First close the 256-point-versus-611-point training confounder with a reproducible full-grid baseline. Then add an isolated research module that generates complete stable pole sets from raw data, scores them through full-grid fixed-pole residue solves, and refines all pole parameters together with a bounded variable-projection optimizer. IdEM pole values remain an evaluation-only oracle; production candidate generation and optimization never receive them.

**Tech Stack:** Python 3.11+, NumPy, SciPy optimization already used by the project, scikit-rf Touchstone loading, pytest, existing `NativeVectorFitting`, fixed-pole residue LS, passivity sampler/enforcer, and JSON/Markdown benchmark artifacts.

## Global Constraints

- All promoted fitting comparisons train and evaluate on every raw Touchstone frequency point. Test16 and Test13 each contain 611 points.
- IdEM numerical poles may only be loaded by benchmark/oracle reporting code. They must never be passed to candidate generation, initialization, optimization bounds, objective functions, or production defaults.
- The IdEM-observed `4 real + 2 complex pairs` topology is allowed only as a D11 attribution experiment. The production path must select topology from a data-only candidate set.
- Pole sets must remain stable in the open left half-plane throughout optimization. No post-solve pole clipping, per-pole reinjection, or D4-D8 relocation constraint may be added.
- Effective order is `real_pole_count + 2 * complex_pair_count`; reports must include requested topology, stored pole count, and resulting effective order separately.
- Every benchmark reports training points, evaluation points, mean RMS, true full-grid max sigma and its frequency, violation-band count, wall time, and peak RSS when available.
- Passivity acceptance uses real samples inside violation intervals plus the full raw grid, not crossover/endpoints alone.
- Experimental code remains opt-in. The current `idem-fast` default cannot change before Test16 and Test13 both pass the promotion gates without case-specific retuning.
- Every task follows test-first development, runs focused tests plus the affected S-parameter suite, receives a fresh code review, and records benchmark evidence before the next task starts.
- Existing unrelated dirty-worktree changes must not be reverted or reformatted.

---

## File Structure

- Create `scripts/sparam_full_grid_pole_baseline.py`: D10 fair-training benchmark and decision report.
- Create `tests/test_sparam_full_grid_pole_baseline.py`: unit coverage for case construction, metrics, and stop decision.
- Create `src/agent_spice/sparam/pole_discovery.py`: stable topology types, data-only candidate generation, full-grid evaluation, and Pareto selection.
- Create `tests/test_sparam_pole_discovery.py`: synthetic and invariant tests for data-only pole discovery.
- Create `scripts/sparam_pole_manifold_probe.py`: D11/D12 research runner and auditable JSON/Markdown artifacts.
- Create `tests/test_sparam_pole_manifold_probe.py`: probe wiring and oracle-separation tests.
- Create `src/agent_spice/sparam/pole_varpro.py`: stable parameterization and full-set variable-projection optimizer.
- Create `tests/test_sparam_pole_varpro.py`: synthetic recovery, topology preservation, and rejection tests.
- Create `scripts/sparam_pole_discovery_benchmark.py`: Test16/Test13/Test11 cross-case benchmark matrix.
- Create `tests/test_sparam_pole_discovery_benchmark.py`: benchmark decision and no-retuning contract tests.
- Modify `src/agent_spice/sparam/fitting.py`: opt-in strategy integration only after promotion gates pass.
- Modify `src/agent_spice/cli.py`: one strategy-level hidden option during research; no low-level optimizer flags.
- Modify `tests/test_sparam_fitting.py` and `tests/test_cli_fit_sparam.py`: defaults and strategy propagation.
- Modify `docs/sparam-large-port-idem-benchmark.md`: append D10-D14 evidence and decisions after each benchmark.

---

### Task 1: D10 Full-Grid Training Baseline

**Files:**
- Create: `scripts/sparam_full_grid_pole_baseline.py`
- Create: `tests/test_sparam_full_grid_pole_baseline.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: `NativeFitRecipe`, `NATIVE_ORDER10_RECIPE`, `build_native_model()`, `fit_fixed_pole_residues()`, `measure_model()`, `describe_poles()`, `compare_pole_distributions()`.
- Produces: `run_full_grid_pole_baseline(*, touchstone_path: Path, idem_model_path: Path, output_dir: Path) -> dict[str, Any]` and a stable `summary.json` schema used by later benchmark tasks.

- [ ] **Step 1: Write failing tests for the fair-training case matrix**

Create tests that monkeypatch raw loading and fitting, then verify the runner constructs exactly these native cases:

```python
def test_baseline_runs_256_and_full_grid(monkeypatch, tmp_path):
    seen = []

    def fake_build(raw, recipe):
        seen.append(recipe.fit_max_frequency_points)
        return fake_model(fit_points=256 if recipe.fit_max_frequency_points == 256 else 611)

    monkeypatch.setattr(baseline, "load_raw_touchstone", lambda path: fake_raw(points=611))
    monkeypatch.setattr(baseline, "build_native_model", fake_build)
    monkeypatch.setattr(baseline, "load_idem_poles", lambda path: IDEM_TEST_POLES)
    monkeypatch.setattr(baseline, "fit_fixed_pole_residues", fake_refit)
    monkeypatch.setattr(baseline, "measure_model", fake_measure)

    result = baseline.run_full_grid_pole_baseline(
        touchstone_path=tmp_path / "Test16.s91p",
        idem_model_path=tmp_path / "model.mod.h5",
        output_dir=tmp_path / "out",
    )

    assert seen == [256, None]
    assert result["cases"]["native_256"]["training_frequency_points"] == 256
    assert result["cases"]["native_full_grid"]["training_frequency_points"] == 611
    assert result["reference_grid"]["evaluation_frequency_points"] == 611
```

Add a decision test:

```python
def test_full_grid_gate_requires_accuracy_passivity_and_order():
    assert baseline.decide_full_grid_baseline(
        mean_rms=0.0019,
        max_sigma=1.009,
        effective_order=10,
    )["stop_before_d11"] is True
    assert baseline.decide_full_grid_baseline(
        mean_rms=0.0021,
        max_sigma=1.009,
        effective_order=10,
    )["stop_before_d11"] is False
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
python -m pytest tests\test_sparam_full_grid_pole_baseline.py -q
```

Expected: FAIL because `scripts.sparam_full_grid_pole_baseline` does not exist.

- [ ] **Step 3: Implement the D10 runner**

Implement these public helpers:

```python
def decide_full_grid_baseline(*, mean_rms: float, max_sigma: float, effective_order: int) -> dict[str, Any]:
    passed = bool(mean_rms < 0.002 and max_sigma < 1.01 and effective_order <= 10)
    return {
        "stop_before_d11": passed,
        "continue_to_d11": not passed,
        "thresholds": {"mean_rms_lt": 0.002, "max_sigma_lt": 1.01, "effective_order_lte": 10},
    }


def run_full_grid_pole_baseline(
    *,
    touchstone_path: Path,
    idem_model_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    raw = load_raw_touchstone(touchstone_path)
    recipes = {
        "native_256": replace(NATIVE_ORDER10_RECIPE, label="native_requested_real4_complex2_256", fit_max_frequency_points=256),
        "native_full_grid": replace(NATIVE_ORDER10_RECIPE, label="native_requested_real4_complex2_full", fit_max_frequency_points=None),
    }
    # For each case, preserve metrics from the trained residues and separately
    # refit the same poles on all raw points to isolate pole-set quality.
```

Each case must include:

```python
{
    "training_frequency_points": int(model.fit_points),
    "evaluation_frequency_points": int(len(raw.freqs_hz)),
    "requested_topology": {"real_poles": 4, "complex_pairs": 2, "requested_effective_order": 8},
    "actual_topology": pole_summary,
    "trained_model_metrics": measure_model(model, raw),
    "full_grid_residue_refit_metrics": measure_model(full_refit, raw),
    "fit_elapsed_seconds": model.fit_elapsed_seconds,
    "poles": describe_poles(model.poles),
    "relocation_trajectory": describe_relocation_history(model.pole_relocation_history or []),
}
```

The IdEM section must contain only oracle metrics and pole-distribution comparison. Add an `oracle_policy` string stating that IdEM poles were not supplied to native fitting.

- [ ] **Step 4: Run unit and regression tests**

Run:

```powershell
python -m pytest tests\test_sparam_full_grid_pole_baseline.py tests\test_sparam_pole_placement_diagnostics.py tests\test_sparam_passivity_source_attribution.py -q
```

Expected: all pass.

- [ ] **Step 5: Run the full Test16 D10 benchmark**

Run:

```powershell
python scripts\sparam_full_grid_pole_baseline.py `
  --touchstone user_input\spara\Test16.s91p `
  --idem-model runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\model.mod.h5 `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d10-full-grid-baseline
```

Expected artifact: `summary.json` and `benchmark_note.md`. If `stop_before_d11=true`, stop this plan and document that full-grid native fitting already closes the pole gap. Otherwise continue to Task 2.

- [ ] **Step 6: Review and commit**

Review requirements:

- Confirm `native_full_grid` actually receives `fit_max_frequency_points=None`.
- Confirm all reported RMS/sigma metrics evaluate 611 points.
- Confirm IdEM poles never enter either native recipe.
- Confirm requested order 8 is not mislabeled as actual order 8 when relocation produces order 10.

Commit only Task 1 files:

```powershell
git add scripts\sparam_full_grid_pole_baseline.py tests\test_sparam_full_grid_pole_baseline.py docs\sparam-large-port-idem-benchmark.md
git commit -m "test: establish full-grid pole fitting baseline"
```

---

### Task 2: D11 Data-Only Complete Pole-Set Discovery

**Files:**
- Create: `src/agent_spice/sparam/pole_discovery.py`
- Create: `tests/test_sparam_pole_discovery.py`
- Create: `scripts/sparam_pole_manifold_probe.py`
- Create: `tests/test_sparam_pole_manifold_probe.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: raw frequency array, flattened S responses, `NativeVectorFitting._fit_residues()`, `_evaluate_residue_model()`, and full-grid passivity sampling.
- Produces: `PoleTopology`, `PoleCandidate`, `PoleCandidateEvaluation`, `effective_order()`, `generate_data_only_candidates()`, `evaluate_pole_candidates()`, `pareto_front()`, and `run_pole_manifold_probe()`.

- [ ] **Step 1: Write topology and stability tests**

```python
def test_make_stable_poles_preserves_requested_topology():
    poles = make_stable_poles(
        real_decay_hz=[1e6, 1e7, 1e8, 5e8],
        complex_frequency_hz=[1.2e9, 1.9e9],
        damping_ratio=[0.03, 0.05],
    )
    assert len(poles) == 6
    assert np.all(poles.real < 0.0)
    assert effective_order(poles) == 8
    assert np.count_nonzero(np.abs(poles.imag) > 0.0) == 2


def test_generator_is_deterministic_and_data_only():
    first = generate_data_only_candidates(FREQS, RESPONSES, TOPOLOGY, candidate_count=16, seed=7)
    second = generate_data_only_candidates(FREQS, RESPONSES, TOPOLOGY, candidate_count=16, seed=7)
    assert [candidate.fingerprint for candidate in first] == [candidate.fingerprint for candidate in second]
    assert all(candidate.source in {"log_grid", "response_activity", "stratified"} for candidate in first)
```

Add tests proving every candidate stays within raw-data-derived bounds and no function accepts an IdEM model or oracle-pole argument.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests\test_sparam_pole_discovery.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the data-only discovery types**

Use these exact public dataclasses:

```python
@dataclass(frozen=True)
class PoleTopology:
    real_count: int
    complex_pair_count: int

    @property
    def effective_order(self) -> int:
        return self.real_count + 2 * self.complex_pair_count


@dataclass(frozen=True)
class PoleCandidate:
    poles: np.ndarray
    topology: PoleTopology
    source: str
    seed_index: int
    fingerprint: str


@dataclass(frozen=True)
class PoleCandidateEvaluation:
    candidate: PoleCandidate
    mean_rms: float
    max_sigma: float | None
    max_sigma_frequency_hz: float | None
    violation_band_count: int | None


def effective_order(poles: Any) -> int:
    pole_array = np.asarray(poles, dtype=complex).reshape(-1)
    return int(np.count_nonzero(np.abs(pole_array.imag) <= 1e-15) + 2 * np.count_nonzero(pole_array.imag > 1e-15))
```

`generate_data_only_candidates()` must create exactly one log-grid candidate, activity-derived candidates using frequency-local variation

```python
activity = np.sqrt(np.mean(np.abs(np.diff(responses, axis=1)) ** 2, axis=0))
```

and deterministic stratified candidates. Bounds come only from `min(freqs_hz[freqs_hz > 0])` and `max(freqs_hz)`. Use damping ratios in `[0.01, 0.20]`; this is a generic stability range, not an IdEM-derived pole value.

- [ ] **Step 4: Implement two-stage full-grid candidate evaluation**

For every candidate, solve residues and compute RMS on all points. Sort by RMS and compute full-grid sigma only for the best `full_sigma_candidate_count=8`. Return the non-dominated Pareto front over `(mean_rms, max_sigma)`; candidates without sigma are never eligible for the front.

Use strict dominance:

```python
def dominates(left: PoleCandidateEvaluation, right: PoleCandidateEvaluation) -> bool:
    return (
        left.mean_rms <= right.mean_rms
        and left.max_sigma <= right.max_sigma
        and (left.mean_rms < right.mean_rms or left.max_sigma < right.max_sigma)
    )
```

- [ ] **Step 5: Implement and test the D11 probe**

`run_pole_manifold_probe()` must run the attribution topology `PoleTopology(4, 2)` with `candidate_count=32`, `seed=20260710`, all raw points, and `full_sigma_candidate_count=8`. Its output must include the policy:

```python
"oracle_policy": {
    "idem_poles_used_for_generation": False,
    "idem_poles_used_for_initialization": False,
    "idem_poles_used_for_objective": False,
    "idem_topology_used_for_attribution_only": True,
}
```

Run:

```powershell
python -m pytest tests\test_sparam_pole_discovery.py tests\test_sparam_pole_manifold_probe.py -q
```

- [ ] **Step 6: Run the Test16 D11 benchmark and apply the stop rule**

Run:

```powershell
python scripts\sparam_pole_manifold_probe.py `
  --touchstone user_input\spara\Test16.s91p `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d11-data-only `
  --candidate-count 32 `
  --seed 20260710
```

Continue to Task 3 only if a data-only candidate reaches both `mean_rms < 0.003` and `max_sigma < 1.03`. If no candidate passes, skip Task 3 and execute the fallback section at the end of this plan.

- [ ] **Step 7: Review and commit**

Review specifically for hidden oracle leakage, topology mutation, accidental sub-sampling, and full-SVD evaluation of all 32 candidates. Commit:

```powershell
git add src\agent_spice\sparam\pole_discovery.py tests\test_sparam_pole_discovery.py scripts\sparam_pole_manifold_probe.py tests\test_sparam_pole_manifold_probe.py docs\sparam-large-port-idem-benchmark.md
git commit -m "feat: discover complete pole sets from S-parameter data"
```

---

### Task 3: D12 Full-Set Variable Projection

**Files:**
- Create: `src/agent_spice/sparam/pole_varpro.py`
- Create: `tests/test_sparam_pole_varpro.py`
- Modify: `pyproject.toml`
- Modify: `scripts/sparam_pole_manifold_probe.py`
- Modify: `tests/test_sparam_pole_manifold_probe.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: the D11 Pareto candidates and existing fixed-pole residue solve.
- Produces: `PoleParameterBounds`, `VariableProjectionResult`, `optimize_pole_set()`, and D12 probe output.

- [ ] **Step 1: Write synthetic recovery and invariant tests**

Generate a stable order-4 synthetic response from two real poles and one complex pair, perturb every pole by 10%, and verify optimization improves RMS without changing topology:

```python
result = optimize_pole_set(
    freqs_hz=freqs,
    responses=responses,
    initial_poles=perturbed,
    topology=PoleTopology(2, 1),
    max_iterations=12,
)
assert result.final_mean_rms < result.initial_mean_rms
assert result.final_mean_rms < 1e-5
assert effective_order(result.poles) == 4
assert np.all(result.poles.real < 0.0)
```

Add rejection tests for unstable, mismatched, duplicated, or out-of-band initial sets.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests\test_sparam_pole_varpro.py -q
```

- [ ] **Step 3: Implement stable full-set parameterization**

Use log-frequency variables for real decay and complex frequencies, and logit variables for damping ratio. Bounds are derived from raw frequency limits and generic damping `[0.005, 0.30]`. Pole reconstruction must always return half-pair storage with positive imaginary representatives and strictly negative real parts.

Add `scipy>=1.11` as a direct project dependency because this module imports `scipy.optimize` directly; do not rely on scikit-rf's transitive dependency.

```python
@dataclass(frozen=True)
class VariableProjectionResult:
    poles: np.ndarray
    initial_mean_rms: float
    final_mean_rms: float
    iterations: int
    function_evaluations: int
    success: bool
    message: str
    history: tuple[dict[str, float], ...]
```

- [ ] **Step 4: Implement the variable-projection objective**

For each nonlinear pole vector:

1. Reconstruct the complete stable pole set.
2. Solve all linear residues/constants with `NativeVectorFitting._fit_residues()` on every raw point.
3. Evaluate the fitted responses with `_evaluate_residue_model()`.
4. Return scalar full-grid mean RMS to `scipy.optimize.minimize(method="L-BFGS-B")`.

Use `maxiter=12`, `ftol=1e-10`, and finite-difference `eps=1e-4` for the first implementation. Do not put max sigma inside the inner optimizer; evaluate full-grid passivity after each completed restart and choose from the resulting RMS/sigma Pareto front.

- [ ] **Step 5: Optimize the best four D11 seeds**

Extend the probe with `--varpro` that optimizes the four best Pareto/RMS-diverse D11 candidates. Record every initial/final pole set, optimizer history, full-grid metrics, time, and peak RSS. The D12 decision is:

```python
passed = (
    effective_order <= 10
    and pre_mean_rms < 0.002
    and pre_max_sigma < 1.01
)
```

Run focused tests:

```powershell
python -m pytest tests\test_sparam_pole_varpro.py tests\test_sparam_pole_manifold_probe.py tests\test_sparam_native_vf.py -q
```

- [ ] **Step 6: Run the Test16 D12 benchmark**

Run:

```powershell
python scripts\sparam_pole_manifold_probe.py `
  --touchstone user_input\spara\Test16.s91p `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d12-varpro `
  --candidate-count 32 `
  --seed 20260710 `
  --varpro `
  --varpro-seed-count 4 `
  --varpro-max-iterations 12
```

If no candidate reaches `RMS < 0.002` and `sigma < 1.01`, stop local optimizer tuning. Do not add more regularization/anchor knobs; execute the Loewner fallback.

- [ ] **Step 7: Review and commit**

Review parameter transforms, exact full-grid use, topology preservation, optimizer failure handling, deterministic selection, and absence of IdEM data. Commit:

```powershell
git add pyproject.toml src\agent_spice\sparam\pole_varpro.py tests\test_sparam_pole_varpro.py scripts\sparam_pole_manifold_probe.py tests\test_sparam_pole_manifold_probe.py docs\sparam-large-port-idem-benchmark.md
git commit -m "feat: jointly refine public poles with variable projection"
```

---

### Task 4: D13 Passivity and Cross-Case Validation

**Files:**
- Create: `scripts/sparam_pole_discovery_benchmark.py`
- Create: `tests/test_sparam_pole_discovery_benchmark.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: promoted D12 data-only strategy and existing passivity enforcement profile.
- Produces: a single benchmark matrix for Test16, Test13, and optional Test11 with pre/post-enforcement accuracy, passivity, order, time, and memory.

- [ ] **Step 1: Write the benchmark contract tests**

Verify one immutable configuration object is reused across cases and that the runner rejects per-case overrides:

```python
def test_cross_case_runner_uses_one_immutable_recipe(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(benchmark, "run_case", lambda case, recipe: seen.append((case.name, recipe)))
    benchmark.run_benchmark(CASES, recipe=DEFAULT_D13_RECIPE, output_dir=tmp_path)
    assert len({id(recipe) for _, recipe in seen}) == 1
```

Verify promotion requires every mandatory case to pass:

```python
assert decide_promotion([passing_test16, passing_test13])["promote"] is True
assert decide_promotion([passing_test16, failing_test13])["promote"] is False
```

- [ ] **Step 2: Implement the benchmark runner**

Mandatory cases:

```python
TEST16 = BenchmarkCase(
    name="Test16.s91p",
    touchstone=Path("user_input/spara/Test16.s91p"),
    idem_model=Path("runs-sparam/large-port-autofit-benchmark/Test16_s91p/idem/order8/order8_init3/model.mod.h5"),
)
TEST13 = BenchmarkCase(
    name="Test13.s60p",
    touchstone=Path("user_input/spara/Test13.s60p"),
    idem_model=Path("runs-sparam/test13-s60p-autofit-benchmark/idem-low/order8/order8_init3/model.mod.h5"),
)
```

Test11 is optional until the mandatory pair passes because its raw file is about 623 MB. The same candidate count, seed, topology set, optimizer limits, and passivity profile must be used for every case.

- [ ] **Step 3: Run enforcement and promotion gates**

For every selected model, record pre-enforcement and post-enforcement metrics on the complete raw grid. Promotion requires, for both Test16 and Test13:

```text
effective_order <= 10
pre-enforcement mean RMS < 0.002
pre-enforcement max sigma < 1.01
post-enforcement max sigma < 1.0
post-enforcement mean RMS < 0.002
no global damping fallback
training_frequency_points == evaluation_frequency_points == raw point count
```

- [ ] **Step 4: Run focused tests and mandatory benchmarks**

```powershell
python -m pytest tests\test_sparam_pole_discovery_benchmark.py tests\test_sparam_passivity.py -q
python scripts\sparam_pole_discovery_benchmark.py `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d13-cross-case
```

If both mandatory cases pass, run Test11 once without retuning. If either mandatory case fails, retain the implementation as research-only and execute the fallback decision rather than weakening thresholds.

- [ ] **Step 5: Review and commit**

Review all metric scopes, no-retuning enforcement, actual order reporting, true violation-interval sampling, and fallback usage. Commit:

```powershell
git add scripts\sparam_pole_discovery_benchmark.py tests\test_sparam_pole_discovery_benchmark.py docs\sparam-large-port-idem-benchmark.md
git commit -m "test: validate pole discovery across large-port models"
```

---

### Task 5: D14 Production Integration and CLI Simplification

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_cli_fit_sparam.py`
- Modify: `README.md`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: a D13-promoted pole-discovery recipe.
- Produces: one strategy-level fitting selection and no new public low-level optimizer knobs.

- [ ] **Step 1: Write failing default and propagation tests**

Before promotion, assert the existing default remains unchanged and `data_varpro` is explicit opt-in. After D13 passes, change only the default strategy assertion to `data_varpro`; do not change numerical thresholds through CLI.

```python
def test_cli_exposes_strategy_not_optimizer_knobs(parser):
    args = parser.parse_args(["fit-sparam", "input.s2p", "--native-pole-strategy", "data_varpro"])
    assert args.native_pole_strategy == "data_varpro"
    assert not hasattr(args, "varpro_ftol")
    assert not hasattr(args, "varpro_eps")
```

- [ ] **Step 2: Integrate one strategy boundary**

Add `SParamFitConfig.native_pole_strategy: Literal["sk", "data_varpro"]`. Keep all D11-D13 numerical settings in one internal immutable recipe. The fitting path chooses either the current `NativeVectorFitting.vector_fit()` or the promoted discovery/varpro pipeline, then passes the resulting model through the same reporting and passivity interfaces.

- [ ] **Step 3: Update README and benchmark documentation**

Document:

- the full-grid training contract;
- effective-order definition;
- data-only/oracle separation;
- default strategy and fallback behavior;
- measured Test16/Test13 accuracy, sigma, time, and memory;
- that D4-D8 flags remain historical research controls and are not user-facing recommendations.

- [ ] **Step 4: Run the complete affected suite**

```powershell
python -m pytest tests\test_sparam_pole_discovery.py tests\test_sparam_pole_varpro.py tests\test_sparam_pole_manifold_probe.py tests\test_sparam_pole_discovery_benchmark.py tests\test_sparam_native_vf.py tests\test_sparam_skrf_streaming.py tests\test_sparam_fitting.py tests\test_cli_fit_sparam.py tests\test_sparam_passivity.py -q
python -m py_compile src\agent_spice\sparam\pole_discovery.py src\agent_spice\sparam\pole_varpro.py src\agent_spice\sparam\fitting.py src\agent_spice\cli.py
```

- [ ] **Step 5: Final whole-branch review and commit**

Review for regressions, hidden down-sampling, oracle leakage, topology mutation, memory blowups, and inaccurate RMS/order labels. Commit:

```powershell
git add src\agent_spice\sparam\fitting.py src\agent_spice\cli.py tests\test_sparam_fitting.py tests\test_cli_fit_sparam.py README.md docs\sparam-large-port-idem-benchmark.md
git commit -m "feat: integrate data-driven public-pole fitting"
```

---

## Fallback: Randomized Loewner/Common-Pole Discovery

Execute this fallback only when either D11 cannot produce a seed with `RMS < 0.003` and `sigma < 1.03`, or D12 cannot reach `RMS < 0.002` and `sigma < 1.01` within four restarts and twelve iterations.

The fallback must be a new plan, not an unreviewed extension of this one. Its design requirements are:

- Build deterministic scalar transfer probes `u^H S(f) v` from fixed random vectors.
- Construct Loewner pencils from disjoint left/right frequency samples.
- Truncate by singular values to candidate effective orders 6, 8, and 10.
- Extract stable poles, merge duplicates, and run the same full-grid residue LS/Pareto evaluation.
- Keep IdEM poles entirely outside the generator.
- Return to D12 variable projection only if Loewner candidates pass the D11 seed gate.

## Stop Rules

1. Stop before D11 if the fair full-grid native baseline already reaches `RMS < 0.002`, `sigma < 1.01`, and effective order `<=10`.
2. Stop D11 and write the Loewner fallback plan if no data-only candidate reaches `RMS < 0.003` and `sigma < 1.03`.
3. Stop D12 optimizer tuning after four seeds and twelve iterations if no result reaches `RMS < 0.002` and `sigma < 1.01`.
4. Do not promote if passivity requires global damping or post-enforcement RMS is `>=0.002`.
5. Do not promote if Test13 needs any setting different from Test16.
6. Do not add a ninth SK relocation repair or another pole-anchor/regularization knob.

## Per-Task Review Protocol

After every task:

1. The implementer runs the stated tests and benchmark, self-reviews, and commits only that task's files.
2. A fresh reviewer checks both specification compliance and code quality from the task diff.
3. Critical and Important findings are fixed and re-reviewed before the next task.
4. The benchmark decision and exact artifact path are appended to `docs/sparam-large-port-idem-benchmark.md`.
5. The controller records completion in `.superpowers/sdd/progress.md`.

## Self-Review

- Spec coverage: fair full-grid baseline, data-only pole discovery, complete-set variable projection, passivity enforcement, cross-case validation, production integration, fallback, and explicit stop rules are all covered.
- Action completeness scan: every task names concrete files, commands, thresholds, and expected decisions.
- Type consistency: `PoleTopology`, `PoleCandidate`, `PoleCandidateEvaluation`, `VariableProjectionResult`, `run_pole_manifold_probe()`, and the benchmark interfaces are defined before use.
- Scope check: D10-D14 form one dependency chain. The Loewner method is deliberately separated into a new plan if the current strategy fails.
- Fairness check: all promoted training/evaluation uses the raw grid, and IdEM numerical poles remain evaluation-only.
