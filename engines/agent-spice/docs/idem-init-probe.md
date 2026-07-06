# IdEM Initial Iteration Probe

This note records the black-box probe path for understanding why IdEM places low-order common poles well. The probe uses documented `idemmp_fitting.exe` XML options and generated `.mod.h5` outputs. It does not disassemble or inspect proprietary binaries.

## Tooling

The CLI entry point is:

```powershell
python -m agent_spice.cli probe-idem-init `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --output-root runs-sparam\idem-init-probe-30p-order32-noasym `
  --report runs-sparam\idem-init-probe-30p-order32-noasym\report.jsonl `
  --csv runs-sparam\idem-init-probe-30p-order32-noasym\report.csv `
  --order 32 `
  --initial-iters 0,1,2,3 `
  --n-threads 8 `
  --target 1e-12 `
  --no-asymptotic-passivity `
  --timeout-seconds 300
```

The command writes one XML file and one `.mod.h5` model per trial. The HDF5 summary extracts:

- `MOD/Splits[*].p`: pole locations in rad/s
- `MOD/Splits[*].nr` and `MOD/Splits[*].nc`: real-pole count and complex-pair count
- `MOD/errorHistory`: IdEM fitting RMS history
- `MOD/ordersHistory`: model order history
- `MOD/fittingOptions`: the normalized XML options saved by IdEM

Important: `MOD/Splits[*].p` is a real state-space encoding, not a flat list of complex poles. The first `nr` entries are real poles. The remaining entries are `(sigma, omega)` pairs for complex conjugates `sigma +/- j*omega`.

## 30-Port Order-32 Result

Target case:

`user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p`

Fixed settings:

- order: 32
- threads: 8
- target RMS: `1e-12`, to avoid stopping early where possible
- asymptotic passivity: disabled for the pole-placement trajectory run

| Initial iterations | Elapsed s | Peak MB | IdEM RMS |
| ---: | ---: | ---: | ---: |
| 0 | 0.843 | 63.1 | n/a |
| 1 | 2.273 | 63.1 | 0.020399 |
| 2 | 3.800 | 78.7 | 0.010971 |
| 3 | 5.133 | 68.6 | 0.008879 |

The same run with asymptotic passivity enabled gives essentially the same RMS:

| Initial iterations | Elapsed s | Peak MB | IdEM RMS |
| ---: | ---: | ---: | ---: |
| 1 | 2.339 | 74.6 | 0.020402 |
| 2 | 3.739 | 68.6 | 0.010996 |
| 3 | 5.000 | 68.8 | 0.008894 |

## First Read

The improvement is mainly in the three initialization iterations, not in a memory-heavy passivity step. With fixed order 32, IdEM moves the initial spread of poles into low-frequency resonance clusters after the first iteration, then refines both low and high bands over iterations 2 and 3.

For the no-asymptotic run, sorted pole-frequency samples show the movement:

| Initial iterations | Lowest four pole frequencies Hz | Highest four pole frequencies Hz |
| ---: | --- | --- |
| 0 | `1.24e6, 2.48e6, 3.71e6, 4.95e6` | `1.61e9, 1.73e9, 1.86e9, 1.98e9` |
| 1 | `4.16e7, 4.31e7, 4.68e7, 4.93e7` | `1.62e9, 1.74e9, 1.74e9, 1.91e9` |
| 2 | `1.99e7, 3.86e7, 4.70e7, 4.78e7` | `1.68e9, 1.72e9, 1.89e9, 2.08e9` |
| 3 | `1.63e7, 3.64e7, 3.71e7, 4.74e7` | `1.62e9, 1.73e9, 1.83e9, 1.89e9` |

Next useful split: feed each IdEM pole set into our own fixed-pole residue solve, then compare `IdEM poles + our residues` against `our poles + our residues`. That isolates pole relocation from residue conditioning.

## Fixed-Pole Residue Probe

The follow-up CLI is:

```powershell
python -m agent_spice.cli probe-idem-residue `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --model runs-sparam\idem-init-probe-30p-order32-noasym\order32_init3\model.mod.h5 `
  --report runs-sparam\idem-residue-30p-order32-noasym\init3.json `
  --parameter-type s
```

