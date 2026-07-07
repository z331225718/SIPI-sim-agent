# IdEM-Inspired Passivity Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and benchmark an IdEM-inspired passivity enforcement path that reduces memory/runtime while moving Test16-class large S-parameter models closer to IdEM standalone passivity quality.

**Architecture:** Keep the current Hamiltonian checker as the interval oracle and final verifier, but replace the coarse fixed violation sampling with adaptive singular-curve-aware sampling, then add IdEM-style margining and in-band preservation. Avoid default pole/constant perturbation until residue-only improvements are exhausted and measured.

**Tech Stack:** Python, NumPy, SciPy, pytest, existing Agent-Spice native S-parameter fitting/passivity modules, local CST IdEM executable and HTML documentation under `C:\Program Files\CST Studio Suite 2026`.

## Global Constraints

- Answer and project-facing notes should stay in Chinese when written for the current investigation.
- Do not stage or modify `.reasonix/*` desktop state files.
- Do not make `perturb_constant` or `perturb_poles` default-on without a benchmark showing better passivity, no RMS regression, and no material runtime/memory regression.
- Treat IdEM as a behavioral benchmark and documented-option inspiration source, not as code to copy or reverse engineer.
- Every algorithm experiment must record Test16 metrics: `max_sigma_before`, `max_sigma_after`, violation count, RMS before/after, elapsed seconds, peak memory MB, active constraints, active variables, and rejection reasons.
- Keep the public CLI simple; experimental knobs should remain internal or documented as diagnostics until they win consistently.

---

## IdEM Inspiration Inventory

These are the local IdEM passivity options and observed behaviors we should test one by one or in combinations.

| IdEM idea | Local evidence | Current gap | First experiment |
| --- | --- | --- | --- |
| `SOC+HAM` hybrid | IdEM XML uses `<algorithm>SOC+HAM</algorithm>` | We use HAM-like interval detection plus linearized QP, but no real SOC loop | Keep HAM as oracle; improve local constraints first |
| Adaptive sampling | XML uses adaptive sampling, `samplesPerPole=3`, `maxTrackingError=0.2`, `maxRefinementPasses=6`, `minSpacingFactor=0.1` | We sample only 5 points per Hamiltonian interval | Add adaptive violation sampler with singular-vector tracking |
| Passivity margin | XML uses `passivityMargin=0.0001` | We target exactly `sigma <= 1` | Change repair constraint to `sigma <= 1 - margin` |
| Max perturbed eig/curve budget | Docs describe non-passive singular-value curves for S-parameters | We pick violating singular modes at sampled points but do not track curves across frequency | Group/track constraints by singular vector overlap |
| In-band low-pass weighting | XML enables model-based low-pass filter, passband 1, stopband 1.05, stop attenuation 40 dB | Current fit-weighted QP is variable-norm based, not frequency-band preservation | Add holdout/in-band frequency weights after adaptive sampling |
| Model-based relative weighting | Docs mention inverse-weighted Gramian | We do not estimate Gramian/state energy | Later approximate via response-impact weights only if low-pass weighting is insufficient |
| Sparse/adaptive Hamiltonian eigensolver | Docs use adaptive HAM solver and multishift Arnoldi for large models | Our Hamiltonian check may become costly for large order/port | Defer until repair loop works; profile first |
| Preserve DC / frequency constraints | CLI exposes `-DC`; XML default has `enforceDC=false`, `preserveFrequencyConstraints=false` | We do not preserve DC explicitly during passivity repair | Add only if Test16 RMS/low-frequency behavior regresses |
| Relaxed passivity | XML supports relaxed thresholds | Useful for AC-only or report-only modes | Keep out of signoff path for now |
| Pole/constant perturbation | Gemini/Agy suggested joint perturbation; IdEM docs talk model perturbation | Our experiment showed default constant perturbation was slower and no better on Test16 | Keep opt-in, benchmark only after residue-only path saturates |

## File Map

- Modify: `src/agent_spice/sparam/passivity.py`
  - Owns Hamiltonian passivity check, violation sampling, QP assembly, line-search acceptance, diagnostics.
- Modify: `src/agent_spice/sparam/fitting.py`
  - Owns `SParamFitConfig` defaults and passes passivity options into enforcement.
