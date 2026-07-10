# Randomized Loewner Common-Pole Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate low-order, stable, shared S-parameter pole sets directly from raw multiport data with randomized Loewner pencils, then determine whether those seeds are good enough to re-enable full-set variable projection.

**Architecture:** Deterministic random left/right port projections reduce the large S-matrix to several scalar transfer traces that share the original system poles. Their Loewner and shifted-Loewner matrices are vertically stacked, rank-truncated with one SVD, and projected to a small generalized eigenproblem. Stable conjugate-consistent eigenvalues become half-pair pole candidates, which are evaluated by the existing full-grid residue LS and RMS/sigma Pareto path.

**Tech Stack:** Python 3.11+, NumPy, SciPy `linalg`, existing `pole_discovery` candidate/evaluation APIs, scikit-rf Touchstone loading, pytest.

## Global Constraints

- Use all 611 Test16 frequency points for final residue fitting, RMS, and sigma evaluation.
- IdEM numerical poles and IdEM model files are forbidden in Loewner projection, pencil construction, rank selection, pole extraction, candidate selection, and objective functions.
- Random vectors, frequency partitions, and candidate order are deterministic under seed `20260710`.
- Candidate effective orders are exactly 6, 8, and 10. Reports distinguish requested Loewner rank, extracted stable order, stored pole count, real-pole count, and complex-pair count.
- Preserve real-system conjugate symmetry by augmenting positive-frequency projected traces with their negative-frequency conjugates; DC appears once.
- Reject non-finite, right-half-plane, unpaired, duplicate, or incomplete eigenvalue sets. Do not reflect unstable poles or silently pad candidates with heuristic poles.
- Candidate poles are half-pair representatives: real poles plus only positive-imaginary members of conjugate pairs, all with strictly negative real parts.
- Full-grid RMS is computed for every valid Loewner candidate; full-grid sigma is computed only for the RMS-best 8 candidates.
- Advance back to variable projection only if at least one candidate reaches both `mean_rms < 0.003` and `max_sigma < 1.03` at effective order `<=10`.
- The current fitting default and CLI remain unchanged. This plan creates research-only modules and scripts.
- Every task uses TDD, receives a fresh code review, fixes all Critical/Important findings, and records benchmark evidence before the next task.
- Existing unrelated dirty-worktree changes must not be reverted, reformatted, staged, or committed.

---

### Task 1: Stable Randomized Loewner Extractor

**Files:**
- Create: `src/agent_spice/sparam/pole_loewner.py`
- Create: `tests/test_sparam_pole_loewner.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `freqs_hz: np.ndarray`, `s_parameters: np.ndarray` shaped `(nfreq, nports, nports)`, requested effective orders, probe count, seed.
- Produces: `LoewnerConfig`, `LoewnerCandidateDiagnostics`, `project_sparameter_traces()`, `build_stacked_loewner_pencil()`, `extract_stable_half_pair_poles()`, and `discover_loewner_candidates()`.

- [ ] **Step 1: Write failing scalar pole-recovery tests**

Use a synthetic real continuous-time transfer function with poles `-2*pi*1e6`, `(-0.04 + 1j)*2*pi*25e6`, and its conjugate. Sample positive frequencies including DC, construct the Loewner pencil, and require an order-3 extraction near the true poles:

```python
def test_loewner_recovers_stable_real_system_poles():
    freqs = np.concatenate(([0.0], np.geomspace(1e4, 1e8, 160)))
    samples = evaluate_real_rational_response(freqs, TRUE_POLES, TRUE_RESIDUES)
    pencil = build_stacked_loewner_pencil(freqs, samples[np.newaxis, :])
    result = extract_stable_half_pair_poles(pencil, requested_order=3)

    assert result.accepted
    assert result.effective_order == 3
    assert nearest_relative_pole_error(result.poles, TRUE_HALF_PAIR_POLES) < 0.05
```

Add rejection tests for an all-constant trace, insufficient points, a requested order greater than numerical rank, and eigenvalues with no conjugate partner.

- [ ] **Step 2: Write failing deterministic multiport projection tests**

```python
def test_random_projections_are_deterministic_and_do_not_change_frequency_count():
    first = project_sparameter_traces(FREQS, S_MATRIX, probe_count=4, seed=20260710)
    second = project_sparameter_traces(FREQS, S_MATRIX, probe_count=4, seed=20260710)
    np.testing.assert_allclose(first, second)
    assert first.shape == (4, len(FREQS))