It decodes the IdEM poles, freezes them, and solves only the residues plus constant term using our column-scaled least-squares solver. This deliberately avoids IdEM's proprietary residue solver so we can isolate how much the poles alone buy us.

30-port, order-32, S-domain absolute LS:

| Initial iterations | Rank | Cond. | S relative RMS | Z log RMS | Diag Z log RMS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 29 | `1.42e16` | 0.07514 | 1.888 | 2.000 |
| 1 | 28 | `9.89e15` | 0.02254 | 1.209 | 1.395 |
| 2 | 29 | `8.19e15` | 0.02030 | 1.311 | 1.472 |
| 3 | 29 | `9.54e15` | 0.02233 | 1.394 | 1.544 |

This confirms the first initialization iteration is the big pole-placement win for S-domain residue LS. More IdEM iterations improve IdEM's own RMS, but our plain residue LS does not keep improving, which points at a residue/conditioning difference.

For the init3 poles, alternate residue solves:

| Basis | Solve target | Relative weight power | Rank | Cond. | S relative RMS | Z log RMS | Diag Z log RMS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Complex-pole LS | S | 0.0 | 29 | `9.54e15` | 0.02233 | 1.394 | 1.544 |
| Complex-pole LS | S | 0.5 | 28 | `2.25e16` | 0.02316 | 1.779 | 1.785 |
| Complex-pole LS | S | 1.0 | 27 | `2.58e16` | 0.02630 | 1.890 | 1.814 |
| Complex-pole LS | Z | 0.0 | 29 | `9.54e15` | 1.226 | 4.771 | 4.262 |
| Complex-pole LS | Z | 0.5 | 29 | `2.00e16` | 1.401 | 1.617 | 1.461 |
| Complex-pole LS | Z | 1.0 | 28 | `1.74e16` | 1.198 | 2.110 | 1.840 |
| IdEM real-state LS | S | 0.0 | 33 | `1.51e2` | 0.05095 | 1.847 | 1.865 |
| IdEM real-state LS | S | 0.5 | 33 | `2.36e3` | 0.05311 | 1.621 | 1.602 |
| IdEM real-state LS | Z | 0.5 | 33 | `4.92e2` | 0.55692 | 2.126 | 2.117 |

The Z-domain relative weighting helps, but not enough. The working conclusion is now sharper:

- IdEM poles alone recover much of the S-domain behavior.
- Plain fixed-pole residue LS remains rank-deficient/ill-conditioned at order 32.
- Rewriting the residue solve in IdEM's real-state basis fixes the numerical conditioning problem: for init3, the S-domain solve condition number drops from `9.54e15` to `1.51e2` and rank becomes full.
- Direct Z-domain residue LS needs better scaling or structure; simple relative weighting is insufficient.
- Z-log quality is not monotonic with IdEM's own S-domain RMS. With the real-state S solve, init2 gives `Z log RMS = 1.361`, while init3 gives `1.847` despite the lower IdEM RMS.
- The next algorithm target is not just better pole placement, but PDN-aware pole/residue selection: choose the iteration/pole set by Z metrics, then solve residues in a real-state basis with response weighting/splitting.

## Z-Aware Sweep

The sweep command ranks combinations by `z_log_magnitude_rms_error`:

```powershell
python -m agent_spice.cli probe-idem-residue-sweep `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --model-glob "runs-sparam/idem-init-probe-30p-order32-noasym/order32_init*/model.mod.h5" `
  --report runs-sparam\idem-residue-sweep-30p-order32\sweep.jsonl `
  --csv runs-sparam\idem-residue-sweep-30p-order32\sweep.csv `
  --parameter-types s,z `
  --bases complex,idem-real `
  --relative-weight-powers 0,0.25,0.5,1,1.5,2
```

Top results:

| Rank | Init | Basis | Target | Weight | Rank | Cond. | S relative RMS | Z log RMS | Diag Z log RMS |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | init1 | complex | S | 0.0 | 28 | `9.89e15` | 0.02254 | 1.209 | 1.395 |
| 2 | init2 | complex | S | 0.0 | 29 | `8.19e15` | 0.02030 | 1.311 | 1.472 |
| 3 | init2 | complex | S | 0.25 | 28 | `2.46e16` | 0.02059 | 1.323 | 1.453 |
| 4 | init2 | idem-real | S | 0.0 | 33 | `1.99e2` | 0.06296 | 1.361 | 1.530 |
| 5 | init3 | complex | S | 0.0 | 29 | `9.54e15` | 0.02233 | 1.394 | 1.544 |

