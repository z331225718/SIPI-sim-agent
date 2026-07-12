# Full-Corpus Native/IdEM Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace historical S-parameter benchmark conclusions with one resumable six-file Native/IdEM comparison at final mean S-RMS `0.001`, enforced passivity, and effective order at most 100.

**Architecture:** Keep pure benchmark contracts, scheduling, corpus identity, resume fingerprints, audits, and summary generation in a focused `agent_spice.sparam.benchmark` module. Extend the existing IdEM adapter with documented accuracy and Touchstone-export commands. A thin script orchestrates sequential Native and IdEM runs, writes atomic per-phase records, and generates the only canonical benchmark Markdown from `summary.json`.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, hashlib, csv/json, NumPy, psutil, existing lightweight Touchstone loader, existing target-driven native fitter, CST IdEM 2026 command-line tools, pytest.

## Global Constraints

- Corpus is exactly the six `.s<ports>p` files in `user_input/spara`; `.sp` files are excluded.
- Final mean S-RMS target is `0.001` on all original frequencies and all port pairs.
- Final passivity requires authoritative checker success and `max_sigma <= 1 + 1e-6`.
- Effective order is `real poles + 2 * complex pairs`; maximum order is 100.
- Both tools use all raw frequency points and 8 computational threads.
- Search schedule is even orders 4 through 100 followed by adjacent odd-order backfill after the first even pass.
- One case/tool runs at a time; phases time out after 7200 seconds.
- Every reusable artifact is guarded by contract version, input SHA-256, options fingerprint, and tool identity.
- Missing/non-finite metrics and frequency/order mismatches fail closed.
- Tests are written and observed failing before production changes.
- Every task receives an inline code review before the next task.
- Execution is inline in the current session; no subagents are used.

---

### Task 1: Remove Historical Benchmark Conclusions

**Files:**
- Delete the 14 files listed under `Documentation Reset` in the approved design spec.
- Modify: `README.md`
- Test: `tests/test_benchmark_documentation.py`

**Interfaces:**
- Produces: a repository with no active links to deleted historical benchmark documents.
- Preserves: `docs/superpowers/specs/2026-07-10-target-driven-sparam-fit-design.md` and `docs/superpowers/plans/2026-07-10-target-driven-sparam-fit.md`.

- [ ] **Step 1: Write the failing documentation-reference test**

```python
from pathlib import Path


DELETED_BENCHMARK_DOCS = {
    "docs/sparam-large-port-idem-benchmark.md",
    "docs/idem-init-probe.md",
    "docs/idem_algorithm_analysis.md",
    "docs/passivity_benchmark_analysis_Gemini.md",
    "docs/sparam-passivity-next-directions_GLM5p2.md",
    "docs/walkthrough.md",
    "docs/superpowers/plans/2026-07-07-idem-passivity-enforcement.md",
    "docs/superpowers/plans/2026-07-08-passivity-ground-truth-to-idem.md",
    "docs/superpowers/plans/2026-07-09-passivity-direction-validation-plan.md",
    "docs/superpowers/plans/2026-07-09-passivity-next-directions.md",
    "docs/superpowers/plans/2026-07-10-data-driven-full-pole-discovery.md",
    "docs/superpowers/plans/2026-07-10-randomized-loewner-common-poles.md",
    "docs/superpowers/plans/2026-07-10-pole-placement-direction-d.md",
    "docs/superpowers/plans/2026-07-10-pole-placement-d4-d6.md",
}


def test_historical_benchmark_docs_are_removed_and_readme_points_to_canonical_report():
    assert not [path for path in DELETED_BENCHMARK_DOCS if Path(path).exists()]
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/sparam-idem-full-benchmark.md" in readme
    assert "docs/sparam-large-port-idem-benchmark.md" not in readme
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest tests/test_benchmark_documentation.py -q`

Expected: the test lists existing historical documents and the old README link.

- [ ] **Step 3: Delete only the approved documents and update README**