- Modify: `tests/test_sparam_passivity.py`
  - Unit tests for adaptive sampling, margin constraints, QP diagnostics, weighting behavior.
- Modify: `tests/test_sparam_fitting.py`
  - Config and integration tests for safe defaults.
- Optional modify: `tests/test_cli_fit_sparam.py`
  - Only if new user-facing passivity options are exposed; avoid this in the first implementation.
- Modify: `docs/sparam-large-port-idem-benchmark.md`
  - Append benchmark results and interpretation after each Test16 experiment.
- Create or update benchmark artifacts under `runs-sparam/passivity-idem-inspired/`
  - Store JSON reports and logs; do not commit large generated models unless explicitly requested.

## Metrics Gate

Use this baseline until a newer one is written into the benchmark doc.

| Engine / mode | Case | Max sigma after | RMS | Time | Peak memory |
| --- | --- | ---: | ---: | ---: | ---: |
| Current residue fallback | Test16 order10 | about `1.00908` | about `0.001835` | about `64s` in best observed run | about `345 MB` |
| Agy constant default | Test16 order10 | about `1.00938` | about `0.001989` | about `189s` | about `347 MB` |
| IdEM standalone passivity | Test16 IdEM order8 `.mod.h5` | about `0.999986` | about `0.001175` | about `15s` | about `162 MB` |

Acceptance for each task:

- Must not regress existing tests.
- Must emit enough diagnostics to explain candidate rejection.
- Must compare against Test16 with the same model/order/input grid as the previous run.
- A change is considered useful only if it improves `max_sigma_after`, lowers runtime/memory, or explains why the remaining violation cannot be repaired by the current linearized residue-only method.

---

### Task 1: Freeze IdEM Option Knowledge Into Project Docs

**Files:**
- Modify: `docs/sparam-large-port-idem-benchmark.md`
- Test: documentation review only

**Interfaces:**
- Consumes: local IdEM option XML and docs already inspected from CST installation.
- Produces: a durable "Passivity option lessons" section that later benchmark rows can reference.

- [ ] **Step 1: Add a concise IdEM passivity option section**

Add this section near the end of `docs/sparam-large-port-idem-benchmark.md`:

```markdown
## IdEM Passivity Option Lessons

Local CST IdEM passivity output and documentation show that the standalone passivity tool is not a simple dense residual perturbation pass. The default path is best interpreted as an `SOC+HAM` hybrid:

- HAM provides global violation interval detection and verification.
- SOC-style local constraints repair selected violating singular-value or eigenvalue curves.
- Adaptive sampling is central: IdEM defaults include `samplesPerPole=3`, `maxTrackingError=0.2`, `maxRefinementPasses=6`, and `minSpacingFactor=0.1`.
- It uses a nonzero passivity margin, observed as `passivityMargin=1e-4`.
- It enables low-pass model-based weighting by default, preserving in-band behavior more strongly than out-of-band behavior.
- It can cap the number of perturbed non-passive curves, but for S-parameters the documented recommended value can be unbounded when memory allows.

Agent-Spice should therefore prioritize adaptive violation sampling, passivity margining, singular-curve tracking, and in-band weighted acceptance before making constant or pole perturbation part of the default path.
```

- [ ] **Step 2: Review diff**

Run:

```powershell
git diff -- docs/sparam-large-port-idem-benchmark.md
```

Expected: the new section is present and does not overwrite the existing caveat about sampled-fit versus full-grid IdEM fitting.

### Task 2: Add Adaptive Violation Sampler Unit Tests

**Files:**
- Modify: `tests/test_sparam_passivity.py`
- Modify: `src/agent_spice/sparam/passivity.py`

**Interfaces:**
- Produces: `_adaptive_violation_frequencies(...) -> list[dict[str, Any]]`
- Consumes later: `enforce_passivity_hamiltonian()` will use each dict's `frequency_hz`, `max_sigma`, and diagnostic fields.

- [ ] **Step 1: Write failing tests**

Add tests to `tests/test_sparam_passivity.py`:

```python
def test_adaptive_violation_sampler_refines_sharp_midband_peak():
    def evaluate(freq_hz):
        sigma = 1.0 + 0.02 * np.exp(-((freq_hz - 5.0) / 0.35) ** 2)
        u = np.array([1.0 + 0.0j, 0.0 + 0.0j])
        v = np.array([1.0 + 0.0j, 0.0 + 0.0j])
        return sigma, u, v

    samples = _adaptive_violation_frequencies(
        intervals=[(0.0, 10.0)],
        evaluate=evaluate,
        epsilon=1e-6,
        passivity_margin=1e-4,
        max_refinement_passes=6,
        max_tracking_error=0.2,
        min_spacing_factor=0.1,
        max_samples=64,
    )

    assert any(abs(sample["frequency_hz"] - 5.0) <= 0.5 for sample in samples)
    assert max(sample["max_sigma"] for sample in samples) > 1.015
    assert max(sample["refinement_pass"] for sample in samples) >= 1


def test_adaptive_violation_sampler_refines_on_vector_tracking_error():
    def evaluate(freq_hz):
        angle = 0.0 if freq_hz < 5.0 else np.pi / 2.0
        u = np.array([np.cos(angle), np.sin(angle)], dtype=complex)
        v = u.copy()
        return 1.002, u, v

    samples = _adaptive_violation_frequencies(
        intervals=[(0.0, 10.0)],
        evaluate=evaluate,
        epsilon=1e-6,
        passivity_margin=1e-4,
        max_refinement_passes=4,
        max_tracking_error=0.2,
        min_spacing_factor=0.1,
        max_samples=64,
    )

    assert len(samples) > 3
    assert any(sample["tracking_error"] > 0.2 for sample in samples)
```

- [ ] **Step 2: Import the new helper**