The best Z-aware selection is not the final IdEM initialization iteration. For our current residue solvers, init1 complex/S absolute gives the best full-matrix Z log RMS. A quick `rcond` sweep on this case did not beat the default: `rcond=1e-12` reproduces the best `1.209`, while stronger or weaker truncation lands between `1.38` and `1.51`.

This gives the next concrete implementation target: keep a Z-aware pole-selection loop, then improve the chosen residue solve with structured real-state conditioning rather than relying on IdEM's S-domain RMS as the selector.

## Local Common-Pole Relocation Prototype

The next probe moves from pure black-box observation to a local reproduction attempt. It implements a relaxed vector-fitting/SK-style common-pole relocation loop:

1. seed stable common poles with linear or logarithmic spacing,
2. solve a shared denominator update across selected high-energy S or Z responses,
3. relocate poles from the zeros of the fitted denominator,
4. freeze the relocated poles and run the existing fixed-pole residue solve,
5. report the same S/Z metrics used for IdEM pole sets.

CLI:

```powershell
python -m agent_spice.cli probe-idem-relocate `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\local-relocate-30p-order32\report.jsonl `
  --csv runs-sparam\local-relocate-30p-order32\report.csv `
  --order 32 `
  --iterations 3 `
  --parameter-type s `
  --pole-f-min 1e6 `
  --fit-max-frequency-points 256 `
  --max-pole-responses 64
```

`--pole-f-min` is important for DC-fitted files: IdEM's order-32 init0 poles started around `1.24 MHz` on the 30-port case, while the raw Touchstone includes near-DC frequency points. The local prototype can now skip those near-DC points when seeding poles.

This is intentionally not an IdEM clone yet. It is the first controllable baseline for testing whether our own common-pole relocation can reproduce the large init0 -> init1 jump observed in IdEM. The important comparison is per iteration:

- pole-frequency clusters versus IdEM init0/1/2/3,
- relocation LS rank and condition number,
- frozen-pole residue condition number,
- `s_relative_rms_error`,
- `z_log_magnitude_rms_error`.

If this prototype fails to move poles into IdEM-like low-frequency clusters, the missing piece is still pole relocation/weighting. If it does move the poles but Z metrics remain worse, the gap shifts back to IdEM's residue solve and conditioning.

## Local Relocation Response Selection

The prototype now exposes a `p4poles`-like response selection knob:

```powershell
python -m agent_spice.cli probe-idem-relocate-sweep `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\local-relocate-sweep-30p-order32-p4poles-v1\report.jsonl `
  --csv runs-sparam\local-relocate-sweep-30p-order32-p4poles-v1\report.csv `
  --order 32 `
  --iterations 2 `
  --parameter-type s `
  --response-selections energy,diagonal,mixed `
  --max-pole-responses-list 32,64 `
  --relative-weight-powers 0 `
  --fit-max-frequency-points 256
