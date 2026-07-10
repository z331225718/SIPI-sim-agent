# Large-Port S-Parameter IdEM Benchmark

Date: 2026-07-06

This note records the current large-port benchmark against CST IdEM using the shared target:

- Touchstone fit target: mean RMS error < 0.002
- IdEM path: `idemmp_fitting.exe`, fixed order sweep, initial iterations = 3, asymptotic passivity enabled
- Our path: lightweight Touchstone parser, native vector fitting backend, streaming reciprocal relocation, passivity check/enforce skipped
- No scikit-rf fitting path was used for our benchmark runs

## Summary

| Case | Ports | IdEM order | IdEM mean RMS | IdEM time | IdEM peak memory | Our order | Our mean RMS | Our time | Our peak memory | Our pole config |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `Test13.s60p` | 60 | 6 | 0.0019926 | 4.90 s | 155.5 MB | 10 | 0.0019846 | 4.64 s | 118.5 MB | real=2, complex=4 |
| `Test16.s91p` | 91 | 8 | 0.0011747 | 24.54 s | 414.2 MB | 17 | 0.0018906 | 19.14 s | 249.6 MB | real=7, complex=5 |
| `Test11.s163p` | 163 | 5 | 0.0018054 | 45.01 s | 1128.1 MB | 4 | 0.0017413 | 24.06 s | 681.9 MB | real=0, complex=2 |

## Interpretation

The native/lightweight path no longer shows a consistent speed or memory disadvantage under the current sampled-fit benchmark. On all three cases above it is faster and lower-memory than IdEM at the lowest order that reaches the target.

Important caveat recorded after re-checking the reports: the native runs in this table used `fit_frequency_points=256` while the original `Test13/Test16/Test11` files contain 611/611/542 points. The reported comparison RMS is still evaluated on `original_frequency_points`, so the accuracy number is not computed only on the training subset. However, the fitting cost/memory comparison is not apples-to-apples with IdEM if IdEM trains on the full frequency grid. For `Test16.s91p`, the IdEM `.mod.h5` contains `DUM/F` with 611 points and the fitting XML has no down-sampling option, so the conservative interpretation is: our 256-point native path is promising, but the previous fit conclusion does not prove similar performance at similar order and memory under full-frequency training.

The remaining gap is mainly pole/order efficiency, but it is not uniform:

- `Test13.s60p`: our path needs 10th order vs IdEM 6th order.
- `Test16.s91p`: our path needs 17th order vs IdEM 8th order. This is the clearest current pole-placement gap.
- `Test11.s163p`: our path reaches the target at 4th order vs IdEM 5th order.

Therefore the next algorithmic target should be `Test16.s91p`: reproduce why IdEM order 8 reaches 0.00117 while our order 8 remains above 0.006 even in the best low-order configuration.

## Artifacts

- Combined JSON: `runs-sparam/large-port-autofit-benchmark/combined_s60_s91_s163_summary.json`
- `Test13.s60p` detail: `runs-sparam/test13-s60p-autofit-benchmark/combined_autofit_summary.json`
- `Test16.s91p` detail: `runs-sparam/large-port-autofit-benchmark/Test16_s91p/summary.json`
- `Test11.s163p` detail: `runs-sparam/large-port-autofit-benchmark/Test11_s163p/summary.json`

## Known Follow-Up

Some very low-order native real/complex pole configurations currently raise `IndexError('arrays used as indices must be of integer (or boolean) type')`. This does not affect the reported lowest passing configurations, but it should be fixed before turning the low-order sweep into an automated benchmark.

## Native Passivity Enforcement Follow-Up

The first low-memory passivity integration pass moved native S-parameter fitting away from the native backend's no-op `passivity_enforce()` and onto the local Hamiltonian/residue-perturbation path. The path is now independent of the SPICE exporter, so `fit-sparam --check-passivity --enforce-passivity` uses the same low-memory engine with the default `skrf` exporter.

The native passivity path now defaults to the Touchstone data band when `passivity_f_max` is not explicitly set. This avoids treating unconstrained extrapolation above the measured band as a default signoff blocker. Asymptotic/passivity-beyond-band work remains a separate algorithm target.

`Test13.s60p` with the current IdEM-fast fit and low-memory passivity enabled:

| Run | Selected order | Mean RMS | Passive before | Passive after | Violation bands before | Violation bands after | Time | Peak memory |
|---|---:|---:|---|---|---:|---:|---:|---:|
| check only | 9 | 0.000593962 | false | false | 169 | 169 | 8.08 s | 177.9 MB |
| sparse enforce, 8 samples, rollback | 9 | 0.000593962 | false | false | 169 | 169 | 15.94 s | 181.1 MB |
| band-limited default | 9 | 0.000593962 | true | true | 0 | 0 | 8.47 s | 178.4 MB |

`Test16.s91p` with band-limited default passivity:

| Run | Selected order | Mean RMS | Max sigma before | Max sigma after | Passive before | Passive after | Violation bands before | Violation bands after | Time | Peak memory |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|
| band-limited default, 1 sparse iteration | 10 | 0.001819411 | 1.027606 | 1.027606 | false | false | 184 | 184 | 34.38 s selected trial, 87.9 s CLI wall time | 322.8 MB |
| fixed order10, 16 samples, 3 iterations, 512 active variables | 10 | 0.001819411 | 1.027606 | 1.027606 | false | false | 184 | 183 | 52.02 s | 343.0 MB |
| fixed order10, 16 samples, 3 iterations, 2048 active variables | 10 | 0.001821926 | 1.027606 | 1.009571 | false | false | 184 | 183 | 80.85 s | 344.8 MB |
| fixed order10, 16 samples, 3 iterations, 4096 active variables | 10 | 0.001819411 | 1.027606 | 1.027606 | false | false | 184 | 185 | 80.53 s | 346.4 MB |
| adaptive active variables up to 2048, sigma-first score | 10 | 0.001821926 | 1.027606 | 1.009571 | false | false | 184 | 188 | 62.72 s | 342.4 MB |
| adaptive active variables up to 3072, sigma-first score | 10 | 0.001822875 | 1.027606 | 1.009493 | false | false | 184 | 187 | 57.42 s | 344.7 MB |
| relative Tikhonov QP + holdout gate diagnostics, active variables up to 3072 | 10 | 0.001823711 | 1.027606 | 1.009509 | false | false | 184 | 182 | 68.48 s | 345.4 MB |
| adaptive active variables up to 3072, 32 samples | 10 | 0.001838170 | 1.027606 | 1.014153 | false | false | 184 | 181 | 64.64 s | 365.1 MB |
| local peak refinement, active variables up to 3072 | 10 | 0.001824085 | 1.027606 | 1.009469 | false | false | 184 | 185 | 73.81 s | 344.7 MB |
| local refinement + global damping fallback | 10 | 0.002169703 | 1.027606 | 1.000169 | false | false | 184 | 5 | 71.10 s | 345.1 MB |
| local refinement + global damping fallback | 12 | 0.061757421 | 2.761448 | 2.761448 | false | false | 775 | 775 | 100.17 s | 394.8 MB |

Interpretation:

- The memory target is now in the right range: `Test13.s60p` passivity check/enforce peaks around `178 MB`, and `Test16.s91p` peaks around `323 MB`, below the IdEM `Test16.s91p` peak of `414.2 MB`.
- For `Test13.s60p`, the apparent 169 violation bands were above the 2 GHz measured data range; the band-limited default is already passive.
- For `Test16.s91p`, band-limited passivity still fails with 184 violation bands. This is the next real enforcement target.
- A rollback guard is required and now active: if a residue perturbation worsens passivity score, the model keeps the best seen residues rather than silently destroying fit accuracy. Before this guard, the same sparse enforcement path could degrade mean RMS from `0.000593962` to `0.0673212` while still remaining non-passive.
- Increasing the active residue-variable budget can reduce violation amplitude without a major memory increase: 2048 active variables lowers max sigma from `1.027606` to `1.009571` at about `345 MB`. Larger is not automatically better; 4096 active variables regresses because the local QP becomes more ill-conditioned.
- The passivity acceptance score now prioritizes max singular value before violation-band count. Band count is too sensitive to tiny crossing movements; on `Test16.s91p`, the sigma-first adaptive run preserves the useful 2048/3072 improvement while avoiding the 4096 regression.
- The current default active-variable cap for explicit native passivity enforcement is `3072`. It is still memory-safe on `Test16.s91p` and gives the best observed max-sigma reduction in this pass.
- The QP diagnostic pass adds relative Tikhonov regularization and records active/dual conditioning, predicted vs actual improvement, selected line-search candidates, and holdout-neighborhood scores. It reproduces the same `1.0095` max-sigma stall, so the remaining gap is not explained by an unregularized dual solve or a hidden peak-shifting artifact in this configuration.
- Local peak refinement gives only a tiny max-sigma gain while adding time, so it is not enabled in the default path.
- Global damping proves that a cheap scalar fallback can nearly remove the remaining violation, but it pushes order10 RMS above the `0.002` target and still leaves a small residual violation. It should remain a diagnostic/fallback idea, not the default algorithm.

IdEM full passivity check/enforcement:

`idemmp_fitting.exe` only exposes fitting controls and the fitting XML only contains `enforceAsymptoticPassivity`, which corrects the high-frequency/asymptotic condition. Full model passivity is handled by the separate `idemmp_passivity.exe` command.

| IdEM model | Before full check | Full enforcement result | Exported sampled max sigma | Exported mean RMS |
|---|---|---|---:|---:|
| `Test16.s91p`, order8 init3 | 129 Hamiltonian imaginary eigenvalues, passive NO | SOC 2 iterations + HAM check, passive YES | 0.999985766 | 0.001174775 |
| `Test13.s60p`, order8 init3 | 22 Hamiltonian imaginary eigenvalues, passive NO | SOC 5 iterations + HAM check, passive YES | 0.999917309 | 0.001636927 |

The IdEM passivity command is now wrapped by `probe-idem-passivity`, so the Test16 order8 reference can be reproduced with:

```powershell
python -m agent_spice.cli probe-idem-passivity `
  runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\model.mod.h5 `
  --output-model runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\model_passive_cli.mod.h5 `
  --report runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\passivity_cli_report.json `
  --n-threads 8 `
  --ham-solver 3 `
  --timeout-seconds 240
```

The first CLI-wrapped run completed in `15.21 s`, peaked at `161.8 MB`, reported SOC peaks `1.00393 @ 1.998 GHz` and `1.00017 @ 1.954 GHz`, then HAM found `0` imaginary eigenvalues and marked `MOD/isPassive = 1`.

This confirms that IdEM can repair full model passivity with very small sampled-fit degradation, but this capability is not part of the fitting step we had previously benchmarked. The right target to reverse-engineer is therefore `idemmp_passivity.exe`: combined SOC/HAM enforcement, model-based/data-based weighting, sparse/adaptive Hamiltonian eigensolver, and local constraints.

Next target:

- Continue from `Test16.s91p`: the current sparse local-QP scaffolding is memory-safe and can reduce max sigma, but it stalls near `1.0095`. The next algorithm step should explicitly target IdEM's separate passivity engine behavior, especially fit-aware/data-aware residue perturbation and SOC/HAM iteration, rather than only increasing samples, iterations, or applying uniform response scaling.

## Test16.s91p Follow-Up

The first diagnosis pass focused on `Test16.s91p`, because it had the largest order gap.

Findings:

- Exporting IdEM order-8 to Touchstone with `idemmp_export.exe` and comparing the exported response to raw data gives mean RMS `0.0011747173504935177`, matching the IdEM-reported RMS. The gap is therefore not a reporting-definition mismatch.
- The input S matrix is numerically reciprocal: symmetry relative error is about `4.7e-16`, so the reciprocal relocation compression is not the cause.
- The current default order-8 native configuration is weak, but log-spaced initialization plus more relocation iterations narrows the gap substantially:
  - `real=4, complex=2, log spacing, 16 iterations, 256 fit points`: mean RMS `0.0023693`
  - best sampled density/iteration point found so far: `real=4, complex=2, log spacing, 17 iterations, 384 fit points`: mean RMS `0.0023016`
- IdEM order-8 poles include four real poles around `10.2 MHz`, `26.6 MHz`, `76.1 MHz`, `275.0 MHz`, plus two high-frequency complex pairs around `1.37 GHz` and `2.00 GHz`.
- Our best order-8 run tends to move one pole to an extremely high real frequency instead of preserving the high-frequency complex pairs. This points to pole relocation/constraint behavior rather than speed or memory.

The immediate algorithmic direction is to improve low-order pole relocation so high-frequency complex pairs are retained or reintroduced, instead of simply increasing order.

## Test16.s91p High-Frequency Pair Experiment

After fixing the native residue solver's empty complex-index bug, a follow-up experiment tested high-frequency complex-pair preservation on `Test16.s91p`.

Results:

- Strict expanded order 8 was not enough. Forcing the layout back to `4 real + 2 complex pairs` after relocation produced a best mean RMS around `0.0039`, worse than the unconstrained log-initialized run.
- Allowing the preserved-pair strategy to increase the expanded order reached the target:
  - high-frequency pair preservation around `1.36 GHz` and `2.0 GHz`
  - damping around `0.03`
  - 14 relocation iterations
  - mean RMS `0.0018194`
  - effective expanded order `10`
- A plain order-10 log sweep without the preservation/reinjection step did not reproduce the improvement; most tested order-10 log configurations stayed around `0.06` RMS or worse.

Interpretation:

The useful signal is not simply "add more order." The important behavior is selective pole topology control: preserve or reintroduce high-frequency complex pairs while keeping the low/mid-band real poles well placed. However, the naive exact-order truncation strategy is harmful, so this should not be made the default yet.

Next target:

- Design an order-aware pole selection step that chooses which real poles to trade for high-frequency complex pairs based on fit error contribution, not only frequency rank.
- Re-test on `Test16.s91p` first, then check that `Test13.s60p` and `Test11.s163p` do not regress.

## Passivity Ground Truth to IdEM Roadmap

This section tracks the clean-main passivity roadmap started on 2026-07-08. The first priority is truthful reporting: a model must never be reported with `max_sigma <= 1` while a sampled violation interval contains `sigma > 1`.