```

Verify each random probe vector has unit norm and projected traces equal `u.conj() @ S[f] @ v` for a small known matrix fixture.

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest tests\test_sparam_pole_loewner.py -q
```

Expected: collection failure because `pole_loewner` does not exist.

- [ ] **Step 4: Implement deterministic random projections and conjugate augmentation**

Add `scipy>=1.11` to direct dependencies in `pyproject.toml`.

Use these public types:

```python
@dataclass(frozen=True)
class LoewnerConfig:
    requested_orders: tuple[int, ...] = (6, 8, 10)
    probe_count: int = 4
    partition_count: int = 4
    seed: int = 20260710
    conjugate_tolerance: float = 1e-5
    duplicate_tolerance: float = 1e-3


@dataclass(frozen=True)
class LoewnerCandidateDiagnostics:
    requested_order: int
    numerical_rank: int
    singular_values: np.ndarray
    raw_eigenvalues: np.ndarray
    poles: np.ndarray
    effective_order: int
    accepted: bool
    rejection_reason: str | None
    partition_index: int
```

Generate independent deterministic complex-normal `u` and `v`, normalize each, and evaluate all probes with `np.einsum`. Augment traces as:

```python
positive = freqs_hz > 0.0
s_axis = np.concatenate((-2j * np.pi * freqs_hz[positive][::-1], 2j * np.pi * freqs_hz))
augmented = np.concatenate((np.conj(traces[:, positive][:, ::-1]), traces), axis=1)
```

Sort by imaginary frequency and assert there are no duplicate `s_axis` values.

- [ ] **Step 5: Implement stacked Loewner pencils**

For each deterministic partition, alternate the sorted augmented sample indices between left and right sets after a cyclic offset. For every projected trace `h_k`:

```python
L_k[i, j] = (h_k[mu_i] - h_k[lambda_j]) / (s_mu[i] - s_lambda[j])
Ls_k[i, j] = (s_mu[i] * h_k[mu_i] - s_lambda[j] * h_k[lambda_j]) / (s_mu[i] - s_lambda[j])
```

Vertically stack every `L_k` and `Ls_k`. Compute thin SVD `L = U @ diag(s) @ Vh`. For requested rank `r`, form:

```python
U_r = U[:, :r]
V_r = Vh.conj().T[:, :r]
E_r = U_r.conj().T @ L @ V_r
A_r = U_r.conj().T @ Ls @ V_r
raw_eigenvalues = scipy.linalg.eigvals(A_r, E_r)
```

Numerical rank uses `singular_value > singular_values[0] * max(L.shape) * eps`.

- [ ] **Step 6: Implement strict stable half-pair extraction**

Reject non-finite and `real >= -1e-12 * max(1, abs(pole))` eigenvalues. Cluster duplicates by relative distance `abs(a-b)/max(1,abs(a),abs(b)) <= duplicate_tolerance`. Real poles require `abs(imag) <= conjugate_tolerance * max(1,abs(pole))`; complex poles require one negative-imaginary conjugate within the same tolerance. Store the averaged positive-imaginary representative. Reject candidates whose resulting effective order differs from the requested order.

`discover_loewner_candidates()` must try all `(partition_index, requested_order)` combinations and return accepted diagnostics plus rejected diagnostics; it must not fabricate a candidate when extraction fails.

- [ ] **Step 7: Run focused tests and static verification**

```powershell
python -m pytest tests\test_sparam_pole_loewner.py tests\test_sparam_pole_discovery.py -q
python -m py_compile src\agent_spice\sparam\pole_loewner.py
```

Expected: all pass with no warnings.

- [ ] **Step 8: Review and commit**

Review conjugate augmentation, Loewner signs, projection shapes, generalized eigenvalue orientation, strict rejection behavior, deterministic partitions, and absence of oracle inputs. Commit only:

```powershell
git add pyproject.toml src\agent_spice\sparam\pole_loewner.py tests\test_sparam_pole_loewner.py
git commit -m "feat: extract common poles with randomized Loewner pencils"
```

---

### Task 2: Test16 Loewner Seed Benchmark

**Files:**
- Create: `scripts/sparam_loewner_pole_probe.py`
- Create: `tests/test_sparam_loewner_pole_probe.py`
- Modify: `docs/sparam-large-port-idem-benchmark.md`

**Interfaces:**
- Consumes: Task 1 `discover_loewner_candidates()`, `PoleCandidate`, `PoleTopology`, `evaluate_pole_candidates()`, and `pareto_front()`.
- Produces: `run_loewner_pole_probe()` plus an auditable `summary.json` and `benchmark_note.md`.

