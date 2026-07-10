# Full-Corpus Native/IdEM Benchmark Design

## Objective

Replace the accumulated S-parameter benchmark narrative with one reproducible,
machine-audited comparison of the production native fitter and CST IdEM. The
benchmark runs every Touchstone file under `user_input/spara`, targets a final
mean S-RMS of `0.001`, enforces passivity, and compares the minimum accepted
order, end-to-end target-search time, and peak process-tree RSS.

The benchmark must not reuse historical conclusions or promote a near miss as
a pass. A case passes only when the final post-enforcement model satisfies both
the accuracy and passivity contracts.

## Corpus

The fixed corpus contains exactly these six files:

- `user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p`
- `user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p`
- `user_input/spara/Test13.s60p`
- `user_input/spara/Test16.s91p`
- `user_input/spara/Test11.s163p`
- `user_input/spara/Test3.s166p`

Corpus discovery accepts only filenames matching `.s<ports>p`, case
insensitively. It must not treat SPICE `.sp` files as Touchstone files. Before
running either tool, the harness records each file's relative path, SHA-256,
byte size, port count, frequency-point count, frequency bounds, and reference
impedance metadata in `manifest.json`.

## Fairness Contract

Both tools use the same immutable contract:

- RMS target: `0.001`.
- RMS formula: `sqrt(mean(abs(S_fit - S_raw) ** 2))` over every original
  frequency and every port-pair response.
- Passivity target: authoritative full-model passivity plus
  `max_sigma <= 1 + 1e-6`.
- Maximum effective common-pole order: `100`.
- Order formula: `real_poles + 2 * complex_pairs`.
- Frequency training set: every original Touchstone frequency point.
- Frequency audit set: every original Touchstone frequency point, with no
  interpolation when comparing exported IdEM data.
- Thread budget: 8 threads for IdEM and 8 threads for BLAS/OpenMP-backed native
  work (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and
  `NUMEXPR_NUM_THREADS`).
- Execution: one tool and one corpus case at a time. Native and IdEM runs never
  overlap.
- Per-phase timeout: 2 hours.

The target-search schedule is `4, 6, 8, ... 100`. After the first passing even
order, the scheduler evaluates every untested integer between the previous
failed even order and the passing order. Each requested order is evaluated at
most once. This is the production scheduler contract, not a binary search;
vector-fitting quality is not assumed to be monotonic in order.

A trial is accepted only from its final post-enforcement model. A pre-passivity
RMS above the target permits the passivity phase to be skipped, because that
trial cannot satisfy the final contract. Missing metrics, timeouts, order
mismatches, frequency-grid mismatches, checker disagreement, or non-finite
values fail the trial rather than being ignored.

## Native Path

Native runs use the public target-driven workflow equivalent to:

```powershell
python -m agent_spice.cli fit-sparam INPUT.sNp `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 100 `
  --output OUTPUT.sp `
  --report REPORT.json