| Step | Case | Config | Mean RMS | Max sigma before | Max sigma after | Violation bands before | Violation bands after | Time | Peak memory | Artifact | Interpretation |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Task 1 truthful report | synthetic 1-port hidden peak | complex pole at 10 Hz, Hamiltonian crossovers mocked empty | n/a | 2.000001900 | 2.000001900 | 1 | 1 | 0.00054 s | n/a | `runs-sparam/passivity-ground-truth-to-idem/task1-synthetic-report/summary.json` | Report sampling now includes interval interior and complex-pole frequency, so the hidden violation is not misreported as passive. |
| Task 1 truthful report | `Test13.s60p` | native manual real0 complex2, hf pairs2, 256 fit points, check-only | 0.000593962 | 1.000000000 | 1.000000000 | 0 | 0 | 11.03 s | 494.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task1-test13-check-only/fit_report.json` | The corrected report does not create a false violation on the known band-limited-passive Test13 sanity case. |
| Task 2 adaptive report sampler | `Test13.s60p` | native manual real0 complex2, hf pairs2, 256 fit points, check-only | 0.000593962 | 1.000000000 | 1.000000000 | 0 | 0 | 11.11 s | 493.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task2-test13-check-only/fit_report.json` | Adaptive report sampling preserves the Test13 sanity result without material runtime or memory change. |
| Task 2 adaptive report sampler | `Test16.s91p` | native manual real4 complex2, hf pairs2, 256 fit points, check-only | 0.003211707 | 1.046066509 | 1.046066509 | 515 | 515 | 71.04 s | 966.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task2-test16-check-only/fit_report.json` | Adaptive sampling reveals a worse hidden peak at 1.386 GHz and many more sampled violation intervals; this is more honest but currently too expensive for the default enforcement loop. |
| Task 3 trust-region QP + final validation | `Test16.s91p` | native manual real4 complex2, hf pairs2, 256 fit points, 3 QP iterations, active 3072 | 0.003212706 | 1.046066509 | 1.028399114 | 515 | 515 | 147.76 s | 917.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task3-test16-order10-enforce/fit_report.json` | Trust-region/holdout diagnostics accept three tiny-to-moderate residue steps and final adaptive validation confirms the model remains non-passive; the honest peak target is harder than the old `1.0095` report implied. |
| Task 4 model-based Gramian weighting | `Test16.s91p` | native manual real4 complex2, hf pairs2, 256 fit points, 3 QP iterations, residue + Gramian candidates | 0.003214431 | 1.046066509 | 1.028284694 | 515 | 506 | 157.32 s | 918.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task4-test16-order10-gramian/fit_report.json` | Gramian-weighted candidates are selected in iterations 1 and 2 and give a small improvement over Task 3, but the model remains far from passive. |
| Task 5 pole perturbation probe | `Test16.s91p` | native manual real4 complex2, hf pairs2, 256 fit points, 3 QP iterations, pole perturbation opt-in | 0.003229029 | 1.046066509 | 1.028873977 | 515 | 514 | 159.84 s | 904.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task5-test16-order10-pole-perturb-probe/fit_report.json` | Existing opt-in pole perturbation does not improve the truthful max-sigma target and slightly worsens RMS; do not default it on. |
| Task 6 adaptive enforcement constraints + multimode | `Test16.s91p` | native manual real4 complex2, hf pairs2, 256 fit points, 3 QP iterations, active 3072, adaptive top violating points, up to 2 singular modes/frequency | 0.003220910 | 1.046066509 | 1.027136760 | 515 | 514 | 166.16 s | 911.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task6-test16-order10-adaptive-multimode/fit_report.json` | Adaptive enforcement constraints improve the first QP step beyond Task 4, but iterations 2 and 3 produce only numerical-scale improvements; final validation still sees `max_sigma=1.027136760` at 2.0 GHz and remains non-passive. |
| Task 7 minimax-slack QP candidate | `Test16.s91p` | Task 6 plus hard-bound and minimax-slack QP candidates for residue-norm and fit-weighted active sets, 3 QP iterations | 0.003223826 | 1.046066509 | 1.026666933 | 515 | 514 | 229.03 s | 921.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task7-test16-order10-minimax-slack/fit_report.json` | Minimax-slack candidates participate and one weighted minimax candidate is selected, but the main gain still comes from residue hard-bound steps; the peak improves by about `4.70e-4` beyond Task 6. |
| Task 8 minimax-slack 6-iteration probe | `Test16.s91p` | Task 7 with `passivity_max_iterations=6` | 0.003225744 | 1.046066509 | 1.026293308 | 515 | 510 | 341.33 s | 917.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task8-test16-order10-minimax-slack-iter6/fit_report.json` | More iterations continue to reduce max sigma slightly, but convergence is too slow to reach passivity; after iteration 4 the selected minimax steps improve only `~3e-8` each. |
| Task 9 minimax slack-weight ladder probe | `Test16.s91p` | Task 7 plus minimax `slack_weight` candidates `1/16/256`, 3 QP iterations | 0.003220910 | 1.046066509 | 1.027136186 | 515 | 516 | 271.41 s | 920.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task9-test16-order10-minimax-slack-ladder/fit_report.json` | Rejected as a default path: stronger slack weights are selected but only make `~3e-7` improvements and prevent the later hard-bound step that produced Task 7's better result. Default minimax remains conservative at `slack_weight=1`. |
| Task 10 D/asymptotic perturbation probe | `Test16.s91p` | Task 7 plus `passivity_perturb_constant=True`, 3 QP iterations | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 212.73 s | 920.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task10-test16-order10-d-perturb-probe/fit_report.json` | Positive signal: allowing D/asymptotic perturbation improves the 3-iteration peak beyond Task 7 and the selected steps include minimax updates at the 2.0 GHz upper-band edge. |
| Task 11 D/asymptotic 6-iteration probe | `Test16.s91p` | Task 10 with `passivity_max_iterations=6` | 0.003233354 | 1.046066509 | 1.024576922 | 515 | 507 | 308.12 s | 919.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task11-test16-order10-d-perturb-iter6/fit_report.json` | D/asymptotic freedom keeps producing meaningful reductions through six iterations, unlike residue-only minimax; still far from passive but now clearly the best native repair path in this series. |
| Task 12 D/asymptotic weight probe before weight fix | `Test16.s91p` | Task 10 plus `passivity_constant_weight=0.1`, before applying weights to default QP candidates | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 202.43 s | 908.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task12-test16-order10-d-weight0p1/fit_report.json` | This reproduced Task 10 exactly because `constant_weight` only affected fit-weighted candidates, while selected candidates were residue-norm. |
| Task 13 D/asymptotic weight probe after weight fix | `Test16.s91p` | Task 10 plus `passivity_constant_weight=0.1`, with base perturbation weights active in default QP candidates | 0.003231802 | 1.046066509 | 1.025979300 | 515 | 508 | 202.57 s | 917.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task13-test16-order10-d-weight0p1-effective/fit_report.json` | The weight now affects active selection and QP norms, but lower D penalty does not improve max sigma; keep constant weight at `1.0` for now. |
| Task 14 edge-focused candidate probe | `Test16.s91p` | Task 10 plus edge-only candidate solves near 2.0 GHz, all candidates still validated on full sampled/holdout set | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 225.83 s | 921.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task14-test16-order10-edge-focused-d/fit_report.json` | Rejected as default: edge-only candidates produced safe local improvements but never beat the all-constraint candidates, while roughly doubling diagnostic attempts and adding runtime. |
| Task 15 high-frequency complex topology probe | `Test16.s91p` | native manual real2 complex4, hf pairs4, D perturbation, 3 QP iterations | 0.010089923 | 1.260420159 | 1.260420159 | 652 | 652 | 311.63 s | 1184.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task15-test16-order10-complex4-d/fit_report.json` | Rejected: trying to force more high-frequency complex freedom caused native relocation to expand to order 26, worsened RMS and passivity, and no enforcement candidate was selected. |
| Task 16 moderate complex topology probe | `Test16.s91p` | native manual real4 complex3, hf pairs3, D perturbation, 3 QP iterations | 0.002297545 | 1.051242153 | 1.050779568 | 569 | 572 | 343.92 s | 918.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task16-test16-real4-complex3-hf3-d/fit_report.json` | More complex poles improve fitting RMS but worsen passivity and inflate effective order to 21; topology selection must balance fit and passivity, not just add high-frequency complex pairs. |
| Task 17 opt-in effective-order cap probe | `Test16.s91p` | native manual real4 complex3, hf pairs3, D perturbation, explicit effective-order cap 10 | 0.054287903 | 3.603427105 | 3.594715994 | 275 | 262 | 147.24 s | 918.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task17-test16-real4-complex3-hf3-d-capped/fit_report.json` | Rejected: naive cap keeps formal order at 10 but destroys fit and passivity. Effective-order control must be selection-aware, not a simple low-real/high-complex truncation. |
| Task 18 default path after cap opt-in | `Test16.s91p` | native manual real4 complex2, hf pairs2, D perturbation, no effective-order cap | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 177.90 s | 917.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task18-test16-real4-complex2-d-default-after-cap-optin/fit_report.json` | Sanity check: making effective-order cap opt-in preserves the best three-iteration default path exactly. |
| Task 19 topology combined-score probe | `Test16.s91p` | score fitted pole topologies by full-frequency residue refit RMS + sampled passivity excess, no enforcement | n/a | n/a | n/a | n/a | n/a | 137.8 s | n/a | `runs-sparam/passivity-ground-truth-to-idem/task19-test16-topology-scoring/summary.json` | The combined scorer ranks real4/complex2/hf2 best (`score=0.04964`), ahead of real4/complex3/hf3 (`score=0.05226`) despite its lower RMS, because the latter has worse passivity risk. |
| Task 20 opt-in topology sweep + D repair | `Test16.s91p` | native manual topology sweep over real4/complex2/hf2, real4/complex3/hf3, real2/complex4/hf4; D perturbation, 3 QP iterations | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 292.60 s | 1011.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task20-test16-topology-sweep-d/fit_report.json` | The sweep correctly selects real4/complex2/hf2 (`score=0.04887`) over the RMS-better real4/complex3/hf3 (`score=0.05356`) and reproduces Task 10/18. It validates topology scoring, but does not improve passivity. |
| Task 21 opt-in D-only candidate probe | `Test16.s91p` | native manual real4 complex2, hf pairs2, D perturbation, explicit D-only active-set candidates, 3 QP iterations | 0.003231796 | 1.046066509 | 1.025977823 | 515 | 510 | 200.36 s | 918.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task21-test16-constant-only-d/fit_report.json` | Rejected as default: D-only generated 90 candidate attempts and none were selected. The best D-only candidate only tied the selected residue-norm/minimax step, so isolated asymptotic correction is not enough. |
| Task 22 opt-in global damping fallback | `Test16.s91p` | native manual real4 complex2, hf pairs2, D perturbation, final scalar damping fallback | 0.004324019 | 1.046066509 | 0.999989000 | 515 | 0 | 162.44 s | 902.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task22-test16-global-damping-fallback/fit_report.json` | Passivity target reached, but by damping the full fitted response by `0.974669`. This is a useful guaranteed fallback/baseline, not an IdEM-equivalent repair because RMS degradation is too large. |
| Task 23 opt-in sampled spectral projection fallback | `Test16.s91p` | native manual real4 complex2, hf pairs2, D perturbation, top-16 violating samples projected to spectral norm ball | 0.004214236 | 1.046066509 | 1.018928198 | 515 | 112 | 205.97 s | 918.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task23-test16-spectral-projection-fallback/fit_report.json` | Directional but rejected as default: sampled projection lowers the post-QP peak beyond Task 10/18, but remains non-passive and increases RMS almost as much as global damping. |
| Task 24 sampled projection plus global damping | `Test16.s91p` | Task 23 followed by final scalar damping fallback | 0.005372359 | 1.046066509 | 0.999989000 | 515 | 0 | 207.20 s | 916.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task24-test16-projection-plus-damping/fit_report.json` | Rejected: projection reduces the required damping factor to `0.981413`, but total RMS is worse than pure global damping. Projection target/weighting is not yet fit-aware enough. |
| Task 25 projection delta-norm trust probe | `Test16.s91p` | Task 23 with `spectral_projection_max_delta_norm=0.02` | 0.004214236 | 1.046066509 | 1.018928198 | 515 | 112 | 205.46 s | 902.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task25-test16-projection-trust0p02/fit_report.json` | Model-parameter delta norm is not a useful fit proxy here: selected delta norm is only `5.4e-13` because large pole magnitudes dominate the normalization, so the run reproduces Task 23. |
| Task 27 response-trust projection probe | `Test16.s91p` | Task 23 with `spectral_projection_max_response_delta_rms=0.001` | 0.003362564 | 1.046066509 | 1.019544165 | 515 | 295 | 213.71 s | 913.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task27-test16-projection-response-trust0p001/fit_report.json` | Best projection tradeoff so far: response-domain trust selects `scale=0.25`, keeps RMS much closer to Task 10 while still lowering max sigma by about `0.00643`. |
| Task 28 response-trust projection tighter probe | `Test16.s91p` | Task 23 with `spectral_projection_max_response_delta_rms=0.0005` | 0.003285595 | 1.046066509 | 1.022760860 | 515 | 491 | 221.29 s | 918.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task28-test16-projection-response-trust0p0005/fit_report.json` | Tighter response trust selects `scale=0.125`; RMS is closer to the baseline, but sigma reduction is much smaller. |
| Task 29 iterative response-trust projection | `Test16.s91p` | Task 27 with `spectral_projection_iterations=3` | 0.004043940 | 1.046066509 | 1.013238092 | 515 | 179 | 253.09 s | 919.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task29-test16-iterative-projection-response-trust0p001/fit_report.json` | Iteration continues to lower sigma but accumulates fit damage; three accepted projection steps reach `1.01324`, still non-passive. |
| Task 30 iterative response-trust projection 6-step | `Test16.s91p` | Task 27 with `spectral_projection_iterations=6` | 0.004214233 | 1.046066509 | 1.005644574 | 515 | 144 | 316.93 s | 896.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task30-test16-iterative-projection-response-trust0p001-iter6/fit_report.json` | Six projection steps nearly reach passivity, but RMS climbs to the same range as full one-shot projection. |
| Task 31 iterative projection plus damping | `Test16.s91p` | Task 30 followed by final scalar damping fallback | 0.004517434 | 1.046066509 | 0.999989000 | 515 | 0 | 315.25 s | 903.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task31-test16-iterative-projection-plus-damping/fit_report.json` | Rejected as default: iterative projection reduces the required damping factor to `0.994376`, but cumulative projection plus damping RMS is worse than pure global damping. |
| Task 32 raw-data-aware projection strict gate | `Test16.s91p` | Task 30 plus raw-reference RMS gate, `max_reference_rms_increase=0` | 0.003690076 | 1.046066509 | 1.018556961 | 515 | 179 | 267.48 s | 918.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task32-test16-raw-aware-projection-ref0/fit_report.json` | Positive signal: the first two projection steps lower both sigma and raw-reference RMS on projection samples; the third step is rejected. Accuracy is much better than unconstrained six-step projection. |
| Task 33 raw-data-aware projection loose gate | `Test16.s91p` | Task 32 with `max_reference_rms_increase=0.0001` | 0.004214233 | 1.046066509 | 1.005644574 | 515 | 144 | 345.98 s | 893.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task33-test16-raw-aware-projection-ref0p0001/fit_report.json` | Too loose: allows the same six projection steps as Task 30 and reproduces its RMS/sigma tradeoff. |
| Task 34 strict raw-aware projection plus damping | `Test16.s91p` | Task 32 followed by final scalar damping fallback | 0.004692837 | 1.046066509 | 0.999989000 | 515 | 0 | 265.74 s | 902.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task34-test16-raw-aware-projection-ref0-plus-damping/fit_report.json` | Rejected: although raw-aware projection itself protects RMS, combining it with scalar damping is worse than pure damping. The remaining correction cannot be a uniform gain shrink. |
| Task 35 raw-target projection, sparse validation | `Test16.s91p` | Task 30 style six-step projection, but projection target is clipped raw Touchstone data instead of current-model spectral clip; top-16 projection samples | 0.004249501 | 1.046066509 | 1.016591263 | 515 | n/a | 304.88 s | 918.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task35-test16-raw-target-projection-iter6/fit_report.json` | Raw-target projection lowers raw-reference RMS on projection samples but still misses hidden shifted peaks; internal projection validation reported `1.00798`, while the final sampled report found `1.01659`. This exposed a candidate-validation coverage bug. |
| Task 36 raw-target projection with raw-grid validation | `Test16.s91p` | Task 35 plus candidate/baseline validation on the original raw frequency grid | 0.003825453 | 1.046066509 | 1.016895006 | 515 | 198 | 304.93 s | 917.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task36-test16-raw-target-projection-fullgrid-iter6/fit_report.json` | The report and projection final validation now agree, so peak shifting is measured honestly. The accepted steps are more conservative and preserve RMS better, but top-16 projection frequencies are too sparse to solve the remaining wide violation region. |
| Task 37 raw-target projection, raw-grid validation, 64 samples | `Test16.s91p` | Task 36 with `passivity_samples=64` so the LS projection fits more violating frequencies | 0.003924818 | 1.046066509 | 1.008187969 | 515 | 162 | 560.52 s | 918.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task37-test16-raw-target-projection-fullgrid-iter6-samples64/fit_report.json` | Increasing projection coverage gives a real improvement (`1.0169 -> 1.0082`) without the scalar damping RMS penalty, but runtime nearly doubles and the model remains non-passive. Next step should use all/segmented violation raw-grid constraints more intelligently, not just raise sample count. |
| Task 38 raw-target projection, all raw-grid violations | `Test16.s91p` | Task 36 plus `passivity_spectral_projection_include_all_reference_violations=True`; top-16 retained plus every violating raw-grid holdout point | 0.003281462 | 1.046066509 | 1.022866749 | 515 | 2994 | 485.89 s | 918.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task38-test16-raw-target-all-reference-violations/fit_report.json` | Rejected: all-violation LS preserves RMS well but dilutes the dominant peak with many small violations. It accepts only one conservative step and leaves the true peak worse than Task 36/37. |
| Task 39 raw-target projection, 128 top samples | `Test16.s91p` | Task 37 with `passivity_samples=128` | 0.003864370 | 1.046066509 | 1.007502786 | 515 | 170 | 885.40 s | 1032.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task39-test16-raw-target-projection-fullgrid-iter6-samples128/fit_report.json` | Marginal improvement over Task 37 (`1.00819 -> 1.00750`) at much higher runtime and memory. Top-N density is entering diminishing returns; the next change should weight or segment the violation band instead of increasing sample count. |
| Task 40 weighted raw-target projection, 64 top samples | `Test16.s91p` | Task 37 plus `passivity_spectral_projection_weight_mode=violation_excess` | 0.003926157 | 1.046066509 | 1.008188490 | 515 | 162 | 588.67 s | 902.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task40-test16-weighted-raw-target-projection-samples64/fit_report.json` | Rejected: top-64 violations have nearly equal excess, so weighting is effectively a uniform scale and reproduces Task 37. |
| Task 41 weighted all-raw-grid violations | `Test16.s91p` | Task 38 plus violation-excess row weights | 0.003837892 | 1.046066509 | 1.007909107 | 515 | 165 | 516.44 s | 914.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task41-test16-weighted-all-reference-violations/fit_report.json` | Positive but insufficient: weighting fixes the all-point dilution from Task 38 and beats Task 37 with lower runtime than Task 39, but still does not beat Task 39 or reach passivity. |
| Task 42 weighted all-raw-grid violations, exponent 2 | `Test16.s91p` | Task 41 with `passivity_spectral_projection_weight_exponent=2.0` | 0.003875498 | 1.046066509 | 1.008131494 | 515 | 161 | 518.27 s | 902.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task42-test16-weighted-all-reference-violations-exp2/fit_report.json` | Rejected: stronger peak weighting shifts the remaining peak to the low-frequency band and slightly worsens sigma. Simple weighted LS has reached its useful limit. |
| Task 43c active singular-mode candidate, top16 | `Test16.s91p` | Task 40 plus opt-in active singular-vector minimax candidate; top-16 projection frequencies, raw-grid validation | 0.003831855 | 1.046066509 | 1.016164361 | 515 | 197 | 789.61 s | 908.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task43c-test16-active-singular-minimax-top16/fit_report.json` | Rejected in this form: active-mode candidates are selected after two matrix-projection steps and reduce `1.016895 -> 1.016164`, but the run is slow and much worse than Task 37/39/41. The uncapped/all-reference active-mode probes timed out beyond 20 minutes. |
| Task 44 dominant-response active-mode candidate | `Test16.s91p` | Task 43c plus active-mode variables limited to top 256 `|u_i v_j|` responses | 0.003827313 | 1.046066509 | 1.016170540 | 515 | 197 | 807.38 s | 915.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task44-test16-active-mode-dominant-responses256/fit_report.json` | Rejected: dominant response selection does not improve sigma or runtime enough. The selected active-mode steps still use tiny `0.0625` scales and remain far worse than Task 39/41. |
| Task 44b restricted dominant-response active-mode | `Test16.s91p` | Task 44 plus active QP variable set restricted to selected response blocks before column selection | 0.003827313 | 1.046066509 | 1.016170540 | 515 | 197 | 803.62 s | 906.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task44b-test16-active-mode-dominant-responses256-restricted/fit_report.json` | Rejected: true variable restriction slightly lowers memory but reproduces Task 44. Runtime is dominated by repeated global candidate validation, and active-mode remains less effective than raw-target projection. |
| Task 45 candidate raw-holdout budget, top128 | `Test16.s91p` | Task 39 plus `passivity_spectral_projection_candidate_reference_max_points=128`; accepted candidates revalidated on full raw grid | 0.003839859 | 1.046066509 | 1.008365324 | 515 | 155 | 966.11 s | 1020.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task45-test16-projection-candidate-holdout128/fit_report.json` | Rejected: bounded candidate holdout changes line-search choices, adds full revalidation after each accepted step, and is slower/worse than Task 39. |
| Task 46 candidate raw-holdout budget, top64 | `Test16.s91p` | Task 37 plus `passivity_spectral_projection_candidate_reference_max_points=64`; accepted candidates revalidated on full raw grid | 0.003936622 | 1.046066509 | 1.009659858 | 515 | 205 | 532.83 s | 913.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task46-test16-projection-candidate-holdout64/fit_report.json` | Rejected as default: runtime is only slightly lower than Task 37, but sigma regresses from `1.008187969` to `1.009659858`. |
| Task 47 pre-enforcement topology revisit | `Test16.s91p` | native manual real4 complex2, hf pairs2, no enforcement, D sigma `0.005777879` | 0.003211707 | 1.046066509 | 1.046066509 | 515 | 515 | 82.89 s | 918.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task47-test16-prepassivity-topology-comparison/real4_complex2_hf2/fit_report.json` | Current topology remains the best passivity tradeoff: not lowest RMS, but lowest sampled max sigma and lowest memory/order among the viable candidates. |
| Task 47 pre-enforcement topology revisit | `Test16.s91p` | native manual real4 complex3, hf pairs3, no enforcement, D sigma `0.001803389` | 0.002296937 | 1.051242153 | 1.051242153 | 569 | 569 | 145.11 s | 1367.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task47-test16-prepassivity-topology-comparison/real4_complex3_hf3/fit_report.json` | Lower RMS does not mean easier passivity: this topology starts farther above 1, uses expanded order 21, and consumes substantially more memory. |
| Task 47 pre-enforcement topology revisit | `Test16.s91p` | native manual real2 complex4, hf pairs4, no enforcement, D sigma `0.001719994` | 0.010089923 | 1.260420159 | 1.260420159 | 652 | 652 | 192.83 s | 1663.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task47-test16-prepassivity-topology-comparison/real2_complex4_hf4/fit_report.json` | Rejected: higher complex-pole pressure explodes effective order to 26, damages fit, and starts much farther from passive. |
| Task 48 banded reference projection | `Test16.s91p` | Task 37 plus `spectral_projection_frequency_selection=reference_bands`, band sample count 8 | 0.003921933 | 1.046066509 | 1.008473262 | 515 | 180 | 549.62 s | 918.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task48-test16-banded-reference-projection-samples64/fit_report.json` | Rejected as default: banded selection is slightly faster and preserves RMS, but final max sigma is worse than Task 37 (`1.008187969`) and Task 41 (`1.007909107`). |
| Task 49 full raw-grid RMS gate | `Test16.s91p` | Task 37 plus `max_reference_rms_increase=0.0001`, `reference_rms_scope=candidate_validation`, full raw-grid candidate scope | n/a | n/a | n/a | n/a | n/a | >900 s | n/a | `runs-sparam/passivity-ground-truth-to-idem/task49-test16-fullgrid-reference-rms-bound/fit.log` | Rejected for now: evaluating reference RMS over the full raw grid inside candidate selection did not complete within 15 minutes. It is too expensive without cached/batched raw-response evaluation. |
| Task 49b holdout raw-RMS gate | `Test16.s91p` | Task 46 plus `max_reference_rms_increase=0.0001`, `reference_rms_scope=candidate_validation`, top64 candidate raw holdout | 0.003936622 | 1.046066509 | 1.009659858 | 515 | 177 | 535.01 s | 914.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task49b-test16-holdout-reference-rms-bound64/fit_report.json` | Rejected as default: bounded holdout RMS does not change candidate selection enough and reproduces Task 46's weaker result. |
| Task 50 vectorized full-grid RMS smoke | `Test16.s91p` | Task 49 full raw-grid RMS scope after batched response/reference interpolation; 1 QP iteration, 1 projection iteration | 0.003292708 | 1.046066509 | 1.023508420 | 515 | 491 | 244.09 s | 919.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task50-test16-vectorized-fullgrid-rms-smoke/fit_report.json` | Compute-path progress: full raw-grid candidate RMS over 611 points completes for one projection step. The accepted step is conservative (`scale=0.125`) and preserves RMS, but full multi-step repair still needs candidate basis caching or a cheaper global validation path. |
| Task 51 rational-basis cache smoke | `Test16.s91p` | Task 50 plus cached `1/(s-p)` basis reuse inside RMS and reference-holdout paths | 0.003292708 | 1.046066509 | 1.023508420 | 515 | 491 | 242.38 s | 902.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task51-test16-basis-cache-fullgrid-rms-smoke/fit_report.json` | Basis caching is numerically neutral and slightly lowers memory/noise, but runtime is effectively unchanged from Task 50. The dominant cost is candidate matrix assembly/SVD/validation, not scalar rational-basis construction. |
| Task 52 multi-candidate holdout batch microbench | synthetic 91-port | 5 candidates, 611 raw-grid frequencies, cached basis, full 91x91 SVD per candidate/frequency | n/a | n/a | n/a | n/a | n/a | 11.89 s | n/a | n/a | Rejected as a speed path: batching candidates together is numerically exact but does not beat individual batched SVD (`11.90 s -> 11.89 s`). The bottleneck is the number/size of SVDs, not Python candidate dispatch. |
| Task 53 fixed singular-mode screening microbench | synthetic 91-port | 5 candidates, 611 frequencies, cached basis, top-2 baseline singular modes per frequency | n/a | n/a | n/a | n/a | n/a | 0.61 s | n/a | n/a | Positive compute signal: fixed-mode response screening is `~19.7x` faster than full 91x91 SVD (`11.94 s -> 0.61 s`) on the same candidate/frequency grid, with max-sigma underestimation around `1.3e-6` for small perturbations. |
| Task 54 naive mode-screen projection smoke | `Test16.s91p` | Task 51 plus mode-screen top2 candidates, top2 modes, before cheap-gate prefilter | 0.003231446 | 1.046066509 | 1.027520130 | 515 | 512 | 204.30 s | 900.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task54-test16-mode-screen-fullgrid-rms-smoke/fit_report.json` | Rejected: runtime improves, but the two screened candidates are later rejected and no projection step is accepted. Mode-screen must run after cheap RMS/trust gates, not before. |
| Task 55 cheap-gated mode-screen projection smoke | `Test16.s91p` | Task 54 plus cheap prefilter using delta/response/reference RMS gates before mode-screen | 0.003292708 | 1.046066509 | 1.023508420 | 515 | 491 | 226.88 s | 918.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task55-test16-mode-screen-cheapgate-fullgrid-rms-smoke/fit_report.json` | Positive but modest: reproduces Task 51's accepted `scale=0.125` and final sigma while reducing one-step runtime by about `6.4%` (`242.38 s -> 226.88 s`). |
| Task 56 cheap-gated mode-screen iter3 | `Test16.s91p` | Task 55 with `spectral_projection_iterations=3` | 0.003466385 | 1.046066509 | 1.017813776 | 515 | 186 | 270.71 s | 903.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task56-test16-mode-screen-cheapgate-fullgrid-rms-iter3/fit_report.json` | Positive: all three screened projection steps are accepted at `scale=0.125`; sigma improves steadily while RMS stays much better than unconstrained projection. |
| Task 57 cheap-gated mode-screen iter6 | `Test16.s91p` | Task 55 with `spectral_projection_iterations=6` | 0.003736812 | 1.046066509 | 1.011754476 | 515 | 176 | 342.22 s | 919.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task57-test16-mode-screen-cheapgate-fullgrid-rms-iter6/fit_report.json` | Best full-grid-RMS-gated projection so far: reaches `1.01175` with lower RMS damage than Task30/33, but still does not reach passivity or Task30's sigma. |
| Task 58 mode-screen total RMS budget | `Test16.s91p` | Task 57 but replace per-step RMS gate with total raw-RMS budget `0.001`, top2 mode-screen | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 262.47 s | 919.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task58-test16-mode-screen-total-rms-budget0p001-iter6/fit_report.json` | Strong positive: total RMS budget accepts larger early steps (`0.5`, `0.25`, `0.125`) and reaches Task37/41 sigma range with much lower runtime than Task37/39. |
| Task 59 mode-screen top4 total RMS budget | `Test16.s91p` | Task 58 but validate top4 screened candidates | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 342.74 s | 908.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task59-test16-mode-screen-top4-total-rms-budget0p001-iter6/fit_report.json` | Rejected: top4 validates more candidates but selects the same steps and final model as Task58; top2 is enough for this budget. |
| Task 60 total RMS budget 0.0012 | `Test16.s91p` | Task 58 with total raw-RMS budget raised to `0.0012` | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 264.50 s | 922.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task60-test16-mode-screen-total-rms-budget0p0012-iter6/fit_report.json` | Neutral: the looser budget lets one more cheap candidate pass early screening, but final selection and the accepted steps remain identical to Task58. |
| Task 61 total RMS budget 0.0015 | `Test16.s91p` | Task 58 with total raw-RMS budget raised to `0.0015` | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 261.62 s | 918.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task61-test16-mode-screen-total-rms-budget0p0015-iter6/fit_report.json` | Neutral: even a larger total RMS budget selects the same `0.5`, `0.25`, `0.125` projection steps and stalls at the same peak. |
| Task 62 top5 screen, budget 0.0015 | `Test16.s91p` | Task 61 but fully validate top5 screened candidates, covering all cheap-gate survivors in the stalled iteration | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 371.16 s | 928.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task62-test16-mode-screen-top5-total-rms-budget0p0015-iter6/fit_report.json` | Rejected: validating all cheap-gate survivors still produces the same final model. The stall is not a mode-screen false negative; the current projection candidate family lacks a better acceptable direction. |
| Task 63 candidate rejection diagnostics | `Test16.s91p` | Task 62 with candidate-level rejection summaries, 4 projection iterations | 0.003885921 | 1.046066509 | 1.008463873 | 515 | 181 | 374.97 s | 918.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task63-test16-candidate-reject-diagnostics-iter4/fit_report.json` | Diagnostic: the stalled iteration has `candidate_reject_reasons={'passivity_not_improved': 5}` and no RMS/cheap-gate rejects. This proves the current raw-target projection direction is locally counterproductive after the third accepted step. |
| Task 64 projection plus final damping | `Test16.s91p` | Task 58 plus final global damping fallback | 0.004306008 | 1.046066509 | 0.999989000 | 515 | 0 | 260.35 s | 912.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task64-test16-total-budget-projection-plus-final-damping/fit_report.json` | Passive but rejected as an IdEM-like answer: projection reduces the required damping factor to `0.991596`, but RMS remains close to pure damping (`0.004306` vs Task22 `0.004324`). The final correction must be nonuniform/raw-target-aware. |
| Task 65 raw-budget plus current-clip candidate | `Test16.s91p` | Task 58 plus opt-in `current_spectral_clip` projection source, top5 screen, no final damping | 0.004127344 | 1.046066509 | 1.002606577 | 515 | 177 | 456.91 s | 931.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task65-test16-raw-budget-plus-current-clip-candidate/fit_report.json` | Positive but incomplete: after one raw-reference projection step, the current-clip source is selected for four more steps and lowers the peak to `1.00261`, beating Task58/64 pre-damping but still not passive. |
| Task 67 current-clip plus revalidated damping | `Test16.s91p` | Task 65 plus final global damping with post-damping Hamiltonian interval revalidation loop | 0.004259218 | 1.046066509 | 0.999814311 | 515 | 0 | 453.17 s | 935.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task67-test16-current-clip-plus-revalidated-damping/fit_report.json` | Passive and slightly better than Task64: current-clip correction reduces the final cumulative damping factor to `0.997378` and lowers passive RMS from `0.004306008` to `0.004259218`, but the gain is still modest relative to IdEM. |
| Task 68 current-clip top10 screen | `Test16.s91p` | Task 65 but validate up to top10 screened candidates, covering all cheap-gate survivors | 0.004127344 | 1.046066509 | 1.002606577 | 515 | 177 | 608.79 s | 937.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task68-test16-current-clip-top10-screen/fit_report.json` | Rejected as a speed/quality tradeoff: top10 validates all candidates but selects the exact same final model as Task65 while adding about 152 s. The stall is not caused by top5 mode-screening. |
| Task 69 tiny sigma-regression step | `Test16.s91p` | Task 68 plus opt-in `max_sigma_regression=5e-5`, allowing tiny peak increase when violation count drops | 0.004134719 | 1.046066509 | 1.002631590 | 515 | 177 | 671.49 s | 939.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task69-test16-current-clip-top10-sigma-regression/fit_report.json` | Rejected: accepting the plateau step lowers validation violation count from 135 to 134 but worsens max sigma and RMS, then stalls again. Do not use peak-regression steps as the next passivity route. |
| Task 70 current-clip samples96 | `Test16.s91p` | Task 65 but increase projection/validation samples from 64 to 96 | 0.004115319 | 1.046066509 | 1.002793530 | 515 | 177 | 577.70 s | 1030.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task70-test16-current-clip-samples96/fit_report.json` | Rejected: more projection coverage slightly lowers RMS but worsens final max sigma and pushes memory above 1 GB. The remaining wall is not solved by simply adding more sampled constraints. |
| Task 71 current-clip raw-reference regularization | `Test16.s91p` | Task 65 plus opt-in current-clip source regularized toward raw reference with weight `0.25` | 0.004219398 | 1.046066509 | 1.003667667 | 515 | 177 | 576.02 s | 944.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task71-test16-current-clip-rawreg0p25/fit_report.json` | Rejected: the regularized current-clip candidate is selected early, but both RMS and max sigma worsen. A simple raw-reference LS regularizer is not the missing IdEM-like objective. |
| Task 72 current-clip plus active-mode64 | `Test16.s91p` | Task 65 plus opt-in active-mode candidate limited to 64 dominant responses | 0.004127612 | 1.046066509 | 1.002451283 | 515 | 176 | 511.30 s | 942.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task72-test16-current-clip-active-mode64/fit_report.json` | Positive but small: active-mode is selected after current-clip stalls and lowers the peak from Task65's `1.002606577` to `1.002451283` with almost no extra RMS. |
| Task 73 current-clip plus active-mode64 iter8 | `Test16.s91p` | Task 72 with projection iterations increased from 6 to 8 | 0.004135380 | 1.046066509 | 1.002331706 | 515 | 174 | 623.75 s | 942.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task73-test16-current-clip-active-mode64-iter8/fit_report.json` | Positive but still slow: extra iterations alternate current-clip and active-mode tiny steps and reduce the peak further to `1.002331706`, but remain non-passive. |
| Task 74 active-mode64 iter8 plus damping | `Test16.s91p` | Task 73 plus revalidated final global damping | 0.004253428 | 1.046066509 | 0.999934624 | 515 | 0 | 664.58 s | 941.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task74-test16-current-clip-active-mode64-iter8-damping/fit_report.json` | Passive and slightly better than Task67: active-mode reduces the final damping factor to `0.997648` and passive RMS to `0.004253428`, but the gain over Task67 is only `~5.8e-6` RMS. |
| Task 75 active-mode64 minimax iter8 | `Test16.s91p` | Task 73 but active-mode source uses opt-in `minimax_slack` solver instead of `min_norm` | 0.004127436 | 1.046066509 | 1.002481950 | 515 | 177 | 562.53 s | 938.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task75-test16-current-clip-active-mode64-minimax-iter8/fit_report.json` | Mixed: minimax accepts larger active-mode scales (`0.25`, `0.125`, `0.0625`) and preserves RMS better, but the final true sampled peak is worse than Task73. |
| Task 76 active-mode64 minimax iter8 plus damping | `Test16.s91p` | Task 75 plus revalidated final global damping | 0.004252855 | 1.046066509 | 0.999874560 | 515 | 0 | 560.10 s | 944.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task76-test16-current-clip-active-mode64-minimax-iter8-damping/fit_report.json` | Passive and marginally best passive RMS in this branch: `0.004252855` beats Task74 by `~5.7e-7` and Task67 by `~6.4e-6`, but the improvement is still tiny versus IdEM. |
| Task 77 active-mode64 holdout64 iter8 | `Test16.s91p` | Task 73 plus peak-shift-aware active-mode solve frequencies: projection points plus top64 raw-grid holdout peaks | 0.004135311 | 1.046066509 | 1.002331285 | 515 | 173 | 849.54 s | 945.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task77-test16-current-clip-active-mode64-holdout64-iter8/fit_report.json` | Tiny undamped improvement over Task73 (`1.002331706 -> 1.002331285`), but runtime rises sharply and RMS is unchanged at practical precision. |
| Task 78 active-mode64 holdout64 iter8 plus damping | `Test16.s91p` | Task 77 plus revalidated final global damping | 0.004253334 | 1.046066509 | 0.999870945 | 515 | 0 | 716.14 s | 939.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task78-test16-current-clip-active-mode64-holdout64-iter8-damping/fit_report.json` | Passive, but does not beat Task76 RMS; holdout active-mode improves peak slightly while costing too much to be the next main route. |
| Task 79 active-mode scalar raw-reg initial bug | `Test16.s91p` | Task 77 but active-mode source uses opt-in raw-reference-regularized min-norm solver, first implementation built full response-reference matrix | 0.004127344 | 1.046066509 | 1.002606577 | 515 | 177 | 742.95 s | 22017.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task79-test16-current-clip-active-mode64-holdout64-rawreg10-iter8/fit_report.json` | Rejected implementation: result reproduces Task65 and memory explodes because `C_ref` was built over all variables before active-column selection. |
| Task 80 active-column raw-reg10 | `Test16.s91p` | Task 79 after constructing reference rows only for active columns | 0.004127344 | 1.046066509 | 1.002606577 | 515 | 177 | 682.32 s | 3258.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task80-test16-current-clip-active-mode64-holdout64-rawreg10-iter8-activecols/fit_report.json` | Memory improves but remains too high; raw-reg10 active candidate still does not beat existing matrix/current-clip candidates. |
| Task 82 scalar-mode raw-reg10 fast rows | `Test16.s91p` | Task 80 with dominant singular-scalar reference rows and O(active-vars * freqs) construction | 0.004127344 | 1.046066509 | 1.002606577 | 515 | 177 | 514.22 s | 1023.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task82-test16-current-clip-active-mode64-holdout64-scalar-rawreg10-iter8-fastrows/fit_report.json` | Compute fixed enough for experiments, but weight 10 over-regularizes; active-mode is not selected and the result still reproduces Task65. |
| Task 83 scalar-mode raw-reg0.1 | `Test16.s91p` | Task 82 with active-mode raw-reference weight reduced to `0.1` | 0.004142674 | 1.046066509 | 1.002086303 | 515 | 177 | 625.02 s | 1026.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task83-test16-current-clip-active-mode64-holdout64-scalar-rawreg0p1-iter8/fit_report.json` | Positive signal: raw-reg active-mode is selected in late iterations and lowers the undamped true peak below Task73/77, at a modest RMS cost. |
| Task 84 scalar-mode raw-reg0.1 plus damping | `Test16.s91p` | Task 83 plus revalidated final global damping | 0.004247510 | 1.046066509 | 0.999989000 | 515 | 0 | 620.82 s | 1047.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task84-test16-current-clip-active-mode64-holdout64-scalar-rawreg0p1-iter8-damping/fit_report.json` | New best passive RMS in this branch: beats Task76 (`0.004252855`) by `~5.3e-6`, proving low-dimensional scalar raw-reference active-mode is directionally useful. |
| Task 85 scalar-mode raw-reg ladder | `Test16.s91p` | Task 84 without damping, but active-mode raw-reference weight candidates `(0.03, 0.1, 0.3)` | 0.004158140 | 1.046066509 | 1.002075649 | 515 | 174 | 792.03 s | 1104.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task85-test16-current-clip-active-mode64-holdout64-scalar-rawreg-ladder-iter8/fit_report.json` | Mixed: ladder lowers undamped peak slightly beyond Task83, but RMS, runtime, and memory all regress. |
| Task 86 scalar-mode raw-reg ladder plus damping | `Test16.s91p` | Task 85 plus revalidated final global damping | 0.004263685 | 1.046066509 | 0.999744989 | 515 | 0 | 785.50 s | 1088.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task86-test16-current-clip-active-mode64-holdout64-scalar-rawreg-ladder-iter8-damping/fit_report.json` | Rejected as default: passive but worse RMS than Task84; the ladder over-optimizes passivity at the expense of raw fit. |
| Task 87 scalar-mode raw-reg ladder budget0.00092 | `Test16.s91p` | Task 85 with cumulative raw-RMS total budget tightened from `0.001` to `0.00092` and same active-mode-specific budget | 0.004143056 | 1.046066509 | 1.002128586 | 515 | 177 | 794.07 s | 1101.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task87-test16-rawreg-ladder-budget0p00092-iter8/fit_report.json` | Budget tightening pulls RMS back near Task84 but gives up some undamped passivity improvement versus Task85. |
| Task 88 scalar-mode raw-reg ladder budget0.00092 plus damping | `Test16.s91p` | Task 87 plus revalidated final global damping | 0.004250088 | 1.046066509 | 0.999989000 | 515 | 0 | 785.67 s | 1092.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task88-test16-rawreg-ladder-budget0p00092-iter8-damping/fit_report.json` | Better than Task86 but still worse than Task84; tightened budget helps but single weight `0.1` remains the best measured passive tradeoff. |
| Task 89 scalar raw-reg0.1 start5 plus damping | `Test16.s91p` | Task 84 but skip active-mode candidate generation before projection iteration 5 | 0.004247510 | 1.046066509 | 0.999989000 | 515 | 0 | 575.54 s | 1085.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task89-test16-scalar-rawreg0p1-start5-iter8-damping/fit_report.json` | Same passive RMS as Task84 with about `45 s` less runtime; memory does not improve, so this is a runtime optimization only. |
| Task 90 scalar raw-reg0.1 start5 holdout32 plus damping | `Test16.s91p` | Task 89 but active-mode holdout peaks reduced from 64 to 32 | 0.004257940 | 1.046066509 | 0.999823699 | 515 | 0 | 571.71 s | 992.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task90-test16-scalar-rawreg0p1-start5-holdout32-iter8-damping/fit_report.json` | Reject as default: memory drops below `1 GB`, but iteration 7 no longer accepts an active-mode step and passive RMS regresses. |
| Task 91 scalar raw-reg0.1 start5 holdout48 plus damping | `Test16.s91p` | Task 89 but active-mode holdout peaks reduced from 64 to 48 | 0.004257940 | 1.046066509 | 0.999823699 | 515 | 0 | 572.76 s | 992.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task91-test16-scalar-rawreg0p1-start5-holdout48-iter8-damping/fit_report.json` | Same as Task90: reducing holdout below 64 saves memory but loses the final useful active-mode step. |
| Task 92 scalar raw-reg0.1 start5 iter10 plus damping | `Test16.s91p` | Task 89 but projection iterations increased from 8 to 10 | 0.004255708 | 1.046066509 | 0.999851336 | 515 | 0 | 692.55 s | 1060.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task92-test16-scalar-rawreg0p1-start5-iter10-damping/fit_report.json` | Rejected: extra iteration 8 accepts a current-clip step that lowers peak but overspends RMS, so passive RMS worsens versus Task89. |
| Task 93 scalar raw-reg0.1 start5 stop-nonactive8 iter10 plus damping | `Test16.s91p` | Task 92 plus late-stage source filter: from iteration 8 onward keep only active-mode candidates | 0.004247510 | 1.046066509 | 0.999989000 | 515 | 0 | 626.61 s | 1022.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task93-test16-scalar-rawreg0p1-start5-stopnonactive8-iter10-damping/fit_report.json` | Guard works: it blocks Task92's damaging late current-clip step and restores Task89 RMS, but adds runtime versus simply stopping at 8 iterations. |
| Task 94 scalar raw-reg0.1 candidate-validation256 | `Test16.s91p` | Task 89 but candidate/reference RMS validation limited to top raw-grid holdout subset around 256 points | 0.004338095 | 1.046066509 | 0.999160724 | 515 | 0 | 554.46 s | 901.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task94-test16-scalar-rawreg0p1-start5-candidate256-iter8-damping/fit_report.json` | Rejected: memory drops below `1 GB`, but sparse validation changes candidate selection and worsens RMS significantly. |
| Task 95 scalar raw-reg0.1 candidate-validation384 | `Test16.s91p` | Task 89 but candidate/reference RMS validation limited to top raw-grid holdout subset around 384 points | 0.004410149 | 1.046066509 | 0.997676825 | 515 | 0 | 303.03 s | 901.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task95-test16-scalar-rawreg0p1-start5-candidate384-iter8-damping/fit_report.json` | Rejected harder: validation subset allows aggressive early steps, producing a passive but much worse fit. |
| Task 96 scalar raw-reg0.1 start5 chunked full-grid RMS | `Test16.s91p` | Task 89 but keep full raw-grid candidate/reference RMS semantics and evaluate reference RMS in chunks of 128 frequencies | 0.004247510 | 1.046066509 | 0.999989000 | 515 | 0 | 622.89 s | 994.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task96-test16-scalar-rawreg0p1-start5-chunk128-iter8-damping/fit_report.json` | Accepted as an opt-in compute building block: it preserves Task89 quality and drops peak memory below `1 GB`, but runtime regresses because each chunk recomputes rational basis/response matrices. |
| Task 97 scalar raw-reg0.1 start5 batched chunked RMS | `Test16.s91p` | Task 96 plus batch candidate RMS evaluation so each full-grid chunk reuses reference interpolation and rational basis across candidates | 0.004247510 | 1.046066509 | 0.999989000 | 515 | 0 | 580.37 s | 944.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task97-test16-scalar-rawreg0p1-start5-chunk128-batched-rms-iter8-damping/fit_report.json` | Accepted: preserves Task89/96 quality, nearly recovers Task89 runtime, and improves memory below both Task89 and Task96. This is the best measured compute-side configuration for the scalar raw-reg path so far. |
| Task 98 active-mode reference-bands | `Test16.s91p` | Task 97 but active-mode raw holdout uses `reference_bands` with `band_sample_count=8` instead of top-only reference peaks | 0.004252651 | 1.046066509 | 0.999904231 | 515 | 0 | 577.51 s | 982.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task98-test16-active-reference-bands-chunk128-iter8-damping/fit_report.json` | Rejected as default: it lowers the pre-damping peak (`1.002086 -> 1.001939`) and proves band coverage reduces peak shifting, but it spends too much raw RMS and final passive RMS is worse than Task97. |
| Task 99 active-mode reference-bands top1 | `Test16.s91p` | Task 98 but active-mode reference-bands keeps only one representative per reference violation band | 0.004250203 | 1.046066509 | 0.999989000 | 515 | 0 | 578.65 s | 924.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task99-test16-active-reference-bands1-chunk128-iter8-damping/fit_report.json` | Rejected as default: memory improves, but pre-damping peak regresses slightly versus Task97 (`1.002138` vs `1.002086`) and passive RMS still worsens. |
| Task 100 strict per-band candidate gate | `Test16.s91p` | Task 97 plus opt-in per-reference-band sigma regression gate from projection iteration 5, strict no-regression threshold `0.0` | 0.004248245 | 1.046066509 | 0.999989000 | 515 | 0 | 524.32 s | 923.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task100-test16-band-holdout-strict-start5-chunk128-iter8-damping/fit_report.json` | Mixed/opt-in: rejects late peak-shifting candidates and stops after iteration 6, giving much lower runtime/memory with only `7.4e-7` RMS loss versus Task97, but pre-damping peak is worse (`1.002402` vs `1.002086`) so final damping dependency increases. |
| Task 101 relaxed per-band candidate gate | `Test16.s91p` | Task 100 but allow per-band sigma regression up to `5e-5` | 0.004257094 | 1.046066509 | 0.999838918 | 515 | 0 | 584.19 s | 980.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task101-test16-band-holdout-5e-5-start5-chunk128-iter8-damping/fit_report.json` | Rejected: the relaxed gate accepts additional current-clip steps that lower pre-damping sigma only modestly but damage RMS significantly. |
| Task 102 reference-band equalized LS weights | `Test16.s91p` | Task 97 but projection frequencies use `reference_bands` and LS sample weights use opt-in `reference_band_equalized` so each reference violation band has roughly equal total LS weight | 0.004246580 | 1.046066509 | 0.999856967 | 515 | 0 | 586.03 s | 959.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task102-test16-reference-bands-equalized-weights-chunk128-iter8-damping/fit_report.json` | Accepted as a better algorithmic direction: active-mode takes over in iterations 5-7, pre-damping peak improves to `1.001544`, and passive RMS beats Task97 by `~9.3e-7`. |
| Task 103 reference-band equalized LS weights iter10 active-only late | `Test16.s91p` | Task 102 plus `projection_iterations=10` and late-stage non-active source filter from iteration 8 | 0.004239451 | 1.046066509 | 0.999906599 | 515 | 0 | 731.50 s | 991.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task103-test16-reference-bands-equalized-weights-stopnonactive8-iter10-damping/fit_report.json` | New best passive RMS in this branch: extra active-only iterations 8-9 lower pre-damping peak to `1.001413` and improve final RMS by `~8e-6` versus Task97. Runtime is higher, but this is the strongest evidence so far that a multi-band objective plus active-mode continuation is the right route. |
| Task 104 reference-band equalized LS weights iter12 active-only late | `Test16.s91p` | Task 103 but continue active-only to 12 projection iterations | 0.004240396 | 1.046066509 | 0.999841483 | 515 | 0 | 842.70 s | 944.1 MB | `runs-sparam/passivity-ground-truth-to-idem/task104-test16-reference-bands-equalized-weights-stopnonactive8-iter12-damping/fit_report.json` | Rejected as default: pre-damping peak keeps improving to `1.001283`, but the extra active steps and final damping slightly worsen RMS versus Task103. Iter10 is the current sweet spot. |
| Task 105b reference peak-minimax active-mode smoke | `Test13.s60p` | Native preview smoke, `reference_regularized_peak_minimax` active-mode solver, one projection iteration, no damping | 1.349992404 | 1.164019031 | 1.037329118 | 146 | 146 | 24.72 s | 204.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task105b-test13-native-peak-minimax-smoke/fit_report.json` | Smoke only, not a quality comparison: proves the new peak-minimax active-mode solver is wired through the native enforcement/report path. Hard-bound/current-clip still wins the selected candidate on this tiny one-iteration preview, so the next meaningful benchmark must be Task103-vs-peak-minimax on Test16 or a comparable large-port case. |
| Task 106 peak-minimax active-mode | `Test16.s91p` | Task103 but active-mode solver is `reference_regularized_peak_minimax` | 0.004330614 | 1.046066509 | 0.999802356 | 515 | 0 | 638.67 s | 938.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task106-test16-reference-bands-equalized-peak-minimax-stopnonactive8-iter10-damping/fit_report.json` | Rejected: peak-minimax is selected in iterations 5-6 but stalls at pre-damping peak `1.002938`, much worse than Task103's `1.001413`; final damping is stronger and RMS regresses substantially. |
| Task 107 hybrid active-mode | `Test16.s91p` | Task103 but active-mode solver is `reference_regularized_hybrid`, generating both min-norm and peak-minimax candidates | 0.004239451 | 1.046066509 | 0.999906599 | 515 | 0 | 782.24 s | 1003.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task107-test16-reference-bands-equalized-hybrid-active-stopnonactive8-iter10-damping/fit_report.json` | Mixed/diagnostic only: hybrid reproduces Task103 exactly because the selector avoids the worse peak-minimax moves, but runtime and memory increase. Keep hybrid opt-in; do not promote peak-minimax as the next default direction. |
| Task 108 active reference-band equalized rows | `Test16.s91p` | Task103 plus active-mode scalar reference rows weighted by `reference_band_equalized` | 0.004273048 | 1.046066509 | 0.999700115 | 515 | 0 | 732.82 s | 924.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task108-test16-active-reference-band-equalized-minnorm-stopnonactive8-iter10-damping/fit_report.json` | Rejected: it lowers the pre-damping peak slightly (`1.001343` vs Task103's `1.001413`) but spends much more raw RMS, mainly after a current-clip step at iteration 7. |
| Task 109 active reference-band equalized rows stop7 | `Test16.s91p` | Task108 but non-active sources stop from iteration 7 | 0.004265572 | 1.046066509 | 0.999989000 | 515 | 0 | 806.26 s | 931.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task109-test16-active-reference-band-equalized-stopnonactive7-iter10-damping/fit_report.json` | Rejected: earlier active-only avoids the damaging Task108 current-clip step and improves RMS, but pre-damping peak is worse (`1.001854`) and still cannot beat Task103. Active reference-band weighting should remain opt-in. |
| Task 110 late non-active RMS-efficiency gate | `Test16.s91p` | Task108 plus late non-active candidates rejected when reference RMS increase per sigma improvement exceeds `0.02` | 0.004265572 | 1.046066509 | 0.999989000 | 515 | 0 | 862.12 s | 991.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task110-test16-active-reference-band-equalized-effgate0p02-iter10-damping/fit_report.json` | Mixed diagnostic: the gate correctly rejects four inefficient late non-active candidates at iteration 7 and reproduces Task109 without manually stopping non-active sources early, but it still loses to Task103. Keep the gate opt-in as a safety guard. |
| Task 143 global-reference32 post-damping selector | `Test16.s91p` | Task141 plus `candidate_selection_metric="post_damping_reference_rms"` | 0.004272810 | 1.046066509 | 0.999933338 | 515 | 0 | 774.62 s | 963.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task143-test16-global-reference32-post-damping-selector/fit_report.json` | Rejected: post-damping-aware selection reproduces Task141's path exactly; the selector is not the reason global reference rows lose to Task128. |
| Task 144 final damping safety margin 1e-7 | `Test16.s91p` | Task128 with configurable final uniform damping safety margin lowered from `1e-5` to `1e-7` | 0.004228779 | 1.046066509 | 0.999998900 | 515 | 0 | 755.72 s | 980.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task144-test16-final-damping-safety-margin-1e-7/fit_report.json` | Small accepted improvement: keeps sampled passivity and slightly improves passive RMS versus Task128 (`0.004229298 -> 0.004228779`) by avoiding an unnecessarily conservative last uniform damping margin. |
| Task 145 final damping safety margin 1e-7 cross-check | `Test13.s60p` | Task127 with final uniform damping safety margin lowered from `1e-5` to `1e-7` | 0.000879426 | 1.164019031 | 0.999836668 | 146 | 0 | 123.3 s | 676.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task145-test13-final-damping-safety-margin-1e-7/fit_report.json` | Accepted cross-check: keeps sampled passivity and improves passive RMS slightly versus Task127 (`0.000879453 -> 0.000879426`). This supports using the smaller safety margin in the large-port CLI profile while leaving library defaults conservative. |
| Task 146 true post-damping selector from iteration 0 | `Test16.s91p` | Task144 plus actually-wired `post_damping_reference_rms` selection and `post_damping_max_sigma_regression=3e-4` | 0.004229702 | 1.046066509 | 0.999918789 | 515 | 0 | 747.7 s | 983.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task146-test16-post-damping-selector-regression3e-4/fit_report.json` | Rejected: using post-damping RMS from the first projection step over-protects RMS early, leaves a higher pre-damping peak (`1.003963`), and worsens final passive RMS versus Task144. |
| Task 147 delayed post-damping selector start7 | `Test16.s91p` | Task146 but keep passivity-first selection until projection iteration 7 | 0.004228779 | 1.046066509 | 0.999998900 | 515 | 0 | 732.3 s | 952.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task147-test16-post-damping-selector-start7-regression3e-4/fit_report.json` | Neutral: delayed post-damping selection reproduces Task144 exactly. Late rejected active-mode candidates have worse simulated post-damping RMS, so accepting their small peak regressions would not help final RMS. |
| Task 148 compensated active objective hybrid screen5 | `Test16.s91p` | Task144 but active-mode emits both regularized and damping-compensated reference candidates | 0.004308824 | 1.046066509 | 0.998523545 | 515 | 0 | 657.2 s | 1005.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task148-test16-reference-compensated-hybrid/fit_report.json` | Rejected: hybrid doubles active candidates and the existing top-5 mode screen drops the useful late regularized step, so final damping is stronger and RMS regresses badly. |
| Task 149 compensated active objective hybrid screen10 | `Test16.s91p` | Task148 but keep 10 mode-screened candidates so the original regularized path is not screened out | 0.004228922 | 1.046066509 | 0.999998900 | 515 | 0 | 1146.1 s | 982.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task149-test16-reference-compensated-hybrid-screen10/fit_report.json` | Rejected as default: pre-damping peak improves only microscopically (`1.002138708 -> 1.002132567`) while final RMS is slightly worse and runtime nearly doubles. Keep the compensated solver as an opt-in diagnostic only. |
| Task 150 active top-2 singular modes | `Test16.s91p` | Task144 but active-mode QP constrains the first two singular modes instead of only the dominant mode | 0.004243565 | 1.046066509 | 0.999998900 | 515 | 0 | 735.4 s | 1113.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task150-test16-active-singular-modes2/fit_report.json` | Rejected as default: top-2 constraints give a stronger iteration-6 drop (`1.006687 -> 1.002605`) but spend too much RMS and later stall at a worse pre-damping peak (`1.002344`) than Task144. |
| Task 151 active top-2 singular modes refweight0.3 | `Test16.s91p` | Task150 with active scalar reference weight increased from `0.1` to `0.3` | 0.004273177 | 1.046066509 | 0.999186984 | 515 | 0 | 648.6 s | 1067.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task151-test16-active-singular-modes2-refweight0p3/fit_report.json` | Rejected: heavier reference regularization does not recover RMS; it stops active-mode after one step and leaves a larger residual peak requiring stronger final damping. |
| Task 152 band-selective top-2 singular modes | `Test16.s91p` | Task144 but only reference holdout violation-band representative frequencies use two active singular modes | 0.004250829 | 1.046066509 | 0.999723080 | 515 | 0 | 738.3 s | 1007.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task152-test16-band-selective-singular-modes2/fit_report.json` | Mixed: band-selective top-2 lowers the pre-damping peak strongly to `1.001397`, but a late current-clip step spends too much RMS, so final fit regresses. |
| Task 153 band-selective top-2 stop non-active7 | `Test16.s91p` | Task152 plus stop non-active projection sources from iteration 7 | 0.004228100 | 1.046066509 | 0.999998900 | 515 | 0 | 734.7 s | 1013.4 MB | `runs-sparam/passivity-ground-truth-to-idem/task153-test16-band-selective-singular-modes2-stopnonactive7/fit_report.json` | New best passive Test16 result in this branch: blocks the damaging current-clip step, keeps band-selective active improvement, and improves final mean RMS versus Task144 (`0.004228779 -> 0.004228100`). |
| Task 154 band-selective top-2 Test13 cross-check | `Test13.s60p` | Task145 plus band-selective top-2 and stop non-active from iteration 7 | 0.000878927 | 1.164019031 | 0.999933416 | 146 | 0 | 98.2 s | 640.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task154-test13-band-selective-singular-modes2-stopnonactive7/fit_report.json` | Accepted cross-check: also improves Test13 passive mean RMS (`0.000879426 -> 0.000878927`) while remaining passive, so this profile is promoted into `idem-fast --enforce-passivity`. |
| Task 155 band-selective top-2 bandcount2 | `Test16.s91p` | Task153 but use two representative frequencies per reference holdout violation band for extra singular-mode rows | 0.004228072 | 1.046066509 | 0.999998900 | 515 | 0 | 729.6 s | 1011.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task155-test16-band-selective-singular-modes2-bandcount2-stopnonactive7/fit_report.json` | Tiny positive: improves Test16 passive mean RMS by another `2.8e-8` versus Task153 with similar memory/runtime. |
| Task 156 bandcount2 Test13 cross-check | `Test13.s60p` | Task154 but use two representative frequencies per holdout band | 0.000878927 | 1.164019031 | 0.999933416 | 146 | 0 | 97.0 s | 662.3 MB | `runs-sparam/passivity-ground-truth-to-idem/task156-test13-band-selective-singular-modes2-bandcount2-stopnonactive7/fit_report.json` | Neutral cross-check: exactly reproduces Task154 RMS/passivity, so the large-port CLI profile now uses band sample count 2. |
| Task 157 band-selective top-2 bandcount3 | `Test16.s91p` | Task155 but use three representative frequencies per reference holdout violation band | 0.004228038 | 1.046066509 | 0.999998900 | 515 | 0 | 734.7 s | 960.6 MB | `runs-sparam/passivity-ground-truth-to-idem/task157-test16-band-selective-singular-modes2-bandcount3-stopnonactive7/fit_report.json` | Tiny positive again: improves passive mean RMS by another `3.5e-8` versus Task155 and keeps passivity. |
| Task 158 bandcount3 Test13 cross-check | `Test13.s60p` | Task156 but use three representative frequencies per holdout band | 0.000878927 | 1.164019031 | 0.999933416 | 146 | 0 | 98.8 s | 665.7 MB | `runs-sparam/passivity-ground-truth-to-idem/task158-test13-band-selective-singular-modes2-bandcount3-stopnonactive7/fit_report.json` | Neutral cross-check: exactly reproduces Task156 RMS/passivity. The large-port CLI profile now uses band sample count 3. |
| Task 159 band-selective top-3 bandcount3 | `Test16.s91p` | Task157 but use three singular modes at holdout-band representative frequencies | 0.004229110 | 1.046066509 | 0.999998900 | 515 | 0 | 673.0 s | 1003.0 MB | `runs-sparam/passivity-ground-truth-to-idem/task159-test16-band-selective-singular-modes3-bandcount3-stopnonactive7/fit_report.json` | Rejected: top-3 does not lower the residual peak enough and worsens RMS, so top-2 is the current sweet spot. |
| Task 160 band-selective top-2 refweight0.03 | `Test16.s91p` | Task157 but lower active reference weight from `0.1` to `0.03` | 0.004232365 | 1.046066509 | 0.999998900 | 515 | 0 | 730.8 s | 1009.2 MB | `runs-sparam/passivity-ground-truth-to-idem/task160-test16-band-selective-refweight0p03/fit_report.json` | Rejected: weaker reference regularization allows larger active moves but spends too much RMS and does not materially reduce the final pre-damping peak. Keep active reference weight `0.1`. |
| Task 161 late active target margin | `Test16.s91p` | Task157 plus active target margin `5e-4` from projection iteration 8 | 0.004228188 | 1.046066509 | 0.999998900 | 515 | 0 | 729.7 s | 963.8 MB | `runs-sparam/passivity-ground-truth-to-idem/task161-test16-band-selective-late-target-margin-0p0005-start8/fit_report.json` | Rejected: late over-targeting slightly worsens both residual peak and final RMS. |
| Task 162 optimized-pole damping on current best | `Test16.s91p` | Task157 but allow optimized-pole final damping candidates | 0.004228038 | 1.046066509 | 0.999998900 | 515 | 0 | 834.5 s | 995.5 MB | `runs-sparam/passivity-ground-truth-to-idem/task162-test16-current-best-optimized-pole-damping/fit_report.json` | Neutral: optimized-pole damping reproduces uniform damping exactly on the current best pre-damping model, so it is not the missing final cleanup. |
| Task 163 mode-screen10 on current best | `Test16.s91p` | Task157 but validate the top 10 mode-screened candidates instead of top 5 | 0.004228038 | 1.046066509 | 0.999998900 | 515 | 0 | 1403.6 s | 1022.9 MB | `runs-sparam/passivity-ground-truth-to-idem/task163-test16-current-best-mode-screen10/fit_report.json` | Neutral but expensive: exactly reproduces Task157, proving the residual peak is not caused by screening out a better candidate. |

Task 1 conclusion: the checker/report path is now stricter about where `max_sigma` is measured. This does not improve enforcement yet; it removes a class of false PASS/contradictory reports before adaptive sampling and QP changes are evaluated.

Task 2 conclusion: deterministic adaptive report sampling is useful as a truth oracle, but the first implementation is too aggressive for large-port default enforcement. The next QP work should use adaptive samples selectively: top violating intervals and holdout validation, not every refined report sample.

Task 3 conclusion: the current residue QP is stable under trust-region and final validation, but it does not solve Test16 passivity. It lowers the truthful max sigma from `1.0461` to `1.0284`, while final validation still sees thousands of violating adaptive samples. The next improvement should change the objective/weights rather than only tightening acceptance logic.

Task 4 conclusion: true controllability-Gramian residue weighting has a measurable but tiny positive effect on Test16. The selected weighted steps reduce max sigma by about `1.14e-4` beyond Task 3 and reduce sampled violation bands from `515` to `506`. This is not enough to justify declaring the residue-only QP path solved; the next decision point should evaluate pole perturbation or a more SOC-like constraint formulation.

Task 5 decision: the existing pole-perturbation path is not the next default route. It does not beat the Gramian-weighted residue/D path and still fails final validation. CFH Arnoldi is also not the immediate blocker: the current bottleneck is repair quality, not only crossover search. The next algorithmic plan should target a more SOC-like multi-frequency constraint formulation or a stronger data/model weighted objective, with adaptive samples limited to the highest-risk intervals to control memory.

Task 6 conclusion: using adaptive top violating frequencies and multiple singular modes is directionally useful but not sufficient. The first selected residue-norm QP step lowers the true peak by about `0.01893`, then the next two accepted steps improve by only `1e-12` scale. The active matrices remain extremely ill-conditioned (`~6e13` to `1.6e14`) and the selected candidates are still residue-norm rather than weighted. The next step should not simply add more iterations; it should reformulate the repair objective so the second and later steps have meaningful degrees of freedom, likely by adding a slack/minimax objective or a stronger data-aware weighted QP before attempting full SOC.

Task 7/8 conclusion: minimax-slack QP is a real but small improvement. It reduces the Task 6 peak from `1.027136760` to `1.026666933` in the same three-iteration budget and to `1.026293308` with six iterations, while memory remains around `918-921 MB`. This proves the max-residual objective is aligned with the passivity target, but it is not strong enough as a drop-in candidate. The next useful change is to move from "candidate beside hard-bound" to a coupled objective that directly trades max sigma reduction against fit/RMS preservation, possibly with a per-interval slack budget and better scaling of the minimax regularization.

Task 9 decision: do not make a slack-weight ladder part of the default repair loop. Stronger minimax weights looked attractive from the dual objective but were counterproductive in the nonlinear line-search loop: they selected tiny safe moves and delayed stronger hard-bound updates. Keep `slack_weight=1` for the minimax nudge and move the next effort to a different degree of freedom, especially asymptotic/D handling near the upper band edge.

Task 20 decision: keep topology sweep opt-in and use it as a guardrail, not as the next passivity breakthrough. It prevents the optimizer from choosing a lower-RMS but less passive topology, which is useful for automated experiments, but the selected model still stalls at `max_sigma_after=1.025977823`. The next improvement should target the repair formulation itself: stronger fit-aware/D-aware perturbation or a more SOC-like local constraint model.

Task 21 decision: keep D-only candidates opt-in and do not include them in the default repair loop. Isolated D/asymptotic active-set solves are safe but not stronger than the coupled residue/D candidate already selected by the base solver. This narrows the next search: the useful degree of freedom is coupled residue-plus-D movement, not D alone.

Task 22 decision: global damping fallback proves that sampled passivity below 1 is achievable with the current model and memory envelope, but the fit penalty is the problem. Damping by `0.974669` moves Test16 to `max_sigma_after=0.999989` and `0` violation bands, while mean RMS worsens to `0.004324019`. This should remain an opt-in last resort and a quantitative target: the next coupled repair needs to recover most of this passivity improvement with much less uniform gain loss.

Task 23/24 decision: naive sampled spectral projection is not the missing IdEM step. It lowers the peak to `1.018928198`, proving that targeted matrix projection has more local passivity leverage than another D-only solve, but it still damages RMS (`0.004214236`) and does not reach passivity. Adding global damping after projection reaches passivity but worsens RMS to `0.005372359`, so the projection target must become data/fit-aware before it can replace global damping.

Task 25-28 decision: response-domain trust is the right way to make projection fit-aware; parameter delta norm is not useful for these rational models. With `max_response_delta_rms=0.001`, projection selects a quarter step and reaches `max_sigma_after=1.019544165` at `mean RMS=0.003362564`, a much better tradeoff than full projection. This still misses passivity, so the next step should not be another scalar threshold sweep; it should fold response-domain trust into the main QP candidate selection or iterate projection with fresh residual targets.

Task 29-31 decision: iterative response-trust projection is a real passivity-reduction mechanism but still not IdEM-like enough. It lowers Test16 from `1.025977823` to `1.005644574` in six steps, and makes the final damping factor very mild (`0.994376`). However, the passive result has `mean RMS=0.004517434`, worse than pure damping. The useful idea is iteration with response trust; the missing piece is a true objective that directly penalizes raw-data RMS, not just response movement from the already imperfect fitted model.

Task 32-34 decision: raw-data-aware candidate gating is the first projection variant that explicitly protects fit quality. With a strict no-regression gate on raw-reference RMS, projection stops after two useful steps and keeps mean RMS at `0.003690076`, while lowering max sigma to `1.018556961`. A loose gate reverts to the damaging six-step behavior, and strict projection plus scalar damping is worse than pure damping. The next repair should replace scalar damping with a raw-aware local correction on the remaining violating subspace.

Task 35-37 decision: raw-target projection is directionally useful only after candidate validation includes the raw frequency grid. Task 35 proved the previous sparse validation could under-report shifted peaks. Task 36 fixed the reporting/selection semantics, and Task 37 showed that increasing projection constraint coverage from 16 to 64 points lowers the true sampled peak to `1.008187969` at `mean RMS=0.003924818`. This is still not enough to beat IdEM's standalone passivity repair, but it narrows the next algorithmic target: build a segmented/all-violation raw-grid projection or SOC-like active singular-vector QP instead of falling back to uniform damping.

Task 38/39 decision: naive all-violation projection is not the right segmentation. It improves raw RMS but under-corrects the dominant peak because many small raw-grid violations dilute the LS target. Increasing top-N samples from 64 to 128 gives only a small sigma gain (`1.008187969 -> 1.007502786`) while runtime jumps to `885 s` and peak memory crosses `1 GB`. The next useful projection variant should weight by violation excess or solve per-band/top-band subproblems, then validate globally.

Task 40-42 decision: weighted LS projection helps only in the all-violation case, and even there it stalls above Task 39. Violation-excess weighting repairs Task 38's dilution (`1.022866749 -> 1.007909107`) at reasonable memory, but exponent 2 regresses by over-focusing the current peak and exposing a low-frequency peak. This suggests the missing mechanism is not another scalar row-weight sweep; the next step should formulate constraints on active singular vectors/frequencies directly, closer to a SOC or minimax QP, while retaining raw-grid global validation.

Task 43 decision: active singular-vector constraints are directionally meaningful but too expensive and too weak when applied over all responses. Full/all-reference active-mode probes timed out beyond 20 minutes even with a 3072 active-variable cap. The top-16 probe completed, selected active-mode candidates in later iterations, and lowered the local peak slightly, but final `max_sigma_after=1.016164361` is far behind Task 41 and Task 39. The next active-mode attempt must reduce the variable space before solving: select dominant port pairs/responses from the singular vectors, or operate on a low-rank/modal response basis rather than all `nports^2` responses.

Task 44 decision: restricting active-mode variables to dominant responses does not rescue this route. It gives nearly identical sigma to Task 43c (`1.01617`) and only modest memory reduction when the variable set is truly restricted. This shows the remaining bottleneck is not just variable count; the active-mode candidate needs a different formulation or should be deprioritized behind the stronger raw-target projection path. The next practical direction is to make Task 39/41 cheaper and more robust, or revisit fitting/order/pole placement before more passivity optimizer complexity.

Task 45/46 decision: limiting intermediate candidate raw-grid holdout is not a safe shortcut. It can reduce per-candidate sampling, but the accepted moves change enough that final full validation regresses, and revalidating after each accepted step erases much of the runtime benefit. Keep full raw-grid candidate validation for projection experiments until a stronger admissible bound or cached batched evaluator exists.

Task 47 decision: revisit fitting topology did not reveal a better passivity starting point. `real4_complex3_hf3` improves raw RMS to `0.002296937`, but worsens the starting max sigma to `1.051242153`, expands order to 21, and raises memory to `1367 MB`. `real2_complex4_hf4` is clearly invalid for this path. The bottleneck remains passivity repair formulation, not simply the chosen pre-enforcement topology; keep `real4_complex2_hf2` as the Test16 baseline while adding more targeted repair objectives.

Task 48 decision: simple banded frequency selection is not enough. It chooses 69-73 projection frequencies per accepted step and avoids Task 38's all-point dilution, but it still under-corrects the dominant peak compared with top-64 selection. This narrows the next useful change: keep the top-violation sample set, but change the objective itself toward a bounded raw-RMS/minimax formulation rather than adding more frequency-selection heuristics.

Task 49 decision: candidate-selection RMS gates need a cheaper raw-response evaluator before they can be useful at full-grid scope. The full raw-grid variant timed out beyond 15 minutes, while the top64 holdout variant completed but simply reproduced Task 46 (`max_sigma_after=1.009659858`). This suggests the next implementation step should be computational, not another gate: cache or vectorize fitted-response evaluation over raw frequencies/candidates, then revisit true full-grid RMS-bounded minimax selection.

Task 50 update: batched S-matrix evaluation and precomputed reference interpolation reduce repeated candidate RMS cost. A synthetic 91-port/611-point/6-candidate microbenchmark improved repeated reference RMS from `1.91 s` to `1.06 s` (`~1.8x`), and a one-step full-grid Test16 smoke completed in `244.09 s` instead of timing out immediately. This is still too slow for the full six-step repair; the next compute-side target is basis caching across candidates with shared poles/frequencies, then re-run the full Task49 configuration.

Task 51 decision: rational-basis caching alone is not the missing performance lever. The synthetic repeated-reference RMS microbenchmark shows no improvement once reference matrices are already precomputed (`0.866 s` without basis cache vs `0.873 s` with basis cache), and the Test16 smoke only changes `244.09 s -> 242.38 s`. Keep the helper because it makes future candidate batching cleaner, but the next speed work should target chunked/batched candidate matrix assembly and SVD or a lower-dimensional singular-mode validation path.

Task 52 decision: multi-candidate full-matrix batching is also not enough. A 5-candidate, 611-frequency, 91-port microbenchmark with cached basis gives `11.90 s` for individual candidate SVD and `11.89 s` for stacked candidate SVD, with identical max sigma values. This closes the "maybe just batch candidates" route. The next viable direction is algorithmic dimension reduction: validate candidate moves on dominant singular vectors/subspaces, with full SVD only as final/global holdout.

Task 53 decision: fixed singular-mode response screening is the first compute-side result with IdEM-like leverage. Evaluating `|u^H S v|` on the top two baseline modes per frequency is about `19.7x` faster than full SVD on a synthetic 91-port/611-point/5-candidate case. For small candidate perturbations, it tracks the full max sigma closely. The next implementation should use this as an opt-in candidate pre-screen: evaluate all candidate scales cheaply on modes, full-SVD only the top few screened candidates plus final/global holdout.

Task 54/55 decision: mode-screening needs cheap-gate prefiltering to be safe. Naive top2 mode-screening reduced runtime but screened in candidates that later failed the RMS gate, so no projection was accepted. Applying cheap delta/response/reference-RMS gates before mode-screening preserves the Task 51 result and gives a modest `~6.4%` one-step speedup. This is a valid opt-in building block, but not enough alone; the next improvement should screen more candidates/iterations and reduce final full-grid validation frequency, while keeping final validation honest.

Task 56/57 decision: multi-step cheap-gated mode-screening is stable and becomes the best accuracy-preserving projection branch so far. Six steps lower the full-grid checked max sigma to `1.011754476` with `mean RMS=0.003736812`, whereas unconstrained six-step projection reached `1.005644574` but damaged RMS to `0.004214233`. The tradeoff is now explicit: RMS-gated steps are safe but too conservative. The next algorithmic change should relax the per-step RMS gate adaptively or use a cumulative RMS budget, so later steps can take larger moves without scalar damping.

Task 58-64 decision: cumulative raw-RMS budget is useful, but budget tuning is not enough. With total budget `0.001`, mode-screened projection reaches `max_sigma_after=1.008463873` in `262.47 s`, close to Task37/41's sigma but roughly half the runtime and with controlled RMS (`0.003885921`). Raising the budget to `0.0012` or `0.0015` and validating up to top5 screened candidates does not change the final model. Candidate diagnostics show the stalled iteration is entirely `passivity_not_improved`, so the current raw-target projection direction is locally exhausted. Adding final global damping reaches passivity but keeps RMS near the pure damping penalty. The next algorithmic step should be a nonuniform/raw-target-aware final correction on the remaining violation subspace, not another scalar threshold or uniform gain sweep.

Task 65/67 decision: adding a second projection source aimed at the current fitted spectral excess is directionally useful. It gives the raw-reference path a nonuniform follow-up direction once raw-target projection stalls, reducing the undamped peak to `1.002606577`. With revalidated final damping it reaches sampled passivity at `mean RMS=0.004259218`, modestly better than Task64's `0.004306008`. This is not enough to call the passivity repair IdEM-like, but it identifies a productive next target: keep current-clip as an opt-in candidate and make the final correction more raw-RMS aware so it can cross below 1 without uniform damping.

Task 68/69 decision: current-clip's remaining stall is real, not a mode-screen artifact. Validating all cheap-gate survivors reproduces Task65 exactly. Allowing tiny peak regression to reduce violation count is counterproductive on Test16 (`1.002483806 -> 1.002507832` internally and final sampled `1.002631590`). The next improvement must change the correction formulation, likely by targeting the active violating singular subspace or by adding a raw-reference objective term, not by accepting local peak regressions.

Task 70/71 decision: two obvious current-clip extensions are now ruled out. Increasing sampled coverage to 96 does not reduce the true sampled peak and costs memory; adding a simple raw-reference regularization term to the current-clip LS objective worsens both passivity and RMS. The next useful formulation should not be another scalar blend of matrix targets. It should target the active singular subspace directly, or introduce a constrained/minimax objective over the residual violating modes with raw-RMS validation held outside the solve.

Task 72-74 decision: active-mode becomes useful only after the stronger current-clip path has lowered the model into the `~1.0025` region. With 64 dominant responses it contributes small accepted steps and modestly improves the passive+damping result. However, convergence remains too slow and the passive RMS gain over Task67 is tiny. This points to a refined active singular-subspace/minimax objective as the next real algorithmic step: keep the low-dimensional active subspace, but solve for a stronger residual-mode reduction instead of relying on tiny min-norm active-mode steps.

Task 75/76 decision: switching active-mode to the existing minimax-slack dual solver changes the tradeoff but does not break through the residual wall. It takes larger active-mode steps and yields the best passive RMS measured in this branch after damping, but its undamped true sampled peak is worse than min-norm active-mode. The next step should not simply reuse the old minimax slack objective; it needs a target aligned to the final sampled peak, likely by including holdout/raw-grid active modes directly in the low-dimensional solve or by adding a peak-shift-aware validation term.

Task 77/78 decision: including top raw-grid holdout peaks directly in the active-mode solve confirms the peak-shift hypothesis but only at numerical-scale benefit. The undamped peak improves by `~4.2e-7` versus Task73, and the passive+damping result does not beat Task76 RMS. Do not keep increasing holdout count or active-mode iterations; the next useful step should change the objective itself, for example a low-dimensional constrained correction that optimizes the remaining peak and raw RMS jointly instead of more min-norm projection steps.

Task 79-84 decision: a raw-reference term becomes useful only when it is low-dimensional and lightly weighted. The first full-response formulation was invalid for large-port use (`22 GB` peak memory), and even active-column full-response rows were too heavy. Dominant singular-scalar rows fix the compute enough for experimentation. Weight `10` is rejected by selection and reproduces Task65, while weight `0.1` is selected in late iterations, lowers the undamped true peak to `1.002086303`, and produces the best passive+damping RMS so far (`0.004247510`). Next work should tune/adapt this scalar raw-reference weight and reduce memory below `1 GB`, rather than returning to all-response raw regularization.

Task 85/86 decision: a naive raw-reference weight ladder is not better than the single `0.1` weight. It improves the undamped peak only marginally (`1.002086303 -> 1.002075649`) while increasing RMS and runtime; after damping, RMS regresses to `0.004263685`. Keep the ladder as an opt-in research knob, but do not make it the default. The next useful refinement is an adaptive acceptance/budget rule for raw-reg active-mode, not simply more simultaneous weights.

Task 87/88 decision: tightening the cumulative raw-RMS budget repairs much of the ladder's RMS overspend, and an active-mode-specific budget hook is now available for future experiments. However, the best passive result remains Task84 (`0.004247510`) rather than the budgeted ladder (`0.004250088`). This suggests the next improvement should reduce the need for final scalar damping or lower memory/runtime of the scalar raw-reg path, not add more ladder variants.

Task 89-91 decision: delaying active-mode candidate generation until iteration 5 is a useful runtime optimization. It preserves Task84 exactly and reduces runtime from `620.82 s` to `575.54 s`. Reducing active-mode holdout peaks from 64 to 32/48 lowers memory to about `992 MB`, but removes the final accepted active-mode step and worsens passive RMS to `0.004257940`. Keep `active_mode_start_iteration=5` as the preferred scalar raw-reg setting; keep holdout at 64 for quality.

Task 92 decision: simply increasing projection iterations is not a good replacement for final damping. Iteration 8 accepts an additional current-clip step and lowers the undamped peak to `1.001902858`, but reference RMS rises to `0.004154343` and final passive RMS regresses to `0.004255708`. The next improvement should add an efficiency/late-stage RMS gate for non-active-mode steps, not more iterations.

Task 93 decision: late-stage non-active filtering is a useful safety guard but not a quality improvement. It prevents Task92's damaging current-clip step and restores Task89/Task84 passive RMS, with lower observed memory than Task89 but higher runtime because extra active-only iterations still evaluate and reject candidates. Prefer `iterations=8, active_mode_start_iteration=5` for speed; keep `non_active_stop_iteration=8` as an opt-in guard for longer exploratory runs.

Task 94/95 decision: reducing candidate-validation raw-grid points is not a safe memory optimization. It lowers memory to about `902 MB`, but it changes the selected early projection steps and destroys the Task89 RMS tradeoff. Full raw-grid candidate/RMS validation is still needed for this path.

Task 96 decision: chunked full-grid reference-RMS evaluation is the right memory direction, but not yet the right speed direction. It preserves Task89's passive RMS exactly while reducing peak memory from about `1085 MB` to `994 MB`; runtime regresses from `575.54 s` to `622.89 s` because the first implementation recomputes basis/response chunks per candidate. The next compute step should keep full-grid semantics and add chunked basis/response reuse, not reduce validation frequencies.

Task 97 decision: batching chunked candidate RMS closes most of the Task96 speed gap while further reducing memory. The implementation keeps full-grid validation semantics, reuses each chunk's reference interpolation and rational basis across all candidates, and preserves the exact Task89/96 result (`mean RMS=0.004247510`, `max_sigma_after=0.999989000`). Runtime is `580.37 s`, within `~5 s` of Task89, while peak memory drops to `944.8 MB`. Keep this as the preferred compute-side setting before the next algorithmic passivity improvement.

Task 98/99 decision: active-mode reference-band coverage is a useful diagnostic/opt-in idea but not a new default. Task98 confirms the peak-shifting hypothesis by lowering the pre-damping peak from Task97's `1.002086` to `1.001939`, but the extra band constraints spend too much raw RMS and produce worse passive RMS. Reducing band samples to one per band lowers memory to `924.8 MB` but loses the passivity benefit. The next algorithmic step should use band coverage more selectively, likely only for late active-mode candidate validation or weighting, not as a blanket active-mode solve frequency expansion.

Task 100/101 decision: per-band candidate regression gating is useful for diagnostics and conservative acceleration, but it does not reduce final damping dependency. Strict no-regression gating rejects peak-shifting late candidates and cuts runtime/memory (`580.37 s/944.8 MB -> 524.32 s/923.7 MB`) with only a tiny RMS penalty, but it leaves a higher pre-damping peak and therefore needs stronger final damping. A relaxed `5e-5` gate is worse. Keep this as an opt-in conservative mode; the next passivity breakthrough needs a candidate objective that can reduce all active bands while preserving raw RMS, not just reject band regressions after the fact.

Task 102-104 decision: putting multi-band information into the LS objective is the strongest passivity/RMS improvement measured so far. Equalizing total LS weight by reference violation band lets active-mode continuation reduce the residual peak without the raw-RMS penalty seen in Task98/99. Task103 is the current best passive result on Test16 (`mean RMS=0.004239451`, `max_sigma_after=0.999906599`), beating Task97 by about `8e-6`. Task104 shows diminishing returns beyond 10 iterations: lower pre-damping peak does not translate to better final RMS. Next work should refine this into a default-quality profile and test on another large-port case before declaring the route stable.

Task 105b decision: `reference_regularized_peak_minimax` is now available as an opt-in active-mode solver and can run through the native fitting/enforcement/report stack. The smoke run is intentionally too small to judge quality; it mainly verifies wiring and diagnostics. The next high-signal experiment should swap only the active-mode solver in the Task103 Test16 profile, keep all other gates unchanged, and compare pre-damping peak, final RMS, runtime, and whether the selected late active-mode candidates change.

Task 106/107 decision: the first peak-minimax formulation should not be the default. Pure peak-minimax is more aggressive locally but less effective globally: it stops after iteration 7 and needs heavier final damping, producing much worse mean RMS (`0.004330614`). Hybrid confirms the existing full-grid selector can reject those moves and recover Task103 exactly, but that costs extra runtime and memory. The next useful correction is not another solver toggle; it should improve the active objective inputs, most likely by adding band-balanced/holdout active-mode rows or using the Task103 min-norm path with a targeted late-stage band residual objective.

Task 108/109 decision: naive band-equalized active reference rows are also not the missing piece. They can reduce the pre-damping peak, but they shift RMS cost into the active-mode reference term and/or invite a damaging current-clip step. Stopping non-active sources earlier partially repairs RMS but worsens the residual peak. This closes the simple "balance the active reference rows" route; the next useful attempt should change candidate acceptance/objective around late current-clip efficiency or formulate a residual-band objective that is explicitly RMS-budgeted rather than only reweighting reference rows.

Task 110 decision: the late non-active RMS-efficiency gate works as a safety mechanism, not as a breakthrough. It rejects the exact Task108 failure mode (`reference_rms_efficiency_exceeded` at iteration 7) and avoids the damaging current-clip step without hard-coding `non_active_stop_iteration=7`. However, once the bad non-active candidate is removed, the remaining active-mode path matches Task109 and still does not beat Task103. The best current default remains Task103; future attempts should preserve Task103's active sequence and focus on reducing final damping, not on rescuing the band-equalized active-reference variant.

Task 111-116 decision: local-agent-council helped close several tempting final-damping ideas. `post_damping_reference_rms` candidate selection reproduces Task103 exactly but costs runtime (`897.66 s`), so selection is not the bottleneck. Active target margins, including final-iteration-only margin, worsen RMS (`0.004252518` and `0.004245773`), confirming that scalar over-targeting is not useful. Selective high-frequency pole/D damping at 500 MHz fails validation (`max_sigma=1.002706`, 75 violations) and falls back to uniform damping. Projection LS reweighting is the only positive signal: two reweight rounds improve passive mean RMS to `0.004235167` with `max_sigma_after=0.999989000` and runtime `695.66 s`, while one round is too aggressive and regresses to `0.004276984`. Keep reweighting opt-in for now and next test whether `reweight_iterations=2` is stable on another large-port file; do not continue target-margin or simple selective-damping variants.

Task 117/118 decision: `reweight_iterations=2` is not just a Test16 accident. On `Test13.s60p`, the Task103 profile reaches passive mean RMS `0.000880427` with final max sigma `0.999619406`; adding reweight2 improves passive mean RMS to `0.000879453` while keeping passivity (`0.999831569`). The improvement is small but consistent across Test16 and Test13, so the large-port CLI profile now uses the Task115 passivity settings when the user explicitly requests `idem-fast --enforce-passivity`. The library-level `SParamFitConfig()` defaults remain conservative/opt-in.

Task 119-123 decision: low-dimensional optimized pole/D damping is useful as an opt-in diagnostic, but not ready as the default final damping replacement. On `Test13.s60p`, the first pure optimized candidate improved RMS but failed final passivity (`max_sigma=1.000001580`), exposing that internal damping validation was too close to the boundary. After adding a stricter acceptance margin and optimized/uniform blend candidates, Task122 selected `optimized_pole_blend_0.5` and improved passive mean RMS from Task118's `0.000879453` to `0.000879254`. However, on `Test16.s91p`, Task123 shows all optimized blends have worse reference RMS than uniform damping, so the selector correctly keeps uniform and reproduces Task115. Keep `global_damping_mode="optimized_pole"` opt-in; do not promote it into the large-port CLI profile until it beats uniform on Test16 or another hard case.

Task 124-126 decision: active-mode fine scale search is promising but not stable enough to become the default. Over-relaxation scales `(1.25, 1.5)` do not change Test16 because the selector still chooses the original smaller active-mode scales. Fine-grained scales `(0.375, 0.1875, 0.09375)` improve the hard Test16 case: Task125 lowers passive mean RMS from Task115's `0.004235167` to `0.004229298`, with final passivity still true. The selected active-mode sequence changes to `0.375`, `0.1875`, and `0.0625`, reducing the pre-damping peak to `1.002138708`. But the same fine scales slightly regress Test13 (`0.000879453 -> 0.000879662`), so keep `passivity_spectral_projection_active_mode_extra_scales` opt-in rather than adding it to the large-port CLI profile.

Task 127/128 decision: conditional fine scales solve the Test13 regression and preserve the Test16 gain. Enabling fine active-mode scales only while the current sampled peak is at least `1.001` makes Test13 reproduce Task118 exactly (`mean RMS=0.000879453`, passive), because its active-mode phase starts near `1.00005`; Test16 still reproduces Task125 (`mean RMS=0.004229298`, passive), because its active-mode phase starts around `1.0067`. This conditional profile is now promoted into the large-port `idem-fast --enforce-passivity` CLI path.

Task 129-131 decision: the real CLI path exposed a reporting gap. Running `idem-fast --enforce-passivity` without `--check-passivity` enforced the model but omitted `max_sigma_after`, which is not acceptable for passivity work. The CLI now treats `--enforce-passivity` as implying passivity checks unless the user explicitly passes `--skip-passivity-check`. Task131 confirms that the user-facing command writes truthful after-check fields (`max_sigma_after=1.000000000`, passive) and carries the promoted conditional fine-scale profile. This smoke used single-order `Test13.s60p` (`--auto-model-order-candidates ""`) to verify wiring, not to replace the harder Task127/128 algorithm benchmarks.

Task 132-134 decision: do not spend more time on active-mode frequency selection or finer active scales. Re-testing `active_mode_frequency_selection="reference_bands"` on top of the Task128 profile slightly worsens the final passive RMS (`0.004229654` vs `0.004229298`) and leaves the same final damping problem. Adding ultra-fine active scales `(0.03125, 0.015625)` reproduces Task128 exactly, proving that the late active-mode stall is not a line-search granularity issue.

Task 135-138 decision: global-energy weighting fixes part of the opt-in optimized-pole damping objective, but it still does not beat uniform damping on Test16. The old optimized-pole candidate was non-passive and high-RMS; with global pole-energy weights, pure optimized-pole damping becomes passive (`max_sigma=0.999979`) and improves its RMS to `0.004236564`, but uniform remains better at `0.004229298`. A line search from the pre-damping model toward the optimized-pole solution finds better-RMS but non-passive candidates (`step_0.93`: RMS `0.004228106`, `max_sigma=1.000130`), and adding a micro-uniform cleanup makes them passive but raises RMS above uniform (`step_0.25_plus_uniform`: `0.004230726`). Keep the global-energy weighting as an opt-in improvement to `optimized_pole`, but do not promote optimized damping into the CLI profile.

Task 139-141 decision: global active-mode reference scalar rows are useful diagnostics but not a default improvement. Adding 128 unnormalized global reference points overweights the reference term and regresses passive RMS to `0.004319121`. Normalizing the added rows fixes part of that over-regularization but still loses (`0.004301882`). A lighter 32-point normalized version lowers the pre-damping peak from Task128's `1.002138708` to `1.001578810`, but it lets a late current-clip step spend too much RMS; final passive RMS is `0.004272810`, still worse than Task128. Keep `passivity_spectral_projection_active_mode_global_reference_points` opt-in. The next attempt should not add global scalar rows blindly; it should either gate late current-clip by RMS efficiency when global rows are enabled, or formulate a true RMS-budgeted active objective that can reduce peak without inviting current-clip.

Task 142 decision: a simple late current-clip RMS-efficiency gate is not the missing piece. With global reference 32, setting `late_current_clip_max_reference_rms_per_sigma_improvement=0.05` from iteration 7 rejects the costly current-clip step as intended, but the remaining active-mode path leaves a higher pre-damping peak (`1.003143287`) and needs stronger uniform damping. Final passive RMS regresses to `0.004280119`, worse than Task141's `0.004272810` and Task128's `0.004229298`. Keep the gate as an opt-in diagnostic, but do not continue scalar threshold tuning; the selector must evaluate post-damping RMS or solve a truly RMS-budgeted active correction rather than rejecting current-clip solely by local RMS/sigma efficiency.

Task 143-163 decision: band-selective top-K active constraints produce the first small but consistent improvement beyond Task144, but the remaining residual peak is not solved by more scalar tuning. Task153 fixes the damaging late current-clip step by stopping non-active projection sources from iteration 7, improving Test16 passive mean RMS from Task144's `0.004228779` to `0.004228100`; Task154 cross-checks the same profile on Test13 and improves mean RMS from `0.000879426` to `0.000878927`. Task155-158 tune the band representative count; count 3 is tiny-positive on Test16 and neutral on Test13. Task159 shows that band top-3 is over-constraining; Task160 shows lower active reference weight spends too much RMS; Task161 shows late target margin is counterproductive; Task162 shows optimized-pole damping cannot beat uniform on the current best model; Task163 shows the residual peak is not a mode-screen top-5 artifact. The large-port `idem-fast --enforce-passivity` profile remains `active_mode_band_singular_modes=2`, `active_mode_band_singular_mode_sample_count=3`, `active_mode_reference_weight=0.1`, and `non_active_stop_iteration=7`; library defaults remain conservative. The next meaningful step needs a new local residual-peak correction formulation, not more threshold/selector sweeps.

Task 10/11 conclusion: D/asymptotic perturbation is the strongest passivity repair direction measured so far on Test16. It improves the three-iteration peak from Task 7's `1.026666933` to `1.025977823`, and the six-iteration probe reaches `1.024576922` with similar memory. This supports the IdEM-inspired hypothesis that asymptotic/passivity treatment matters for the high-frequency edge, but it is still nowhere near `max_sigma <= 1`.

Task 12/13 conclusion: `passivity_constant_weight` now correctly participates in default QP candidates when D perturbation is enabled. However, lowering the D penalty to `0.1` does not improve Test16; the best measured D path remains `constant_weight=1.0`. The next passivity work should focus on better D/residue coupling or explicit edge-frequency constraints, not simply making D cheaper.

Task 14 decision: do not keep edge-only QP candidates in the default path. The best edge candidates were valid and improved max sigma locally, but they were consistently worse than the all-constraint candidate selected in the same iteration. This suggests the upper-edge peak is not under-constrained; it is limited by the available model degrees of freedom and the current linearization.

Task 15 decision: do not simply increase `n_poles_cmplx` / high-frequency pair count. The native pole relocation path can inflate the effective order and produce a much worse model. Any high-frequency topology improvement needs explicit order control or a post-relocation pole selection step, not just a larger complex-pole request.

Task 16 conclusion: a moderate complex-topology increase gives the expected fitting benefit but moves passivity in the wrong direction. This separates the two objectives: the pole set that improves RMS is not automatically the pole set that is easiest to passivize. The next fitting/passivity step should evaluate topology candidates with a combined score, or add explicit effective-order control before using richer high-frequency pole sets.

Task 17/18 decision: keep effective-order cap as an opt-in research knob, not a default. The naive cap proves that order control alone is not enough: selecting high complex poles plus low real poles can break the model badly. However, the default path is now protected and remains reproducible after the opt-in change. Future pole selection must score candidates by actual fit/passivity behavior, not only by pole frequency.

Task 19 conclusion: topology selection should be driven by a combined score, not by RMS alone or pole frequency heuristics. A quick full-frequency residue-refit scorer correctly prefers the current best passivity topology (`real4_complex2_hf2`) over the RMS-better but passivity-worse `real4_complex3_hf3`. This is a useful stepping stone toward an IdEM-like auto topology chooser.

## Source Attribution Matrix Tool

Task 1 的 source-attribution 诊断工具已落到 `scripts/sparam_passivity_source_attribution.py`。它在同一个 Test16 全频参考网格上构造四个可审计对照：

- IdEM order8 poles + local fixed-pole residue LS
- native order10 poles + local fixed-pole residue LS
- native high-order poles + local fixed-pole residue LS
- native order10 poles + current residues control

输出路径固定为 `runs-sparam/passivity-direction-validation/source-attribution/summary.json`，其中每个 case 都记录 enforcement 前后的 `mean_rms`、`max_sigma`、`max_sigma_frequency_hz`、`violation_band_count`、`effective_order`，并附带当前 promoted passivity profile 与 decision-table 结论。

2026-07-10 复核后，决策分支修正为 **Task 4：Native pole placement is the main blocker**。关键证据是 IdEM order8 poles 进入我们的 fixed-pole residue LS 后，裸 RMS `0.000894440`，pre-sigma 只有 `1.002174253`，并且不需要 global damping 就能到 `0.999998394`；native order10 poles 则从 `1.046432673` 起步，需要 `0.997799114` uniform damping，final RMS 回到 `0.004223465`。因此 attribution 的主因不是 residue LS，而是 native pole relocation/placement 产不出 IdEM 质量的低公共 pole order。

| Case | Pre RMS | Pre sigma | Pre-damping sigma | Final RMS | Final sigma | Damping | Time s | Peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| idem_order8_poles_our_residue_ls | 0.000894440 | 1.002174253 | 0.999998394 | 0.000909128 | 0.999998394 | n/a | 222.05 | 359.0 |
| native_order10_poles_our_residue_ls | 0.003210012 | 1.046432673 | 1.002204638 | 0.004223465 | 0.999998900 | 0.997799114 | 621.14 | 376.7 |
| native_high_order_poles_our_residue_ls | 0.043893958 | 2.379686446 | 2.364182234 | 0.069100160 | 0.999998900 | 0.422978773 | 210.54 | 380.9 |
| native_order10_poles_current_residues_control | 0.003211707 | 1.046048725 | 1.002102862 | 0.004228038 | 0.999998900 | 0.997900453 | 647.66 | 381.8 |

Artifacts:

- `runs-sparam/passivity-direction-validation/source-attribution/summary.json`
- `runs-sparam/passivity-direction-validation/source-attribution/benchmark_note.md`

复现命令：

```powershell
python scripts\sparam_passivity_source_attribution.py `
  --touchstone <path-to-Test16.s91p> `
  --idem-order8-model runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\model.mod.h5 `
  --output-dir runs-sparam\passivity-direction-validation\source-attribution
```