Use `apply_patch` deletions. Replace the old benchmark link with
`docs/sparam-idem-full-benchmark.md`. Do not delete the target-driven spec or
plan, and do not stage `.reasonix`, `.workbuddy`, unrelated research code, or
other user changes.

- [ ] **Step 4: Run the test and inspect the deletion diff**

Run: `python -m pytest tests/test_benchmark_documentation.py -q`

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add README.md tests/test_benchmark_documentation.py
git add -u -- docs
git commit -m "docs: remove superseded S-parameter benchmarks"
```

---

### Task 2: Add IdEM Accuracy and Touchstone Export Adapters

**Files:**
- Modify: `src/agent_spice/sparam/idem.py`
- Modify: `tests/test_sparam_idem.py`

**Interfaces:**
- Produces: `parse_idem_accuracy_report(text: str) -> dict[str, Any]`.
- Produces: `run_idem_accuracy_check(touchstone_path, model_path, report_path, *, idem_bin_dir=None, timeout_seconds=None) -> dict[str, Any]`.
- Produces: `run_idem_touchstone_export(model_path, output_path, *, idem_bin_dir=None, timeout_seconds=None) -> dict[str, Any]`.

- [ ] **Step 1: Write failing accuracy parser tests**

```python
def test_parse_idem_accuracy_report_extracts_full_grid_metrics():
    report = """** No. of ports: 91
** No. of samples: 611
** Max Err: 0.0921744123
** RMS Err: 0.001174775322
"""
    parsed = parse_idem_accuracy_report(report)
    assert parsed == {
        "ports": 91,
        "frequency_points": 611,
        "max_error": pytest.approx(0.0921744123),
        "mean_rms": pytest.approx(0.001174775322),
    }


def test_parse_idem_accuracy_report_rejects_missing_rms():
    with pytest.raises(ValueError, match="RMS Err"):
        parse_idem_accuracy_report("** No. of samples: 611")
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_sparam_idem.py -q`

Expected: import failure for `parse_idem_accuracy_report`.

- [ ] **Step 3: Implement strict report parsing**

Parse `No. of ports`, `No. of samples`, `Max Err`, and `RMS Err` with anchored
regular expressions. Require finite non-negative metrics and positive integer
counts.

- [ ] **Step 4: Write failing command-wrapper tests**

Mock `_run_command` and assert exact documented commands:

```python
assert accuracy_command == [
    str(bin_dir / "idemmp_checkaccuracy.exe"),
    "-its", str(touchstone),
    "-ih5m", str(model),
    "-r", str(report),
]
assert export_command == [
    str(bin_dir / "idemmp_export.exe"),
    "-ih5", str(model),
    "-o", str(exported),
    "-type", "2",
]
```

IdEM success is artifact-based because the 2026 tools return code 1 after
successful accuracy/export operations. Accuracy requires a parseable report;
export requires a non-empty output Touchstone and the `Results` marker.

- [ ] **Step 5: Implement wrappers and serialization**

Return dictionaries containing `status`, input/output paths, command result,
and parsed metrics. Do not treat return code 1 alone as failure or success.

- [ ] **Step 6: Run tests and code review**

Run: `python -m pytest tests/test_sparam_idem.py -q`

Review path quoting, artifact checks, finite validation, and timeout propagation.

- [ ] **Step 7: Commit**

```powershell
git add src/agent_spice/sparam/idem.py tests/test_sparam_idem.py
git commit -m "feat: audit IdEM model accuracy and export"
```

---

### Task 3: Benchmark Contract, Corpus Manifest, and Shared Scheduler

**Files:**
- Create: `src/agent_spice/sparam/benchmark.py`
- Create: `tests/test_sparam_benchmark.py`

**Interfaces:**
- Produces: `BenchmarkContract` with contract version, target, epsilon, max order, threads, and timeout.
- Produces: `CorpusEntry` with identity and Touchstone metadata.
- Produces: `discover_touchstone_corpus(root: Path) -> tuple[CorpusEntry, ...]`.
- Produces: `run_benchmark_order_search(contract, evaluate_order) -> ToolSearchResult`.
- Produces: `atomic_write_json(path: Path, payload: dict) -> None`.

- [ ] **Step 1: Write failing strict-discovery tests**

Create `.s2p`, `.S19P`, and `.sp` files in `tmp_path`. Assert only the first two
are returned, sorted by `(ports, filename)`, with SHA-256 and byte size.

- [ ] **Step 2: Verify RED and implement corpus discovery**

Use `re.fullmatch(r"(?i).*\.s(\d+)p", path.name)`. Use
`load_touchstone_metadata()` for frequency count/range and stream SHA-256 in
1 MiB chunks.

- [ ] **Step 3: Write failing scheduler tests**

```python
def test_shared_scheduler_uses_even_ladder_then_odd_backfill():
    outcomes = {4: False, 6: False, 8: True, 7: True}
    calls = []
    result = run_benchmark_order_search(contract(max_order=10), evaluator(outcomes, calls))
    assert calls == [4, 6, 8, 7]
    assert result.selected_order == 7