```

30-port order-32, local relocation, no near-DC lower bound:

| Rank | Selection | Responses | Relocation weight | Iteration | S relative RMS | Z log RMS | Residue cond. |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | energy | 64 | 0.0 | 2 | 0.011886 | 1.251 | 223.5 |
| 2 | mixed | 64 | 0.0 | 2 | 0.011886 | 1.251 | 223.5 |
| 3 | diagonal | 30 | 0.0 | 2 | n/a | 1.322 | n/a |
| 4 | energy | 32 | 0.0 | 2 | n/a | 1.335 | n/a |

Then a focused weight sweep on `energy/mixed`, 64 responses:

| Rank | Selection | Responses | Relocation weight | Iteration | Z log RMS |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | energy | 64 | 0.0 | 2 | 1.251 |
| 2 | mixed | 64 | 0.0 | 2 | 1.251 |
| 3 | energy | 64 | 0.25 | 2 | 1.332 |
| 4 | mixed | 64 | 0.25 | 2 | 1.332 |
| 5 | energy | 64 | 0.5 | 2 | 1.420 |

Readout:

- The local pole relocation already reproduces most of the IdEM init benefit.
- Diagonal-only p4poles is not enough on this 30-port case.
- 64 high-energy responses beat 32, so the relocation solve wants enough cross-coupled responses.
- Relative weighting inside the relocation solve hurts this case; keep relocation absolute for now.
- The remaining gap to IdEM is now concentrated in two places: response selection beyond simple energy ranking, and residue solve/conditioning after relocation.

## Adaptive Z-Worst p4poles Trial

The next hypothesis was that IdEM's `p4poles` selection may be driven by responses that dominate the final Z-domain error, not just by raw S/Z response energy. The local prototype now has:

```powershell
python -m agent_spice.cli probe-idem-relocate-sweep `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\local-relocate-sweep-30p-order32-adaptive-z-v1\report.jsonl `
  --csv runs-sparam\local-relocate-sweep-30p-order32-adaptive-z-v1\report.csv `
  --order 32 `
  --iterations 3 `
  --parameter-type s `
  --response-selections energy,adaptive-z `
  --max-pole-responses-list 64 `
  --relative-weight-powers 0 `
  --adaptive-worst-pair-count 16 `
  --fit-max-frequency-points 256
```

`adaptive-z` starts with high-energy responses, then after each frozen-pole residue solve adds the worst Z-log port pairs to the next relocation iteration.

Results:

| Selection | Worst Z pairs injected | Best iteration | Best Z log RMS | Readout |
| --- | ---: | ---: | ---: | --- |
| energy | 0 | 2 | 1.251 | baseline |
| adaptive-z | 16 | 3 | 1.341 | worse |
| adaptive-z | 4 | 2 | 1.266 | close, still worse |

This rejects the naive version of the hypothesis. Directly forcing worst Z pairs into the denominator relocation overreacts: it helps target the visible error but degrades the shared pole placement. The useful conclusion is negative but sharp:

- IdEM's p4poles behavior is closer to robust high-energy/common-response selection than to chasing current worst Z pairs.
- The remaining 1.251 -> 1.209 gap is unlikely to be solved by p4poles selection alone.
- The next target should shift to residue-side structure: real-state residue solve, split/grouped residue solving, or per-response scaling after poles are already placed.

## Local Relocation + Real-State Residues

The next residue-side test keeps the local common-pole relocation unchanged and swaps only the residue solve basis:

```powershell
python -m agent_spice.cli probe-idem-relocate-sweep `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\local-relocate-sweep-30p-order32-realstate-v1\report.jsonl `
  --csv runs-sparam\local-relocate-sweep-30p-order32-realstate-v1\report.csv `
  --order 32 `
  --iterations 3 `
  --parameter-type s `
  --response-selections energy `
  --max-pole-responses-list 64 `
  --relative-weight-powers 0 `
  --residue-bases complex,real-state `
  --fit-max-frequency-points 256
```

Result:

| Pole source | Residue basis | Iteration | S relative RMS | Z log RMS | Diag Z log RMS | Residue cond. | Rank |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local relocation | complex | 2 | 0.011886 | 1.251 | 1.366 | 223.5 | 33 |
| local relocation | complex | 3 | 0.011517 | 1.284 | 1.399 | 261.8 | 33 |
| local relocation | real-state | 2 | 0.016257 | 1.359 | 1.410 | 361.3 | 59 |
| local relocation | real-state | 3 | 0.012056 | 0.991 | 1.096 | 3392.5 | 63 |

An `iterations=4` check confirmed iteration 3 is the current sweet spot:

| Iteration | Residue basis | Z log RMS |
| ---: | --- | ---: |
| 3 | real-state | 0.991 |
| 4 | real-state | 1.079 |

This is the first local result that beats the previous IdEM-pole fixed-residue reference (`1.209` with IdEM init1 poles + complex S-domain residue LS). The biggest remaining lesson is that pole and residue choices interact: real-state residues are worse on early/local init poles, but substantially better once relocation has produced the iteration-3 pole set.

Current best local recipe on the 30-port case:

- order: 32 common poles
- relocation: 3 iterations
- p4poles analog: 64 high-energy S responses
- relocation weighting: absolute
- residue solve: S-domain real-state basis
- result: `Z log RMS = 0.991`, `diag Z log RMS = 1.096`, `S relative RMS = 0.0121`

## Reproducible IdEM-Like Entry Point

The current best recipe is now available as a stable CLI entry point:

```powershell
python -m agent_spice.cli fit-idem-like `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-v1\report.json `
  --csv runs-sparam\fit-idem-like-30p-order32-v1\iterations.csv