说明：本轮也修正了 source-attribution 脚本的 half-complex-pair 响应口径，保证 native VF、passivity engine、final RMS/sigma measurement 使用同一套 complex-pair convention。

## Direction Validation Task 2/3

Task 2/3 现在作为反证记录保留：它们验证了“在坏 native poles 上继续修 residue”不是主路线。Task 2 fixed-pole fit/passivity alternation 已作为 probe 落到 `scripts/sparam_passivity_alternation_probe.py`。在 Test16 order10 fixed poles 上跑 `iterations=1,2` 后，第二轮完全复现第一轮，没有额外收益：

| Iterations | Best RMS | Best sigma | Score | Time s | Positive |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.003231578 | 1.026986913 | 0.005930269 | 227.35 | False |
| 2 | 0.003231578 | 1.026986913 | 0.005930269 | 454.76 | False |

结论：如果每一轮都回到同一个 fixed-pole raw LS 解，alternation 是退化的；不能继续在这个形式上调 `iterations=3/5`。

Task 3 passivity-aware residue LS 已作为 probe 落到 `scripts/sparam_passivity_aware_residue_probe.py`。第一个尝试是 DC-constrained active-frequency reweighting。强 lambda 与 adaptive active set 结果如下：

| Variant | Lambda | Active rounds | Pre RMS | Pre sigma | Final RMS | Final sigma | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| fixed active set | 10 | 1 | 0.003310256 | 1.030397523 | n/a | n/a | misses no-enforcement gate |
| fixed active set | 30 | 1 | 0.003600310 | 1.028202525 | n/a | n/a | peak shifts |
| fixed active set | 100 | 1 | 0.004658120 | 1.024731040 | n/a | n/a | RMS too high |
| adaptive active set | 10 | 3 | 0.003735068 | 1.025369907 | 0.005168670 | 0.999998900 | rejected |