def test_shared_scheduler_exhausts_at_100_without_duplicate_trials():
    result = run_benchmark_order_search(contract(max_order=100), always_fail)
    assert result.attempted_orders == tuple(range(4, 101, 2))
    assert len(result.attempted_orders) == len(set(result.attempted_orders))
```

- [ ] **Step 4: Implement immutable result types and scheduler**

Each `ToolTrial` contains requested/effective order, pre/final RMS, authoritative
passivity, final/sampled sigma, phase timings, peak RSS, target status, status,
failure reason, artifact paths, and fingerprint. Serialization converts all
non-finite floats to JSON `null`.

- [ ] **Step 5: Write atomic-write and fingerprint tests**

Assert temporary files are replaced atomically and resume fingerprints change
when the input hash, target, order, thread count, options, or tool identity
changes.

- [ ] **Step 6: Run tests and code review**

Run: `python -m pytest tests/test_sparam_benchmark.py -q`

Review deterministic ordering, no binary-search assumption, fail-closed metric
validation, and no deep-copy of model payloads.

- [ ] **Step 7: Commit**

```powershell
git add src/agent_spice/sparam/benchmark.py tests/test_sparam_benchmark.py
git commit -m "feat: define fair S-parameter benchmark contract"
```

---

### Task 4: Independent IdEM Touchstone Audit

**Files:**
- Modify: `src/agent_spice/sparam/benchmark.py`
- Modify: `tests/test_sparam_benchmark.py`

**Interfaces:**
- Produces: `audit_touchstone_model(original_path: Path, exported_path: Path, *, chunk_size=32) -> dict[str, Any]`.

- [ ] **Step 1: Write failing exact-grid audit tests**

Use the checked-in two-port fixture and a temporary exported copy. Assert exact
frequency count, frequency agreement, zero mean RMS, and sampled max sigma.
Create a second export with one shifted frequency and assert
`frequency_grid_mismatch` without interpolation.

- [ ] **Step 2: Verify RED and implement chunked audit**

Load both files with the lightweight RI Touchstone loader. Require identical
port count, point count, and frequencies under
`np.allclose(rtol=1e-12, atol=0)`. Compute:

```python
mean_rms = float(np.sqrt(np.mean(np.abs(exported.s - original.s) ** 2)))
sampled_max_sigma = max(
    float(np.linalg.svd(exported.s[index], compute_uv=False)[0])
    for index in range(len(exported.f))
)
```

Process frequency matrices in bounded chunks and release arrays after each
audit.

- [ ] **Step 3: Add agreement-gate tests**

`accuracy_agrees(reported, audited, target)` uses
`abs(reported-audited) <= max(1e-9, 1e-5*target)`. Missing values fail.

- [ ] **Step 4: Run tests and review memory behavior**

Run: `python -m pytest tests/test_sparam_benchmark.py -q`

- [ ] **Step 5: Commit**

```powershell
git add src/agent_spice/sparam/benchmark.py tests/test_sparam_benchmark.py
git commit -m "feat: independently audit exported IdEM models"
```

---

### Task 5: Resumable IdEM Target Search

**Files:**
- Create: `scripts/sparam_full_corpus_benchmark.py`
- Create: `tests/test_sparam_full_corpus_benchmark.py`
- Modify: `src/agent_spice/sparam/benchmark.py`

**Interfaces:**
- Produces: `run_idem_order_trial(entry, order, contract, output_dir) -> ToolTrial`.
- Produces: `run_idem_target_search(entry, contract, output_dir, *, resume=True) -> ToolSearchResult`.

- [ ] **Step 1: Write failing IdEM trial orchestration tests**

Inject fake fit/accuracy/passivity/export callables. Assert:

- pre-RMS `0.002` skips passivity and fails `pre_rms_above_target`;
- pre-RMS `0.0008`, passive final RMS `0.0011` fails
  `final_rms_above_target`;
- final RMS `0.0009`, check-only passive, sampled sigma `0.999` passes;
- check-only non-passive fails even when RMS passes;
- effective order mismatch fails;
- phase timeout is recorded and does not raise out of the corpus runner.

- [ ] **Step 2: Verify RED and implement one-order IdEM flow**

Generate fixed-order `IdemFittingOptions` with 8 threads, target `0.001`, three
initial iterations, no splitting, and asymptotic passivity enabled. Run fit,
pre-accuracy, conditional enforcement, final accuracy, and check-only. Record
all phase command results and use artifact-based IdEM completion rules.

- [ ] **Step 3: Write failing resume tests**

Write a completed `trial.json`, rerun with the same fingerprint, and assert no
fake phase callable runs. Change the input hash or threads and assert all phases
rerun. A truncated JSON must be treated as interrupted and rerun.

- [ ] **Step 4: Implement atomic phase records and cleanup**

Write `fit.json`, `pre_accuracy.json`, `enforce.json`, `final_accuracy.json`,
`final_check.json`, and `trial.json`. Retain selected model later; after a
failed trial is durably summarized, delete only its `.mod.h5` binaries.

- [ ] **Step 5: Implement IdEM scheduler and selected-model audit**

After selection, export the model with `-type 2`, run independent audit, require
reported/audited RMS agreement, and rewrite the selected trial atomically with
audit fields. If the audit fails, invalidate the trial and continue searching
higher orders rather than accepting it.

- [ ] **Step 6: Run tests and code review**

Run: `python -m pytest tests/test_sparam_full_corpus_benchmark.py tests/test_sparam_benchmark.py tests/test_sparam_idem.py -q`

Review final-vs-pre RMS use, authoritative check semantics, return-code-1
handling, order cross-check, and cleanup target safety.

- [ ] **Step 7: Commit**

```powershell
git add scripts/sparam_full_corpus_benchmark.py src/agent_spice/sparam/benchmark.py tests/test_sparam_full_corpus_benchmark.py
git commit -m "feat: run resumable IdEM target search"
```

---

### Task 6: Resumable Native Worker and Sequential Corpus Runner

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `scripts/sparam_full_corpus_benchmark.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_cli_fit_sparam.py`
- Modify: `tests/test_sparam_full_corpus_benchmark.py`

**Interfaces:**
- Removes the obsolete per-order target-search resume option because trials are no longer persisted.
- Produces: `run_native_target_search(entry, contract, output_dir, *, resume=True) -> ToolSearchResult`.
- Produces: `run_full_corpus(corpus_root, output_root, contract, *, resume=True) -> dict[str, Any]`.

- [ ] **Step 1: Write failing native-resume tests**

Create valid per-order `fit_report.json` plus model artifacts. Assert a resumed
target search reconstructs the trial without calling the fake fitter. Change
target/order/config/input fingerprint and assert the trial reruns. Assert a
resumed passing trial still copies only the selected model to the production
output.

- [ ] **Step 2: Verify RED and implement native trial fingerprints**

Each trial report stores `target_trial_contract_version`, input SHA-256,
requested order, target, passivity policy, full-grid point count, and serialized
config fingerprint. Resume only exact matches and parse metrics through
`trial_from_fit_result`-compatible reconstruction.

- [ ] **Step 3: Add hidden CLI wiring and tests**

The per-order target-search resume option is removed. Public defaults and target semantics remain unchanged.

- [ ] **Step 4: Write failing sequential-corpus tests**

Fake both tool runners and assert case order is deterministic, Native and IdEM
never overlap, a timeout in one tool/case is recorded, and later cases still
run. Assert manifest and case summaries are rewritten after every tool.

- [ ] **Step 5: Implement monitored Native subprocess and corpus loop**

Launch the public CLI with target `0.001`, enforce, max order 100, explicit
report paths, and the 8-thread environment. Monitor process-tree RSS at 50 ms.
Validate the top report and merge external wall/RSS metrics without replacing
the report's sum-over-all-trials timings.

- [ ] **Step 6: Run tests and code review**

Run: `python -m pytest tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py tests/test_sparam_full_corpus_benchmark.py -q`

Review resume fail-closed behavior, requested-output absence, subprocess
environment, process termination on timeout, and sequential execution.

- [ ] **Step 7: Commit**

```powershell
git add src/agent_spice/sparam/fitting.py src/agent_spice/cli.py scripts/sparam_full_corpus_benchmark.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py tests/test_sparam_full_corpus_benchmark.py
git commit -m "feat: run resumable full-corpus benchmark"
```

---

### Task 7: Canonical JSON, CSV, Markdown, and Parity Gates

**Files:**
- Modify: `src/agent_spice/sparam/benchmark.py`
- Modify: `scripts/sparam_full_corpus_benchmark.py`
- Modify: `tests/test_sparam_benchmark.py`
- Modify: `tests/test_sparam_full_corpus_benchmark.py`
- Generate after real run: `docs/sparam-idem-full-benchmark.md`

**Interfaces:**
- Produces: `build_corpus_summary(...) -> dict[str, Any]`.
- Produces: `write_benchmark_csv(summary, path) -> None`.
- Produces: `render_benchmark_markdown(summary) -> str`.

- [ ] **Step 1: Write failing parity and invalid-cell tests**

Assert valid cells apply exact gates: RMS target, epsilon, order ratio 1.25,
time ratio 2.0, memory ratio 1.5. Missing IdEM target success, hash mismatch,
frequency mismatch, or audit disagreement yields `invalid_comparison` rather
than parity success.

- [ ] **Step 2: Implement summary normalization and gates**

Ratios are `None` for missing/zero denominators. Overall parity requires six
valid passing cells; zero cells is false.

- [ ] **Step 3: Write failing CSV/Markdown snapshot tests**

Assert deterministic corpus order, explicit `FAIL`/`INVALID` labels, all metric
units, contract text, exact commands, input hashes, and no unsupported narrative
claim. Markdown must include a generated-file marker and summary JSON path.

- [ ] **Step 4: Implement generators**

Markdown is rendered only from the summary payload. It must not read historical
docs or infer root causes. The runner writes JSON first, then CSV and Markdown.

- [ ] **Step 5: Run tests and code review**

Run: `python -m pytest tests/test_sparam_benchmark.py tests/test_sparam_full_corpus_benchmark.py tests/test_sparam_target_parity.py -q`

- [ ] **Step 6: Commit**

```powershell
git add src/agent_spice/sparam/benchmark.py scripts/sparam_full_corpus_benchmark.py tests/test_sparam_benchmark.py tests/test_sparam_full_corpus_benchmark.py
git commit -m "feat: generate canonical IdEM benchmark reports"
```

---

### Task 8: Real Native/IdEM Smoke and Full Regression

**Files:**
- Modify only files owned by Tasks 2-7 if smoke exposes a defect.

- [ ] **Step 1: Run unit and integration suites**

```powershell
python -m pytest tests/test_sparam_idem.py tests/test_sparam_benchmark.py tests/test_sparam_full_corpus_benchmark.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py -q
python -m pytest -q
```

- [ ] **Step 2: Run real IdEM accuracy/export calibration**

Use the existing Test16 passive model to verify that successful IdEM 2026
accuracy/export operations return code 1 with valid artifacts. Confirm exported
default `-type 2` frequencies equal the stored input grid. Record this behavior
in an automated opt-in integration test or smoke report, not as a hard-coded
global return-code rule.

- [ ] **Step 3: Run real two-port smoke**

```powershell
python scripts/sparam_full_corpus_benchmark.py `
  --corpus-file tests/fixtures/sparam/simple_through.s2p `
  --output-root runs-sparam/full-corpus-target-0p001-smoke `
  --rms-target 0.5 `
  --max-order 4 `
  --threads 8 `
  --resume