- [ ] **Step 1: Write failing runner-contract tests**

Mock raw data, candidate discovery, and candidate evaluation. Verify the runner uses all raw points, converts only accepted diagnostics to `PoleCandidate`, evaluates all candidates for RMS, limits full sigma to 8, and never receives an IdEM path:

```python
def test_probe_uses_full_grid_and_only_accepted_loewner_candidates(monkeypatch, tmp_path):
    result = probe.run_loewner_pole_probe(
        touchstone_path=tmp_path / "input.s2p",
        output_dir=tmp_path / "out",
        requested_orders=(6, 8, 10),
        probe_count=4,
        partition_count=4,
        seed=20260710,
    )
    assert result["reference_grid"] == {"training_frequency_points": 611, "evaluation_frequency_points": 611}
    assert result["full_sigma_candidate_count"] == 8
    assert result["oracle_policy"]["idem_numeric_poles_used"] is False
```

Add gate tests requiring both `RMS < 0.003`, `sigma < 1.03`, and order `<=10`.

- [ ] **Step 2: Implement the probe**

Use `LoewnerConfig(requested_orders=(6,8,10), probe_count=4, partition_count=4, seed=20260710)`. Convert accepted diagnostics to `PoleCandidate` with actual topology inferred from pole kinds. Fingerprints must include requested order, partition, and pole bytes. Preserve all rejected diagnostics in the report so extraction failure cannot disappear.

The decision schema is:

```python
{
    "advance_to_variable_projection": bool(passing),
    "stop_and_reassess": not bool(passing),
    "thresholds": {"mean_rms_lt": 0.003, "max_sigma_lt": 1.03, "effective_order_lte": 10},
    "passing_candidate_fingerprints": [...],
}
```

- [ ] **Step 3: Run tests**

```powershell
python -m pytest tests\test_sparam_loewner_pole_probe.py tests\test_sparam_pole_loewner.py tests\test_sparam_pole_discovery.py -q
```

- [ ] **Step 4: Run the fixed Test16 benchmark**

```powershell
python scripts\sparam_loewner_pole_probe.py `
  --touchstone user_input\spara\Test16.s91p `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d15-loewner `
  --orders 6,8,10 `
  --probe-count 4 `
  --partition-count 4 `
  --seed 20260710
```

The benchmark must report accepted/rejected candidate counts, rejection reasons, singular spectra, extracted poles/topologies, full-grid metrics, runtime, and peak RSS.

- [ ] **Step 5: Apply the decision**

- If at least one candidate passes, write a short follow-up plan that resumes the skipped variable-projection task using only the passing Loewner seeds.
- If none pass but the best candidate reaches `RMS < 0.005` and `sigma < 1.10`, do not tune rank/probe counts yet; first inspect pole geometry and write a targeted refinement plan.
- If the best candidate is outside those near-gate values or no valid candidates are extracted, stop this algorithm branch and reassess matrix/tangential Loewner or AAA with the local agent council. Do not silently increase order above 10.

- [ ] **Step 6: Review and commit**

Review full-grid semantics, strict candidate rejection, actual order, sigma budget, deterministic output, and decision correctness. Because the benchmark document is already dirty in the controller workspace, the implementer must leave its proposed documentation text in the report; the controller appends it after review. Commit only:

```powershell
git add scripts\sparam_loewner_pole_probe.py tests\test_sparam_loewner_pole_probe.py
git commit -m "test: benchmark Loewner common-pole seeds"
```

---

## Stop Rules

1. Reject any candidate that requires unstable-pole reflection, topology padding, or IdEM-derived values.
2. Do not evaluate sigma for more than the RMS-best 8 candidates.
3. Do not increase effective order above 10 in this plan.
4. Re-enable variable projection only when a Loewner seed satisfies `RMS < 0.003` and `sigma < 1.03`.
5. If no candidate reaches the near-gate `RMS < 0.005` and `sigma < 1.10`, stop and seek a new algorithmic design rather than adding Loewner knobs.

## Self-Review

- Coverage: deterministic projections, conjugate augmentation, stacked pencils, rank truncation, strict pole extraction, full-grid benchmark, and stop decisions are specified.
- Action completeness: every task names exact files, formulas, commands, thresholds, and expected decisions.
- Type consistency: Task 2 consumes the public types and functions introduced in Task 1.
- Fairness: IdEM values are excluded, all final metrics use 611 raw points, and order remains at most 10.