Artifacts:

- `runs-sparam/passivity-direction-validation/fixed-pole-alternation/summary.json`
- `runs-sparam/passivity-direction-validation/passivity-aware-residue-ls-lambda10-dc/summary.json`
- `runs-sparam/passivity-direction-validation/passivity-aware-residue-ls-strong-lambda-dc/summary.json`
- `runs-sparam/passivity-direction-validation/passivity-aware-residue-ls-adaptive-dc/summary.json`
- `runs-sparam/passivity-direction-validation/passivity-aware-residue-ls-adaptive-lambda10-enforced/summary.json`

结论：simple active-frequency reweighting 有方向信号，但不是可推广突破。它能把起始 violation 从 `1.046` 降到 `~1.025-1.030`，但会发生 peak shifting；adaptive active set 后仍需要较重 uniform damping，最终 RMS `0.005168670`，比 Task157 baseline `0.004228038` 更差。结合 source attribution，这不是 residue optimizer 不够努力，而是在坏 poles 上做 residue 修正的上限。下一步转入方向 D：pole placement / pole relocation / pole selection。

## Direction D0 Pole Placement Diagnostics

Direction D0 已落到 `scripts/sparam_pole_placement_diagnostics.py`，输出：

- `runs-sparam/passivity-direction-validation/pole-placement-diagnostics/summary.json`
- `runs-sparam/passivity-direction-validation/pole-placement-diagnostics/benchmark_note.md`