```

Require both tools to produce parseable trials, equal export grids, independent
RMS audits, and passive final models.

- [ ] **Step 4: Review smoke artifacts and commit corrections**

Do not start the six-file run while any smoke comparison is invalid.

---

### Task 9: Execute the Six-File Benchmark and Publish the Canonical Result

**Files:**
- Generate: `runs-sparam/full-corpus-target-0p001/manifest.json`
- Generate: `runs-sparam/full-corpus-target-0p001/summary.json`
- Generate: `runs-sparam/full-corpus-target-0p001/summary.csv`
- Generate/track: `docs/sparam-idem-full-benchmark.md`
- Modify: `README.md` only if the final canonical link needs correction.

- [ ] **Step 1: Start or resume the full run**

```powershell
python scripts/sparam_full_corpus_benchmark.py `
  --corpus-root user_input/spara `
  --output-root runs-sparam/full-corpus-target-0p001 `
  --rms-target 0.001 `
  --passivity-epsilon 1e-6 `
  --max-order 100 `
  --threads 8 `
  --phase-timeout-seconds 7200 `
  --resume `
  --markdown docs/sparam-idem-full-benchmark.md
```

- [ ] **Step 2: Validate every completed cell**

Check manifest hashes, full frequency counts, requested/effective orders,
selected model existence, final RMS, authoritative passivity, sampled sigma,
phase timings, peak RSS, and audit agreement. A case that exhausted order 100
must have no promoted production model.