```

The benchmark launches this workflow in a monitored subprocess with the fixed
thread environment. The public workflow remains the source of truth for native
order scheduling, final RMS, Hamiltonian/adaptive passivity validation, output
absence on failure, phase timings, and selected model. The harness validates
the report contract and records external wall time and process-tree peak RSS so
the benchmark does not rely only on self-reported resource metrics.

## IdEM Path

IdEM uses the documented executables under
`C:/Program Files/CST Studio Suite 2026/AMD64`:

1. `idemmp_fitting.exe` performs a fixed-order full-grid fit using generated
   fitting XML, three initial iterations, the `0.001` target, no splitting, and
   asymptotic passivity enabled.
2. `idemmp_checkaccuracy.exe` measures full-input pre-enforcement RMS. If it is
   above `0.001`, the trial is rejected without running passivity.
3. `idemmp_passivity.exe` performs full passivity enforcement for eligible
   fits, using 8 threads and the documented Hamiltonian/SOC path.
4. `idemmp_checkaccuracy.exe` measures the final passive model. The final RMS,
   not the fit-stage RMS, controls acceptance.
5. A separate `idemmp_passivity.exe` check-only invocation verifies the final
   model and captures the final reported maximum singular value.

After an IdEM order first passes, `idemmp_export.exe` exports the selected model
as S-parameter Touchstone data with `pre-stored` frequencies. An independent
auditor loads the original and exported Touchstone files, requires equal point
counts and matching frequencies, computes `mean_s_rms_v1`, and computes sampled
max sigma on every raw frequency. IdEM's accuracy result and the independent
RMS must agree within `max(1e-9, 1e-5 * target)`; otherwise the comparison cell
is invalid. The authoritative passivity decision remains IdEM's full-model
checker, while sampled max sigma is retained as an independent holdout metric.

IdEM effective order comes from the generated fixed-order request and is
cross-checked against the `.mod.h5` split metadata. Any mismatch invalidates the
trial.

## Resource Accounting

Every executable phase is monitored at 50 ms intervals. Peak memory is the sum
of resident memory for the root process and all recursive children. Each trial
records fit, accuracy-check, enforcement, final-check, export, and independent
audit costs separately.

The primary time comparison is end-to-end target-search wall time, from the
first order attempt until selection or exhaustion at order 100. It includes all
orders attempted and every validation needed to make the target decision. The
post-selection independent export audit is reported separately so it cannot
silently inflate or hide either algorithm's search time. The primary memory
comparison is the maximum process-tree RSS among phases required for target
search. Independent audit memory is reported separately.

## Resumability and Storage

The canonical output root is:

`runs-sparam/full-corpus-target-0p001/`

It contains:

```text
manifest.json
summary.json
summary.csv
<case>/native/
<case>/idem/order<N>/
```

Each completed phase writes an atomic JSON record before the next phase starts.
`--resume` reuses a phase only when its contract version, input SHA-256, tool
identity, order, target, thread count, and relevant option fingerprint all
match. Interrupted, stale, or mismatched records are rerun.

The selected final model, selected exported Touchstone, generated option files,
logs, and all JSON reports are retained. Large unselected model binaries are
removed only after their metrics and logs are durably recorded. A timeout or
tool failure is recorded for that case, and the corpus runner continues with
the remaining cases.

## Output and Parity Decisions

`summary.json` is the sole source for generated conclusions. `summary.csv`
contains one row per corpus/tool pair and includes:

- input identity and frequency count;
- target status and failure reason;
- selected requested/effective order;
- pre/final mean RMS;
- authoritative and sampled max sigma;
- fit, passivity, validation, audit, and total-search time;
- peak search RSS and audit RSS;
- attempted orders and timeout status.

The Native-vs-IdEM parity row applies the established thresholds only to valid
cells:

```text
native final RMS <= 0.001
native final max sigma <= 1 + 1e-6
native order <= 1.25 * IdEM order
native target-search time <= 2.0 * IdEM target-search time
native peak search RSS <= 1.5 * IdEM peak search RSS
```

If IdEM itself does not reach the target by order 100, resource and raw metrics
remain visible but relative parity is `invalid_comparison`; IdEM failure is not
treated as a Native pass.

## Documentation Reset

The following historical documents are deleted because they mix incompatible
frequency grids, RMS definitions, order meanings, oracle-pole experiments, or
later-invalidated attribution conclusions:

- `docs/sparam-large-port-idem-benchmark.md`
- `docs/idem-init-probe.md`
- `docs/idem_algorithm_analysis.md`
- `docs/passivity_benchmark_analysis_Gemini.md`
- `docs/sparam-passivity-next-directions_GLM5p2.md`
- `docs/walkthrough.md`
- `docs/superpowers/plans/2026-07-07-idem-passivity-enforcement.md`
- `docs/superpowers/plans/2026-07-08-passivity-ground-truth-to-idem.md`
- `docs/superpowers/plans/2026-07-09-passivity-direction-validation-plan.md`
- `docs/superpowers/plans/2026-07-09-passivity-next-directions.md`
- `docs/superpowers/plans/2026-07-10-data-driven-full-pole-discovery.md`
- `docs/superpowers/plans/2026-07-10-randomized-loewner-common-poles.md`
- `docs/superpowers/plans/2026-07-10-pole-placement-direction-d.md`
- `docs/superpowers/plans/2026-07-10-pole-placement-d4-d6.md`

The target-driven S-parameter design and implementation plan remain because
they define the current product contract rather than a benchmark conclusion.
Unrelated project documents also remain.

After the run, `docs/sparam-idem-full-benchmark.md` is generated from
`summary.json`. It contains the exact command, environment, corpus hashes,
contract, complete result table, invalid/failed cells, and only conclusions
mechanically supported by those results. README links only to this canonical
benchmark document.

## Testing and Acceptance

Unit and integration tests cover:

- strict Touchstone corpus discovery;
- manifest hashing and metadata;
- shared order scheduling and no duplicate trials;
- IdEM fitting, accuracy, passivity, export, and log parsing;
- frequency-grid equality and independent mean-RMS calculation;
- report fingerprinting and resume invalidation;
- timeout/failure continuation;
- atomic result writes;
- CSV and Markdown generation from machine-readable summaries;
- missing/non-finite metric rejection;
- resource aggregation over all attempted orders.

Before the full corpus run, the harness performs a real Native/IdEM smoke on
`tests/fixtures/sparam/simple_through.s2p` with a relaxed RMS target and low
order cap. The full benchmark starts only after the smoke produces matching
frequency grids, parseable final metrics, and passive selected models.

The implementation is accepted when all automated tests pass, the six-case run
finishes or records explicit bounded failures, every valid selected model has a
successful independent audit, the generated Markdown exactly reflects
`summary.json`, and no deleted historical benchmark document is referenced by
README or remaining active documentation.