Test16 实测极点差异：

| Source | Effective order | Real poles | Complex pairs | Complex frequencies | Mean RMS | Max sigma |
|---|---:|---:|---:|---|---:|---:|
| IdEM order8 | 8 | 4 | 2 | 1.365548 GHz, 2.000444 GHz | 0.000894440 | 1.002174253 |
| native order10 | 10 | 6 | 2 | 0.000053 GHz, 1.385964 GHz | 0.003210012 | 1.046432673 |

解释：native 的 1.38 GHz 复对其实贴近 IdEM 的 1.365 GHz 复对；真正缺失的是 IdEM 在 2.0 GHz 边缘附近的复对。当前 native relocation 后保留下来的第二个复对漂到了约 `53 kHz`，等效于把一个高频自由度丢到了近 DC。这直接支持 D1：不能在 relocation 之后才粗暴 reinject 高频复对，而要在 relocation 过程中软锚定目标高频复对。

## Direction D1 Soft Anchor Probe

D1 opt-in soft anchor 已接入 native VF/config/CLI。Test16 check-only、单阶 `real4/complex2/hf2/lin/256pts` 结果如下：

| Variant | Anchor bands | Strength | Mean RMS | Max sigma | Peak freq | Decision |
|---|---|---:|---:|---:|---:|---|
| D1 two-band | 1.3-1.45GHz, 1.8-2.0GHz | 0.01 | 0.013057463 | 1.407603502 | 2.000GHz | rejected |
| D1 two-band | 1.3-1.45GHz, 1.8-2.0GHz | 0.03 | 0.046350578 | 1.721174583 | 1.960GHz | rejected |
| D1 two-band | 1.3-1.45GHz, 1.8-2.0GHz | 0.10 | 0.059590100 | 2.872758181 | 2.000GHz | rejected |
| D1b high-only | 1.8-2.0GHz | 0.001 | 0.001332056 | 1.067001474 | 1.385GHz | rejected |
| D1b high-only | 1.8-2.0GHz | 0.003 | 0.004559336 | 1.041500808 | 1.902GHz | rejected |
| D1b high-only | 1.8-2.0GHz | 0.010 | 0.008008293 | 1.133379116 | 2.000GHz | rejected |