Add `_adaptive_violation_frequencies` to the import list in `tests/test_sparam_passivity.py`.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py::test_adaptive_violation_sampler_refines_sharp_midband_peak tests/test_sparam_passivity.py::test_adaptive_violation_sampler_refines_on_vector_tracking_error -q
```

Expected: fails with import error or missing helper.

### Task 3: Implement Adaptive Violation Sampling

**Files:**
- Modify: `src/agent_spice/sparam/passivity.py`
- Test: `tests/test_sparam_passivity.py`

**Interfaces:**
- Consumes: intervals `(f_start, f_end)` and an evaluator returning `(max_sigma, left_vector, right_vector)`.
- Produces: sorted violating sample dicts with keys `frequency_hz`, `max_sigma`, `tracking_error`, `curvature_error`, `refinement_pass`.

- [ ] **Step 1: Implement helper functions**

Add these helpers above `enforce_passivity_hamiltonian()`:

```python
def _vector_overlap(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = float(np.linalg.norm(a))
    b_norm = float(np.linalg.norm(b))
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return float(abs(np.vdot(a, b)) / (a_norm * b_norm))


def _adaptive_violation_frequencies(
    *,
    intervals: list[tuple[float, float]],
    evaluate: Callable[[float], tuple[float, np.ndarray, np.ndarray]],
    epsilon: float,
    passivity_margin: float,
    max_refinement_passes: int,
    max_tracking_error: float,
    min_spacing_factor: float,
    max_samples: int,
) -> list[dict[str, Any]]:
    records: dict[float, dict[str, Any]] = {}
    queue: list[tuple[float, float, int]] = []
    for f_start, f_end in intervals:
        if f_end < f_start:
            f_start, f_end = f_end, f_start
        queue.append((float(f_start), float(f_end), 0))

    def record(freq_hz: float, refinement_pass: int) -> dict[str, Any]:
        key = float(freq_hz)
        if key not in records:
            sigma, u_vec, v_vec = evaluate(key)
            records[key] = {
                "frequency_hz": key,
                "max_sigma": float(sigma),
                "left_vector": np.asarray(u_vec, dtype=complex),
                "right_vector": np.asarray(v_vec, dtype=complex),
                "tracking_error": 0.0,
                "curvature_error": 0.0,
                "refinement_pass": int(refinement_pass),
            }
        else:
            records[key]["refinement_pass"] = max(int(records[key]["refinement_pass"]), int(refinement_pass))
        return records[key]

    while queue and (max_samples <= 0 or len(records) < max_samples):
        f_start, f_end, refinement_pass = queue.pop(0)
        if f_end == f_start:
            record(f_start, refinement_pass)
            continue
        left = record(f_start, refinement_pass)
        right = record(f_end, refinement_pass)
        mid_freq = 0.5 * (f_start + f_end)
        mid = record(mid_freq, refinement_pass + 1)

        left_overlap = min(
            _vector_overlap(left["left_vector"], mid["left_vector"]),
            _vector_overlap(left["right_vector"], mid["right_vector"]),
        )
        right_overlap = min(
            _vector_overlap(mid["left_vector"], right["left_vector"]),
            _vector_overlap(mid["right_vector"], right["right_vector"]),
        )
        tracking_error = 1.0 - min(left_overlap, right_overlap)
        curvature_error = float(mid["max_sigma"] - 0.5 * (left["max_sigma"] + right["max_sigma"]))
        mid["tracking_error"] = max(float(mid["tracking_error"]), tracking_error)
        mid["curvature_error"] = max(float(mid["curvature_error"]), curvature_error)

        interval_width = abs(f_end - f_start)
        min_width = max(abs(f_start), abs(f_end), 1.0) * min_spacing_factor
        should_refine = (
            refinement_pass < max_refinement_passes
            and interval_width > min_width
            and (
                tracking_error > max_tracking_error
                or curvature_error > passivity_margin
                or mid["max_sigma"] > 1.0 + epsilon
            )
        )
        if should_refine:
            queue.append((f_start, mid_freq, refinement_pass + 1))
            queue.append((mid_freq, f_end, refinement_pass + 1))

    violating = [
        record
        for record in records.values()
        if float(record["max_sigma"]) > 1.0 + epsilon
    ]
    violating.sort(key=lambda item: (-float(item["max_sigma"]), float(item["frequency_hz"])))
    if max_samples > 0:
        violating = violating[:max_samples]
    for record in violating:
        record.pop("left_vector", None)
        record.pop("right_vector", None)
    return sorted(violating, key=lambda item: float(item["frequency_hz"]))
```

- [ ] **Step 2: Run the new unit tests**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py::test_adaptive_violation_sampler_refines_sharp_midband_peak tests/test_sparam_passivity.py::test_adaptive_violation_sampler_refines_on_vector_tracking_error -q
```

Expected: both tests pass.

### Task 4: Integrate Adaptive Sampling Into `enforce_passivity_hamiltonian`

**Files:**
- Modify: `src/agent_spice/sparam/passivity.py`
- Modify: `tests/test_sparam_passivity.py`

**Interfaces:**
- Consumes: `check_passivity_hamiltonian_s()` crossover frequencies.
- Produces: `violating_freqs` from adaptive samples instead of fixed 5-point grids.

- [ ] **Step 1: Add enforcement parameters with internal defaults**

Extend `enforce_passivity_hamiltonian()` signature:

```python
    passivity_margin: float = 1e-4,
    adaptive_sampling: bool = True,
    max_refinement_passes: int = 6,
    max_tracking_error: float = 0.2,
    min_spacing_factor: float = 0.1,
```

- [ ] **Step 2: Add a test that adaptive sampling is default-on and perturbation remains default-off**

Update `test_hamiltonian_passivity_advanced_perturbations_are_experimental_opt_in()`:

```python
    assert signature.parameters["adaptive_sampling"].default is True
    assert signature.parameters["passivity_margin"].default == pytest.approx(1e-4)
    assert signature.parameters["perturb_constant"].default is False
    assert signature.parameters["perturb_poles"].default is False
```

- [ ] **Step 3: Replace the fixed 5-point interval scan**

In `enforce_passivity_hamiltonian()`, replace the loop that builds `violating_freqs` using `np.linspace(f_start, f_end, 5)` with:

```python
        intervals = [(points[i], points[i + 1]) for i in range(len(points) - 1)]

        def evaluate_violation_sample(freq_hz: float) -> tuple[float, np.ndarray, np.ndarray]:
            s_val = 1j * 2.0 * np.pi * float(freq_hz)
            S_f = constant_coeff.reshape((nports, nports)).copy().astype(complex)
            residue_cube = residues.reshape((nports, nports, len(poles)))
            for k in range(len(poles)):
                S_f += residue_cube[:, :, k] / (s_val - poles[k])
            U, sigmas, Vh = la.svd(S_f)
            max_idx = int(np.argmax(sigmas))
            return float(sigmas[max_idx]), U[:, max_idx], Vh.conj().T[:, max_idx]

        if adaptive_sampling:
            violation_records = _adaptive_violation_frequencies(
                intervals=intervals,
                evaluate=evaluate_violation_sample,
                epsilon=epsilon,
                passivity_margin=passivity_margin,
                max_refinement_passes=max_refinement_passes,
                max_tracking_error=max_tracking_error,
                min_spacing_factor=min_spacing_factor,
                max_samples=max_violation_samples if max_violation_samples > 0 else 0,
            )
            violating_freqs = [
                (float(record["frequency_hz"]), float(record["max_sigma"]))
                for record in violation_records
            ]
        else:
            violating_freqs = []
            for f_start, f_end in intervals:
                grid = np.linspace(f_start, f_end, 5)
                max_sigma_val = -np.inf
                max_f = f_start
                for f in grid:
                    sigma, _u_vec, _v_vec = evaluate_violation_sample(float(f))
                    if sigma > max_sigma_val:
                        max_sigma_val = sigma
                        max_f = float(f)
                if max_sigma_val > 1.0 + epsilon:
                    violating_freqs.append((max_f, max_sigma_val))
            violation_records = [
                {"frequency_hz": float(freq), "max_sigma": float(sigma), "refinement_pass": 0}
                for freq, sigma in violating_freqs
            ]
```

- [ ] **Step 4: Record sampling diagnostics once per iteration**

Immediately after `current_score` is built, append:

```python
        diagnostics.append({
            "iteration": int(iteration),
            "stage": "violation_sampling",
            "adaptive_sampling": bool(adaptive_sampling),
            "sample_count": int(len(violation_records)),
            "max_refinement_pass": int(max((record.get("refinement_pass", 0) for record in violation_records), default=0)),
            "max_tracking_error": float(max((record.get("tracking_error", 0.0) for record in violation_records), default=0.0)),
            "max_curvature_error": float(max((record.get("curvature_error", 0.0) for record in violation_records), default=0.0)),
        })
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py -q
```

Expected: all passivity tests pass.

### Task 5: Add Passivity Margin To QP Constraints And Acceptance

**Files:**
- Modify: `src/agent_spice/sparam/passivity.py`
- Modify: `tests/test_sparam_passivity.py`

**Interfaces:**
- Consumes: `passivity_margin` from `enforce_passivity_hamiltonian()`.
- Produces: constraints that aim below one, not exactly at one.

- [ ] **Step 1: Add a focused margin test**

Add a test using a tiny 1-port fake model that runs `enforce_passivity_hamiltonian(..., passivity_margin=1e-3)` and asserts diagnostics contain the configured margin:

```python
def test_enforce_passivity_hamiltonian_records_passivity_margin():
    class FakeVectorFit:
        def __init__(self):
            self.poles = np.array([-1.0])
            self.residues = np.array([[0.2]])
            self.constant_coeff = np.array([1.01])

    vf = FakeVectorFit()
    enforce_passivity_hamiltonian(
        vf,
        nports=1,
        max_iterations=1,
        passivity_margin=1e-3,
        adaptive_sampling=False,
    )

    assert any(
        item.get("passivity_margin") == pytest.approx(1e-3)
        for item in vf.passivity_enforcement_diagnostics
    )
```

- [ ] **Step 2: Change QP bound**

Where QP rows are assembled, replace:

```python
                b_val = 1.0 - sm
```

with:

```python
                b_val = (1.0 - passivity_margin) - sm
```

- [ ] **Step 3: Add `passivity_margin` to diagnostics**

Add:

```python
                    diagnostic["passivity_margin"] = float(passivity_margin)
```

to QP attempt diagnostics before appending.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py -q
```

Expected: all passivity tests pass.

### Task 6: Benchmark Adaptive Sampling On Test16

**Files:**
- Modify: `docs/sparam-large-port-idem-benchmark.md`
- Generated only: `runs-sparam/passivity-idem-inspired/test16-*`

**Interfaces:**
- Consumes: current Test16 model generated by the native flow.
- Produces: benchmark row comparing current fallback, adaptive sampling, and IdEM standalone passivity.

- [ ] **Step 1: Run the existing relevant tests first**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run formatting check**

Run:

```powershell
git diff --check
```

Expected: exit code 0. CRLF warnings are acceptable if no whitespace errors are reported.

- [ ] **Step 3: Run Test16 passivity benchmark**

Use the same command pattern as the previous Test16 passivity run and write the output to:

```text
runs-sparam/passivity-idem-inspired/test16-adaptive-sampling/
```

Record:

```text
max_sigma_before
max_sigma_after
violation_count_before
violation_count_after
mean_rms
elapsed_seconds
peak_memory_mb
adaptive sample count
max refinement pass
max tracking error
candidate reject reasons
```

- [ ] **Step 4: Update benchmark doc**

Append a table row in `docs/sparam-large-port-idem-benchmark.md` using the actual numeric values from the generated JSON/log. A completed row must have this shape and must contain numbers before commit:

```markdown
| Native adaptive violation sampler | Test16 order10 | `1.027606` | `1.006500` | `0.001840` | `52.3` | `310.0` | `adaptive samples=41, max_refinement=4` |
```

The numeric values above are an example format only; overwrite them with the measured run values from the current experiment before committing.

### Task 7: Add In-Band Low-Pass Acceptance Weighting If Adaptive Sampling Alone Stalls

**Files:**
- Modify: `src/agent_spice/sparam/passivity.py`
- Modify: `tests/test_sparam_passivity.py`

**Interfaces:**
- Produces: `_lowpass_passivity_holdout_weights(freqs, f_band_max, stopband_factor=1.05, stop_attenuation_db=40.0) -> np.ndarray`
- Consumes later: line-search acceptance compares weighted in-band holdout regression before accepting a candidate.

- [ ] **Step 1: Add weighting tests**

Add:

```python
def test_lowpass_passivity_holdout_weights_preserve_inband_more_than_outband():
    weights = _lowpass_passivity_holdout_weights(
        np.array([0.5e9, 1.0e9, 1.1e9, 2.0e9]),
        f_band_max=1.0e9,
        stopband_factor=1.05,
        stop_attenuation_db=40.0,
    )

    assert weights[0] == pytest.approx(1.0)
    assert weights[1] == pytest.approx(1.0)
    assert weights[2] < weights[1]
    assert weights[3] <= pytest.approx(0.01)
```

- [ ] **Step 2: Implement the helper**

Add:

```python
def _lowpass_passivity_holdout_weights(
    freqs: np.ndarray,
    *,
    f_band_max: float,
    stopband_factor: float = 1.05,
    stop_attenuation_db: float = 40.0,
) -> np.ndarray:
    freqs = np.asarray(freqs, dtype=float)
    if f_band_max <= 0.0:
        return np.ones_like(freqs, dtype=float)
    stop_freq = f_band_max * stopband_factor
    min_weight = 10.0 ** (-stop_attenuation_db / 20.0)
    weights = np.ones_like(freqs, dtype=float)
    transition = (freqs - f_band_max) / max(stop_freq - f_band_max, np.finfo(float).eps)
    transition = np.clip(transition, 0.0, 1.0)
    weights = min_weight + (1.0 - min_weight) * (1.0 - transition) ** 2
    weights[freqs <= f_band_max] = 1.0
    weights[freqs >= stop_freq] = min_weight
    return weights
```

- [ ] **Step 3: Integrate only into acceptance diagnostics first**

Before changing acceptance criteria, compute weighted holdout max before/after and record it in diagnostics. Do not reject based on it until one benchmark shows whether it predicts RMS preservation.

- [ ] **Step 4: Benchmark and decide**

Run Test16. Enable weighted rejection only if weighted holdout regression correlates with observed RMS damage.

### Task 8: Evaluate Curve-Budget Variants

**Files:**
- Modify: `src/agent_spice/sparam/passivity.py`
- Modify: `tests/test_sparam_passivity.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: SVD modes from `_singular_violation_modes()`.
- Produces: optional internal cap for number of singular curves per frequency and per iteration.

- [ ] **Step 1: Add diagnostics before behavior**

Record:

```python
diagnostic["singular_modes_used"] = int(len(A_list))
diagnostic["violating_frequency_count"] = int(len(violating_freqs))
diagnostic["constraints_per_frequency_mean"] = float(len(A_list) / max(len(violating_freqs), 1))
```

- [ ] **Step 2: Benchmark without cap**

Use current default first. For S-parameters, IdEM docs allow all non-passive curves when memory allows.

- [ ] **Step 3: Try caps only if memory grows**

Try internal values `8`, `16`, `32`, and unbounded. Keep the smallest cap that produces the same or better `max_sigma_after` on Test16 with lower memory.

### Task 9: Revisit Constant/Pole Perturbation Only After Residue-Only Plateau

**Files:**
- Modify: `docs/sparam-large-port-idem-benchmark.md`
- Optional modify: `src/agent_spice/sparam/passivity.py`
- Test: existing tests from `tests/test_sparam_passivity.py`

**Interfaces:**
- Consumes: current opt-in `perturb_constant` and `perturb_poles`.
- Produces: decision record on whether to keep, remove, or quarantine these options.

- [ ] **Step 1: Benchmark residue-only best path**

Use the best version from Tasks 4-8.

- [ ] **Step 2: Benchmark constant perturbation opt-in**

Run the same Test16 model with `perturb_constant=True` and `perturb_poles=False`.

- [ ] **Step 3: Benchmark pole perturbation opt-in**

Run the same Test16 model with `perturb_constant=False` and `perturb_poles=True`.

- [ ] **Step 4: Decide based on table**

Document one of these decisions:

```markdown
- Keep opt-in: improves `max_sigma_after` by at least 20% without increasing RMS by more than 5% and without increasing peak memory by more than 10%.
- Quarantine: improves one metric but regresses RMS, runtime, or memory.
- Remove: does not improve `max_sigma_after` compared with residue-only best path.
```

### Task 10: Commit A Small, Reviewable Slice

**Files:**
- Stage only files touched by the completed slice.

**Interfaces:**
- Produces: a commit that can be reviewed independently.

- [ ] **Step 1: Inspect status**

Run:

```powershell
git status --short
```

Expected: `.reasonix/*` may be dirty and must not be staged.

- [ ] **Step 2: Run final verification**

Run:

```powershell
python -m pytest tests/test_sparam_passivity.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py -q
git diff --check
```

Expected: tests pass and diff check has no whitespace errors.

- [ ] **Step 3: Stage source, tests, and docs**

Run:

```powershell
git add src/agent_spice/sparam/passivity.py src/agent_spice/sparam/fitting.py tests/test_sparam_passivity.py tests/test_sparam_fitting.py docs/sparam-large-port-idem-benchmark.md docs/superpowers/plans/2026-07-07-idem-passivity-enforcement.md
```

- [ ] **Step 4: Commit**

Run:

```powershell
git commit -m "plan idem inspired passivity enforcement"
```

If implementation tasks are included in the same slice, use:

```powershell
git commit -m "improve passivity violation sampling"
```

## Combination Strategy

Try combinations in this order:

1. Adaptive sampling only.
2. Adaptive sampling plus `passivity_margin=1e-4`.
3. Adaptive sampling plus margin plus wider holdout neighborhood.
4. Add low-pass weighted diagnostics.
5. Turn weighted diagnostics into acceptance rejection only if RMS preservation improves.
6. Try singular-curve budget caps only if memory rises.
7. Re-test constant/pole perturbation only if residue-only still plateaus above `max_sigma=1.001`.

Stop early if a combination reaches `max_sigma <= 1.0001` on Test16 with RMS increase under 5%, peak memory under 250 MB, and runtime under 30 seconds. At that point, freeze the path and test another large-port case before adding more complexity.

## Self-Review

- Spec coverage: the plan records every IdEM option inspiration currently identified and turns the highest-confidence items into implementation tasks.
- Empty-work scan: the plan contains concrete work items. Task 6 includes a numeric example row and explicitly requires overwriting it with measured values before commit.
- Type consistency: helper names and parameter names are consistent across tests and implementation tasks.
- Risk check: pole/constant perturbation remains opt-in and delayed; the first implementation changes sampling and constraints only.