```

Defaults:

- `order=32`
- `iterations=4`, with best iteration selected by `z_log_magnitude_rms_error`
- `parameter_type=s`
- `response_selection=energy`
- `max_pole_responses=64`
- `fit_max_frequency_points=256`
- `residue_basis=real-state`

30-port result from this entry point:

| Best iteration | Residue basis | Z log RMS | Diag Z log RMS | S relative RMS | Residue cond. |
| ---: | --- | ---: | ---: | ---: | ---: |
| 3 | real-state | 0.990716 | 1.0955 | 0.0120559 | 3392.47 |

This command is the current local IdEM-like benchmark harness. It is still not a SPICE exporter, but it gives a reproducible fitting quality target that can now be used across multiple cases and orders.

## Saved Model Artifact

`fit-idem-like` can now save the selected best rational model to a compressed `.npz` artifact:

```powershell
python -m agent_spice.cli fit-idem-like `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\report.json `
  --csv runs-sparam\fit-idem-like-30p-order32-model-v1\iterations.csv `
  --model-output runs-sparam\fit-idem-like-30p-order32-model-v1\model.npz
```

The artifact stores:

- selected poles in rad/s,
- residue basis (`complex` or `real-state`),
- fitted coefficient matrix,
- Touchstone reference impedances,
- real-state pole block metadata for replay/export.

Replay command:

```powershell
python -m agent_spice.cli eval-idem-like-model `
  runs-sparam\fit-idem-like-30p-order32-model-v1\model.npz `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\eval.json
```

30-port replay result:

| Source | Z log RMS | Diag Z log RMS | S relative RMS |
| --- | ---: | ---: | ---: |
| fit report | 0.990716 | 1.0955 | 0.0120559 |
| saved model replay | 0.990716 | 1.0955 | 0.0120559 |

This is an important line in the sand: the local IdEM-like fit is now a reusable rational model artifact, not just a transient probe result. The next gap toward IdEM parity is export and circuit-consumable realization.

## Fitted Touchstone Export

The saved model artifact can now be exported to a fitted Touchstone file:

```powershell
python -m agent_spice.cli export-idem-like-touchstone `
  runs-sparam\fit-idem-like-30p-order32-model-v1\model.npz `
  runs-sparam\fit-idem-like-30p-order32-model-v1\fitted.s30p `
  --reference user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\export_touchstone.json
```

Self-replay check on the exported file:

```powershell
python -m agent_spice.cli eval-idem-like-model `
  runs-sparam\fit-idem-like-30p-order32-model-v1\model.npz `
  runs-sparam\fit-idem-like-30p-order32-model-v1\fitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\eval_on_export.json
```

Result:

| Check | Z log RMS | Diag Z log RMS | S relative RMS |
| --- | ---: | ---: | ---: |
| model vs exported fitted Touchstone | 0 | 0 | 0 |
| original vs exported fitted Touchstone | 0.990716 | 1.095505 | 0.0120559 |

This creates a tool-consumable `fitted.s30p` that can be opened by external RF tools while preserving the local IdEM-like model response exactly at the reference frequency grid. It is still one step short of a SPICE macro-model, but it gives a robust export contract for response quality.

## State-Space Artifact

The saved rational model can also be exported to an explicit state-space artifact:

```powershell
python -m agent_spice.cli export-idem-like-statespace `
  runs-sparam\fit-idem-like-30p-order32-model-v1\model.npz `
  runs-sparam\fit-idem-like-30p-order32-model-v1\statespace.npz `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\statespace_export.json
```

Replay command:

```powershell
python -m agent_spice.cli eval-idem-like-statespace `
  runs-sparam\fit-idem-like-30p-order32-model-v1\statespace.npz `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-model-v1\statespace_eval.json
```

30-port replay result:

| Artifact | States | Z log RMS | Diag Z log RMS | S relative RMS |
| --- | ---: | ---: | ---: | ---: |
| state-space `.npz` | 1860 | 0.990716 | 1.0955 | 0.0120559 |

This proves the local IdEM-like model can be represented as explicit `A/B/C/D` matrices and replayed without losing fitted response quality. The state count is currently larger than the nominal order-32 pole count because the local relocation step does not preserve conjugate pairing; the real-state realization therefore adds conjugate partners during residue fitting. The next algorithm target is to enforce or recover conjugate pole pairs during relocation so the same quality can be achieved with a compact state count.

## Compact Pole Pairing Probe

Two compact-pole relocation modes were added:

- `--pole-pairing conjugate`: force the relocated pole set back to conjugate pairs after each relocation.
- `--relocation-basis real-state`: solve the relocation denominator in a real-valued IdEM-style basis rather than an unconstrained complex denominator.

Baseline compact pairing:

```powershell
python -m agent_spice.cli fit-idem-like `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-paired-v1\report.json `
  --csv runs-sparam\fit-idem-like-30p-order32-paired-v1\iterations.csv `
  --model-output runs-sparam\fit-idem-like-30p-order32-paired-v1\model.npz `
  --iterations 4 `
  --residue-basis real-state `
  --fit-max-frequency-points 256 `
  --max-pole-responses 64 `
  --pole-pairing conjugate
```

Real-basis compact relocation:

```powershell
python -m agent_spice.cli fit-idem-like `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-order32-realreloc-paired-v1\report.json `
  --csv runs-sparam\fit-idem-like-30p-order32-realreloc-paired-v1\iterations.csv `
  --model-output runs-sparam\fit-idem-like-30p-order32-realreloc-paired-v1\model.npz `
  --iterations 4 `
  --residue-basis real-state `
  --fit-max-frequency-points 256 `
  --max-pole-responses 64 `
  --pole-pairing conjugate `
  --relocation-basis real-state
```

30-port results:

| Recipe | States | Best iter | Z log RMS | Diag Z log RMS | S relative RMS | Residue cond |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unconstrained relocation + real-state residue | 1860 | 3 | 0.990716 | 1.0955 | 0.0120559 | 3392 |
| post-relocation conjugate pairing | 960 | 2 | 1.38383 | 1.46743 | 0.196347 | 459 |
| real-state relocation + conjugate pairing | 960 | 1 | 1.42057 | 1.39319 | 0.341391 | 3.56e16 |
| IdEM compact recipe v1 (`log`, `f_min=10 MHz`, 256 points, 64 responses) | 960 | 1 | 1.11739 | 1.21795 | 0.135687 | 5.87e5 |
| IdEM compact recipe v2 (`log`, `f_min=10 MHz`, 128 points, 128 responses) | 960 | 1 | 0.862216 | 0.893769 | 0.135225 | 4.65e5 |

The compact 960-state artifact now exists, but it exposes the real gap: simply forcing conjugate pairs is not enough. The best unconstrained path is still much more accurate, while IdEM gets compact order-32 common poles without paying that accuracy penalty. The next target is therefore not export mechanics; it is the pole relocation algorithm itself, especially the constrained real-denominator solve and conditioning strategy.

The best compact recipe found so far is now available as a CLI preset:

```powershell
python -m agent_spice.cli fit-idem-like `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --recipe idem-compact `
  --report runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\report.json `
  --csv runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\iterations.csv `
  --model-output runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\model.npz
```

The preset expands to compact order-32 settings: log-spaced initial poles, `f_min=10 MHz`, two relocation iterations, conjugate pole pairing, real-state residues, 128 fit frequency samples, and 128 selected pole-relocation responses. This result is a meaningful move toward IdEM parity: the state count now matches IdEM's order-32/common-pole interpretation (`30 ports * 32 states = 960`) while the 30-port Z-log error improves from the first compact attempt's `1.38383` to `0.862216`.

The v2 state-space replay confirms the compact artifact preserves the fitted model response:

```powershell
python -m agent_spice.cli eval-idem-like-statespace `
  runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\statespace.npz `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --report runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\statespace_eval.json