Artifacts live under `runs-sparam/passivity-direction-validation/direction-d/`.

Conclusion: naive per-iteration soft anchoring is too blunt. It confirms the 2GHz pole is important, but pulling relocation toward anchor bands directly either damages RMS or shifts the violation. Continue to D2 resonance-aware seeding before making anchoring more elaborate.

## Direction D2 Resonance Seeding Probe

D2 `init_pole_spacing="resonance"` 已接入 native VF/CLI。Test16 check-only、单阶 `real4/complex2/hf2/256pts` 结果如下：

| Variant | Mean RMS | Max sigma | Peak freq | Effective order | Decision |
|---|---:|---:|---:|---:|---|
| D2 resonance seed | 0.024267271 | 1.805663848 | 2.000GHz | 10 | rejected |
| D2 resonance seed + high-only anchor 0.003 | 0.022769305 | 1.750004189 | 2.000GHz | 10 | rejected |

Artifacts:

- `runs-sparam/passivity-direction-validation/direction-d/d2-resonance-seed/fit_report.json`
- `runs-sparam/passivity-direction-validation/direction-d/d2-resonance-seed-high-anchor-0p003/fit_report.json`

Conclusion: naive response-energy resonance seeding is not IdEM-like. It over-focuses large response peaks and produces a bad pole basin. Do not promote `init_pole_spacing="resonance"` in this form. Continue to D3 contribution-scored pole selection, which tests whether richer topologies can be pruned by actual fit/passivity contribution instead of frequency rank.