- [ ] **Step 3: Re-run the command with `--resume`**

The second run must reuse every valid phase, perform no fitting/passivity work,
and reproduce byte-identical `summary.csv` and Markdown apart from explicitly
excluded generation timestamps. Prefer omitting timestamps so all canonical
outputs are byte-identical.

- [ ] **Step 4: Run final regression and documentation-reference checks**

```powershell
python -m pytest -q
python -m pytest tests/test_benchmark_documentation.py -q
git diff --check
```

- [ ] **Step 5: Final code review**

Review against the approved spec: six exact inputs, full grid, target 0.001,
post-enforcement acceptance, order cap 100, 8 threads, sequential execution,
honest total search cost, fail-closed invalid comparisons, resumability, and no
historical narrative dependency.

- [ ] **Step 6: Commit code-independent benchmark evidence**

```powershell
git add docs/sparam-idem-full-benchmark.md README.md
git commit -m "bench: compare Native and IdEM on full S-parameter corpus"
```

## Completion Gate

The task is complete only when the historical documents are gone, the real
Native/IdEM smoke is valid, the full six-file command has finished or recorded
bounded explicit failures for every case/tool, the canonical Markdown is
generated from `summary.json`, a second `--resume` run performs no algorithm
work, and the full repository test suite passes from a clean checkout.