```

Result: `states=960`, `z_log_rms=0.862216`, `diag_z_log_rms=0.893769`, `s_rel_rms=0.135225`.

## Joint Pole-Residue Micro-Refinement

The next prototype adds a local joint refinement command:

```powershell
python -m agent_spice.cli refine-idem-like `
  runs-sparam\fit-idem-like-30p-idem-compact-recipe-v2\model.npz `
  user_input\spara\5power_30port_wocap_121124_221036_4876_DCfitted.s30p `
  --output runs-sparam\fit-idem-like-30p-idem-compact-joint-refine-v1\model.npz `
  --report runs-sparam\fit-idem-like-30p-idem-compact-joint-refine-v1\report.json `
  --iterations 1 `
  --candidate-pair-count 4 `
  --relative-step 0.02 `
  --fit-max-frequency-points 128
```

This is deliberately not a global nonlinear optimizer. Each refinement round:

1. ranks compact conjugate pole pairs by residue/coefficient energy,
2. tries small stable `sigma` and `omega` perturbations on the top pairs,
3. re-solves residues in the real-state basis for each candidate,
4. accepts only the candidate that improves the selected metric.

30-port compact order-32 results:

| Model | States | Z log RMS | Diag Z log RMS | S relative RMS |
| --- | ---: | ---: | ---: | ---: |
| compact recipe v2 | 960 | 0.862216 | 0.893769 | 0.135225 |
| joint refine v1 | 960 | 0.817058 | 0.782324 | 0.135164 |
| joint refine v2 | 960 | 0.723842 | 0.46668 | 0.135272 |
| joint refine v4 | 960 | 0.713908 | 0.541588 | 0.135279 |

The important signal is that same-order compact accuracy improves without increasing the state count. The S-relative metric barely moves, and optimizing directly for S-relative improves S only marginally while damaging Z (`z_log_rms=1.29196`, `s_rel_rms=0.134937`). This suggests the next joint refinement should use a guarded multi-objective accept rule rather than a single scalar selector: improve Z/diagonal-Z while constraining S-relative degradation, then separately target S residual structure.

Frequency normalization and real-numerator constrained relocation were also probed:

| Probe | Best Z log RMS | Note |
| --- | ---: | --- |
| complex relocation + frequency normalization + pairing | 1.49471 | no improvement |
| real-state relocation + frequency normalization + pairing | 2.23619 | better conditioning, worse poles |
| real-state relocation + real numerator + pairing | 2.0575 | closer structural assumption, worse accuracy |
| real-state relocation + real numerator + frequency normalization + pairing | 1.86994 | still worse than complex relocation |

So the current evidence says the bigger gain is not just "make relocation more real-valued"; it is the initialization/conditioning combination. IdEM's initial pole floor is much higher than our original near-DC linear grid, and a log grid with a low-MHz floor materially improves compact common-pole quality.

## RMS Definition Alignment

One important reporting mismatch was identified: `s_rms_error` in this tool historically used a summed port-pair RMS:

```text
sqrt(sum_ij(mean_f(|S_ij - Sfit_ij|^2)))
```

IdEM-style reports use the port-pair mean RMS:

```text
sqrt(mean_ij(mean_f(|S_ij - Sfit_ij|^2)))
```

For an `N`-port network, the relationship is:

```text
s_mean_rms_error = s_rms_error / N
```

The evaluation reports now include `s_mean_rms_error` explicitly so IdEM comparisons use the same scale.

30-port compact examples with the aligned metric:

| Model | Summed S RMS | Mean S RMS | Z log RMS | Diag Z log RMS |
| --- | ---: | ---: | ---: | ---: |
| compact recipe v2 | 0.706947 | 0.0235649 | 0.862216 | 0.893769 |
| joint refine wide v2 | 0.707259 | 0.0235753 | 0.712437 | 0.514742 |

This changes the interpretation of the gap. The compact order-32 Z-domain work above is still useful, but S-RMS comparisons against IdEM must use `s_mean_rms_error`, not the summed `s_rms_error`.