## Direction D3 Contribution-Scored Pole Selection Probe

D3 opt-in `native_effective_order_selection="contribution_score"` 已接入 native VF/config/CLI。Test16 check-only probe：

| Variant | Topology | Cap | Mean RMS | Max sigma | Peak freq | Effective order | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| D3 contribution score | real4/complex3/hf3 | 10 | 0.073293355 | 1.645606614 | 19.279MHz | 9 | rejected |

Artifact:

- `runs-sparam/passivity-direction-validation/direction-d/d3-contribution-score-real4-complex3-hf3-cap10/fit_report.json`

Conclusion: greedy leave-one-out contribution scoring is not enough to rescue richer topology under an effective-order cap. It prunes to a formally small model but destroys fit/passivity, similar in spirit to the earlier frequency-rank cap failure.

Direction D minimum-plan conclusion: D0 was decisive diagnostically, but D1/D2/D3 naive fixes are rejected. The actionable new fact is narrower: native already has the 1.38GHz pair, but loses the 2GHz edge pair. The next pole-placement work should not add broad anchoring/seeding knobs; it should focus specifically on preserving or relocating a 2GHz edge pair through the SAN relocation math, likely by modifying relocation basis/normalization or injecting a constrained pole after relocation followed by a contribution-aware full refit.

## Direction D4-D6 Follow-Up

D4-D6 tested the narrower hypothesis from D0: the native repair path failed because `_ensure_high_frequency_complex_pairs()` counted the 53 kHz complex pair as a valid high-frequency pair. The implementation is kept behind explicit experimental flags after code review, because the measured results do not justify changing the promoted `idem-fast` default.

Fixed-order Test16 diagnostics, full 611-point evaluation:

| Case | Experimental flags | Complex-pair frequencies | Effective order | Mean RMS | Max sigma | Verdict |
|---|---|---:|---:|---:|---:|---|
| default safety check | none | 53 kHz, 1.385964 GHz | 10 | 0.003210012 | 1.046432673 | baseline restored |
| D4 frequency-gated repair | `native_high_frequency_complex_pair_frequency_gate=True` | 1.383751 GHz | 8 | 0.004638040 | 1.039349012 | rejected: sigma improves only 0.0071, RMS exceeds gate |
| D5 residual edge injection | D4 + residual injection | 1.383751 GHz | 8 | 0.004638040 | 1.039349012 | rejected: 2 GHz candidate was rejected by score gate |
| D6 weighted relocation | D4 + high-frequency relocation weight gain 2.0 | 1.399748 GHz, 2.281023 GHz | 8 | 0.030410623 | 2.098197292 | rejected: preserves edge pair but destroys fit/passivity |

D5 diagnostic detail: the residual seed chose `2.0 GHz`, but the injected-pair candidate had `candidate_rms_error=0.003443241` and `candidate_max_sigma=1.141471626`, versus current `rms=0.004638128` and `max_sigma=1.038176148`. The combined score rejected it because passivity got much worse.

D6 trajectory detail: default relocation keeps an edge-like pair through most iterations, then collapses near the end: `2.390938 GHz -> 3.298629 GHz -> 1.396800 GHz -> 1.385964 GHz`. Weighted relocation prevents that collapse, but drifts monotonically to `2.281023 GHz` and produces `max_sigma=2.098`.

Conclusion: D4-D6 confirm that the missing 2 GHz pair is a real symptom, but post-hoc reinjection, residual insertion, and blunt high-frequency weighting are not enough. The next viable direction is to diagnose the final relocation jump and change the relocation solve itself so the edge pair remains coupled to the residue solution manifold.

## Direction D7 Collapse Root-Cause Diagnostics

D7 extends relocation trajectory diagnostics with per-iteration numerical data from the pole relocation LS solve:

- `condition_number`
- `|d_res|`
- input complex-pair frequencies before relocation
- corresponding `c_res` magnitude per input pole

Artifact:

- `runs-sparam/passivity-direction-validation/pole-placement-d6-trajectory-cres-diagnostics/summary.json`

Collapse window on the default fixed-order Test16 path:

| Iteration | Input complex frequencies | Output edge frequency | cond | `|d_res|` | input complex `c_res` magnitudes |
|---:|---:|---:|---:|---:|---:|
| 10 | 2.169332 GHz, 1.382689 GHz, 105.918 kHz | 2.390938 GHz | 10.3215 | 5452.8428 | 11593.2207, 441.9141, 2.2930 |
| 11 | 2.390938 GHz, 1.388320 GHz, 30.822 kHz | 3.298629 GHz | 18.3927 | 3057.6970 | 30875.5773, 391.7160, 10.7245 |
| 12 | 3.298629 GHz, 1.394254 GHz, 68.278 kHz | 1.396800 GHz | 54.0568 | 6919.9693 | 191481.7515, 625.0846, 10.9269 |
| 13 | 1.396800 GHz, 59.772 kHz | 1.385964 GHz | 163.5767 | 3517.1936 | 1960.1761, 7.8975 |

Interpretation:

- `d_res` is not near zero in the collapse window, so this is not a simple denominator-scaling degeneracy.
- Rank deficiency remains zero, and condition number rises but does not explode until after the edge pair has already collapsed.
- The dominant signal is `c_res` on the out-of-band edge pole: it grows from `1.16e4 -> 3.09e4 -> 1.91e5` as the pole moves from `2.39 GHz -> 3.30 GHz`, then the eigenvalue collapses back to the 1.4 GHz pair.

This supports the out-of-band extrapolation hypothesis: once the edge pole drifts beyond the `2 GHz` data boundary, its pole column is weakly constrained by data and the solve allows a large `c_res/d_res` perturbation. The following iteration's H matrix becomes sensitive enough that the edge eigenvalue jumps back into the existing 1.4 GHz basin.

Important correction: the current native/streaming pole relocation is already using the relaxed non-triviality form, not the original fixed high-frequency asymptote. It solves for `d_res` and adds a summation equation for the scaling function, matching Gustavsen's relaxed VF idea. Therefore the next experiment should not be called "add relaxed relocation"; it should be an out-of-band pole-column regularization experiment that directly limits `c_res` growth for poles that leave the data range.

### Direction D7 Out-of-Band Pole-Column Regularization Probe

D7 adds an opt-in Tikhonov-style LS row on `c_res` columns for complex input poles whose frequency is above `start_fraction * fmax`. This is lower-level than D6 data weighting: it does not pull high-frequency samples harder, it only discourages the solve from using a large `c_res` on poles outside the measured band.

Fixed-order Test16 diagnostics, full 611-point evaluation:

| Case | Weight | Complex-pair frequencies | Effective order | Mean RMS | Max sigma | Trajectory effect | Verdict |
|---|---:|---:|---:|---:|---:|---|---|
| baseline | 0 | 53 kHz, 1.385964 GHz | 10 | 0.003210012 | 1.046432673 | edge collapses after 3.298629 GHz | baseline |
| D7 regularization | 0.001 | 56 kHz, 1.394328 GHz | 10 | 0.015610117 | 1.129019309 | collapse reduced but still returns to 1.4 GHz | rejected |
| D7 regularization | 0.01 | 1.372292 GHz, 2.003325 GHz | 10 | 0.061979468 | 2.806363052 | keeps 2 GHz pair | rejected: fit/passivity destroyed |
| D7 regularization | 0.1 | 211 kHz, 1.368139 GHz, 2.510025 GHz | 9 | 0.009361646 | 1.253757118 | prevents final collapse but leaves out-of-band edge | rejected |

Conclusion: out-of-band `c_res` regularization confirms the mechanism but is not a usable fix in this direct form. The solve can be forced away from the catastrophic 3.3 GHz to 1.4 GHz jump, but the resulting pole/residue geometry is still not IdEM-like. The next solve-level experiment should be more selective: regularize only the specific edge-pair branch when it crosses the data boundary, or use a trust-region on the pole movement/eigenvalue step rather than a global static penalty on all out-of-band complex poles.

### Direction D8 Dynamic Local `c_res` Regularization Stop Rule

D8 tried a more local version of D7: apply an opt-in per-pole LS regularization only to the edge branch when its trajectory grows beyond the data boundary. This still enters the LS system and does not post-clip poles.

Fixed-order Test16 diagnostics:

| Case | Base weight | Complex-pair frequencies | Effective order | Mean RMS | Max sigma | Verdict |
|---|---:|---:|---:|---:|---:|---|
| D8 dynamic local `c_res` | 0.001 | 1.393209 GHz, 2.000000 GHz | 11 | 0.021706486 | 1.859876908 | rejected |
| D8 dynamic local `c_res` | 0.01 | 47 kHz, 1.396174 GHz, 4.317900 GHz | 10 | 0.005374798 | 1.164349707 | rejected |
| D8 dynamic local `c_res` | 0.1 | 49 kHz, 1.395981 GHz, 4.053144 GHz | 10 | 0.006217688 | 1.190185933 | rejected |

Stop rule triggered: after D4-D8, no solve-level pole-preservation experiment reached `pre-sigma < 1.01` and `RMS < 0.0035`. Continue no further with ad hoc relocation constraints.

### Direction D9 Full Pole-Set Distribution Comparison

Artifact:

- `runs-sparam/passivity-direction-validation/pole-placement-d9-pole-distribution-baseline/summary.json`

D9 confirms that the gap is not only the missing 2 GHz complex pair. The full pole-set distributions differ substantially:

| Source | Real pole frequencies | Complex-pair frequencies |
|---|---:|---:|
| IdEM order8 | 10.232 MHz, 26.640 MHz, 76.053 MHz, 274.971 MHz | 1.365548 GHz, 2.000444 GHz |
| native order10 | 0.510 MHz, 15.434 MHz, 30.675 MHz, 118.420 MHz, 590.827 MHz, 23.230956 GHz | 53 kHz, 1.385964 GHz |

Nearest-distance summaries:

- Native real poles to IdEM real poles: mean distance `3888.861 MHz`, max distance `22955.985 MHz`, dominated by the `23.23 GHz` real pole.
- IdEM real poles to native real poles: mean distance `52.039 MHz`, max distance `156.551 MHz`.

This supports the meta conclusion: forcing only the 2 GHz complex pair is insufficient because the rest of the native pole set is also not IdEM-like. The next direction should switch from "repair SK relocation" to "find an IdEM-like initial/target pole distribution from data," then run residue LS/enforcement on that complete pole set.

### D10 Full-Grid Training Fair Baseline

Command:

```powershell
python scripts\sparam_full_grid_pole_baseline.py `
  --touchstone user_input\spara\Test16.s91p `
  --idem-model runs-sparam\large-port-autofit-benchmark\Test16_s91p\idem\order8\order8_init3\model.mod.h5 `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d10-full-grid-baseline
```

All RMS and sigma values below are evaluated on the 611-point Test16 reference grid. IdEM poles were oracle-only and were not supplied to native fitting.

| Case | Training points | Actual order | Refit RMS | Refit max sigma |
|---|---:|---:|---:|---:|
| native_256 | 256 | 10 | 0.00321001231 | 1.04643267 |
| native_full_grid | 611 | 11 | 0.0604466873 | 2.66280092 |
| IdEM oracle (full-grid residue refit) | 611 | 8 | 0.000894439915 | 1.00217425 |

Decision: `stop_before_d11=false`; continue to D11. Independent code review confirmed that `fit_max_frequency_points=None` reaches the full-grid recipe, all metrics use the raw 611-point grid, the decision uses the full-grid residue refit, and IdEM pole values do not leak into native fitting.

The full-grid native run places complex pairs at approximately `1.378 GHz` and `2.000 GHz`, much closer to the IdEM complex-pair frequencies than the 256-point baseline, yet its fit and passivity become dramatically worse. This is stronger evidence that matching one or two complex frequencies is insufficient: the complete pole geometry, damping, topology preservation, and pole-residue coupling must be solved together.

### D11 Data-Only Complete Pole-Set Discovery

The first D11 run exposed a candidate-generation defect during the mandatory code-review gate: activity-centered windows clipped both complex pairs to exactly `2 GHz` in 15 of 16 activity candidates, while a shared log-stratified pool forced every real pole below `1 MHz`. That negative result was invalidated rather than used to trigger the stop rule.

The corrected generator samples real and complex pole frequencies independently from raw-frequency/activity empirical distributions, enforces complex-pair separation without clipping, and keeps the same fixed budget: 32 candidates, full-grid residue/RMS evaluation for all candidates, and full-grid sigma for the RMS-best 8.

Command:

```powershell
python scripts\sparam_pole_manifold_probe.py `
  --touchstone user_input\spara\Test16.s91p `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d11-data-only-fixed `
  --candidate-count 32 `
  --seed 20260710
```

The fixed Test16 run used all 611 points for training and evaluation. No IdEM numeric poles were used for generation, initialization, bounds, or objective.

| Candidates | Sigma candidates | Best source | Best RMS | Best max sigma | Runtime | Peak RSS |
|---:|---:|---|---:|---:|---:|---:|
| 32 | 8 | stratified | 0.0266428971 | 1.47142525 | 41.37 s | 873.4 MB |

The corrected candidate set has no double-`fmax` activity pair, 29 distinct activity complex frequencies, and 54 of 60 stratified real-pole frequencies above `10 MHz`. Independent re-review approved the fix and the resulting negative decision.

Decision: D11 does not advance to D12 because no data-only candidate reaches `RMS < 0.003` and `sigma < 1.03`. Do not spend local variable-projection iterations on these poor basins. Activate the planned randomized Loewner/common-pole discovery fallback, and only return to variable projection if a Loewner seed passes the D11 gate.

### D15 Randomized Loewner Common-Pole Probe

The initial implementation used complex tangential projection vectors and then imposed per-trace negative-frequency conjugate symmetry. Code review found this mathematically inconsistent: for complex `u` and `v`, `u^H S(-jw) v` is not generally `conj(u^H S(jw) v)`. The implementation was corrected to deterministic real tangential directions and an end-to-end synthetic two-port order-6 recovery test before running Test16.

Command:

```powershell
python scripts\sparam_loewner_pole_probe.py `
  --touchstone user_input\spara\Test16.s91p `
  --output-dir runs-sparam\passivity-direction-validation\pole-placement-d15-loewner `
  --orders 6,8,10 `
  --probe-count 4 `
  --partition-count 4 `
  --seed 20260710
```

The run used all 611 raw points and completed in `13.53 s` with peak RSS `964.2 MB`. All 12 `(partition, order)` combinations were rejected:

| Requested orders | Partitions | Accepted | Rejected | Rejection reason | Numerical rank |
|---|---:|---:|---:|---|---:|
| 6, 8, 10 | 4 | 0 | 12 | `unstable_eigenvalue` | 450-451 |

The reduced pencils contain mostly stable real eigenvalues plus one to four right-half-plane eigenvalues, but no accepted complete order-6/8/10 pole set. No poles were reflected, padded, or borrowed from IdEM.

Decision: `advance_to_variable_projection=false`. The scalar-projection stacked-Loewner branch stops here under its predefined rule. The next principled experiment is a proper tangential matrix Loewner pencil, where left/right interpolation directions are attached to individual frequency samples instead of stacking independent scalar projection pencils. Do not increase order or relax stability rejection before that experiment.

## 2026-07-10 Attribution Correction: DC Policy and Real-State Basis

The D0-D15 pole-attribution conclusion was invalidated by a solver-policy mismatch in the research scripts. IdEM full conjugate poles were fitted with independent complex residues and no hard DC constraint, while native half-pair poles were fitted in the real-state basis with an automatic exact DC constraint. This was not an apples-to-apples pole comparison.

Direct HDF5 inspection confirms that the IdEM model itself uses a real-state representation: `MOD/B` and `MOD/C` are real, and replaying its four real poles plus two complex-pair representatives reproduces the reported RMS (`0.00117471735`). The decisive difference was the hard DC constraint:

| IdEM order-8 pole geometry | Residue policy | Mean RMS | Max sigma |
|---|---|---:|---:|
| full conjugate, unconstrained complex LS | no hard DC | 0.000894440 | 1.002174 |
| half-pair real-state LS | exact DC | 0.056754803 | 2.6666 |
| half-pair real-state LS | no hard DC | 0.001173734 | approximately IdEM |

The source-attribution, pole-discovery, full-grid baseline, alternation, and passivity-aware residue probes now default to no hard DC and normalize full conjugate pole lists to positive-imaginary half-pair representatives before residue fitting. Therefore the old statement that pole placement explains 95% of the gap, and the D10 `0.000894` oracle comparison, must be treated as historical invalid evidence rather than an active decision basis.

## No-DC Full-Grid Order-8 Baseline

The production `idem-fast` path now uses all 611 frequency points, no hard DC constraint, post-relocation order trimming, and the requested `4 real + 2 complex-pair` topology. A code-review catch was required here: the first trim implementation preserved every relocated complex pair and produced `2 real + 3 complex`, giving RMS `0.007688`. The corrected trim respects the requested complex-pair count.

| Case | Fit points | Order/topology | Pre sigma | Final sigma | Final mean RMS | Time | Peak RSS |
|---|---:|---|---:|---:|---:|---:|---:|
| Test16 fit only | 611 | 8, real4/complex2 | not checked | not checked | 0.001306690 | 33.18 s | 352.9 MB |
| Test16 uniform fallback | 611 | 8, real4/complex2 | 1.036132117 | 0.999998900 | 0.003754903 | 57.59 s | 413.5 MB |
| Test16 QP1 + full-frequency line search, active3072 | 611 | 8, real4/complex2 | 1.036132117 | 0.999998900 | 0.003064602 | 169.95 s | 560.1 MB |
| Test16 QP1 + full-frequency line search, active768 | 611 | 8, real4/complex2 | 1.036132117 | 0.999998900 | 0.003058796 | 166.95 s | 533.9 MB |
| Test16 QP2 | 611 | 8, real4/complex2 | 1.036132117 | 0.999998900 | 0.003064590 | 275.23 s | 571.5 MB |
| Test13 default | 611 | 8, real4/complex2 | 0.999977674 | 0.999977674 | 0.000516018 | 17.03 s | 161.7 MB |

Artifacts are under `runs-sparam/passivity-direction-validation/no-dc-order8-*`.

The fit conclusion is now much stronger and simpler: native full-grid fitting reaches IdEM-like order and accuracy on both Test16 and Test13 without oracle poles. Test16's remaining gap is specifically passivity repair quality. IdEM reaches passive RMS `0.001174775`; our best truthful passive Test16 result in this round is `0.003058796`.

## QP Peak-Shifting Correction

The first QP1 run passed the old sampled/holdout gate (`1.0361 -> 1.0068`) but moved the true Hamiltonian peak to `1.10245`, producing RMS `0.00950` after fallback damping. Candidate acceptance now performs a real Hamiltonian/adaptive full-frequency line search before committing the update.

For Test16, the accepted QP direction has the following post-damping RMS curve:

| QP scale | Full-frequency sigma before fallback | Estimated final mean RMS |
|---:|---:|---:|
| 1.0 | 1.102381 | 0.0094957 |
| 0.5 | 1.049206 | 0.0049272 |
| 0.25 | 1.028157 | 0.0030646 |
| 0.125 | 1.032142 | 0.0034061 |
| 0.0625 | 1.034137 | 0.0035798 |

The selector now chooses by full-grid post-damping reference RMS and rejects any QP route that is worse than the pure uniform fallback. One QP step helps; a second step is numerical noise. Reducing active variables from 3072 to 768 changes final RMS by only `5.8e-6`. Optimized per-pole damping was also evaluated and correctly selected uniform damping instead.

Decision: keep the fast zero-QP uniform fallback as the production baseline for now. Do not continue iteration-count, active-budget, or scalar damping sweeps. The next enforcement experiment must change the correction direction itself, using an SOC/active-singular-subspace formulation with raw-reference weighting, while retaining the new Hamiltonian full-frequency acceptance gate.

## 2026-07-10 Target-Driven CLI Verification

The production workflow now accepts one accuracy target and one passivity policy:

```powershell
python -m agent_spice.cli fit-sparam INPUT.sNp `
  --rms-target 0.001 `
  --passivity off|check|enforce `
  --max-order 8 `
  --output model.sp `
  --report report.json
```

Every trial uses the full raw frequency grid and exact effective order `real poles + 2 * complex pairs`. The scheduler probes even orders first and backfills the untested integer orders below the first passing order. A failed search retains reports and trial artifacts but removes the requested production model. Top-level time is the sum of every attempted order, and top-level memory is the maximum trial RSS; reporting only the selected order's cost would understate autofit cost.

| Case | Policy | RMS target | Result | Selected order | Final mean RMS | Final max sigma | Total time | Peak RSS |
|---|---|---:|---|---:|---:|---:|---:|---:|
| `simple_through.s2p` | off | 0.5 | PASS | 3 | about 0.10 | not checked | 0.01 s | 39.2 MB |
| `simple_through.s2p` | check | 0.5 | PASS_WITH_PASSIVITY_WARNING | 3 | about 0.10 | about 1.73 | 0.01 s | 82.1 MB |
| `simple_through.s2p` | enforce | 0.5 | PASS | 4 | about 0.15 | about 0.89 | 0.45 s | 81.6 MB |
| `Test13.s60p` | enforce | 0.001 | PASS | 8 | 0.000516018 | 0.999977674 | 55.32 s | 226.0 MB |
| `Test16.s91p` | check | 0.001 | FAIL, no model | none through 8 | order-8 pre RMS 0.001306690 | check skipped after RMS gate | 92.18 s | 353.2 MB |
| `Test16.s91p` | enforce | 0.001 | FAIL, no model | none through 8 | order-8 pre RMS 0.001306690 | enforcement skipped after RMS gate | 92.10 s | 353.0 MB |

The RMS cost gate skips passivity work only after a trial already exceeds the final RMS target. This reduced the Test16 check run from `230.04 s` to `92.18 s`; no potentially acceptable trial was skipped.

Artifacts are under `runs-sparam/target-driven/verification-20260710/`.

The available IdEM Test16 order-8 passivity report is not a valid target-search comparison. Running `scripts/sparam_target_parity.py` against it correctly produces `valid_cell_count=0`: the IdEM artifact lacks the Touchstone identity, RMS target, passivity policy, full-grid point count, RMS/order formula identifiers, `sparam_target_v1` contract, and a successful target-search marker. Therefore this verification establishes truthful native behavior, but it does not yet claim IdEM parity. A new IdEM autofit run must emit the same target contract before order/time/memory ratios can be accepted.
