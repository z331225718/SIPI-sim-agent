# IdEM S19 Adaptive Tuning Canonical Report

## Evidence Labels

- [FACT]: directly read from run summaries or audited trial artifacts listed in Data Sources.
- [STRONG INFERENCE]: conclusion forced by multiple run artifacts, but not a private IdEM implementation claim.
- [HYPOTHESIS]: plausible explanation kept separate from accepted results.

## Data Sources

- [FACT] `baseline_summary`: `runs-sparam\idem-s19-adaptive-v1-pipe-drain\summary.json`
- [FACT] `combination_summary`: `runs-sparam\idem-s19-combinations-v1\summary.json`
- [FACT] `old_baseline_summary`: `runs-sparam\idem-s19-adaptive-v1\summary.json`
- [FACT] `order58_diagnostic_summary`: `runs-sparam\idem-s19-order58-diagnostic\summary.json`
- [FACT] `weighting_summary`: `runs-sparam\idem-s19-weighting-v1\summary.json`

## Contract

| Field | Value |
| --- | --- |
| Contract version | `idem_s19_adaptive_v1` |
| Input SHA-256 | `87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e` |
| Points / ports | `826` / `19` |
| Frequency range Hz | `0.0`..`2000000000.0` |
| Threads | `8` |
| Order contract | `4:2:100` |
| Target RMS | `0.001` |
| Hard / idle timeout s | `1800.0` / `300.0` |
| Splitting | `none` |

## Accepted Model

[FACT] Accepted model: `stagnation-alpha0p01`, order `74`, final independent RMS `0.0009369159680584244`, authoritative passive `true`, sigma `0.9999999944613438`, elapsed `118.46026999992318` s, peak `88.29296875` MiB.

[FACT] Accepted fingerprint: `3f573f18841d9978f8f8df7304b542c3d7e35652df711df519a0ef83509b1845`.

[FACT] overall accepted=stagnation-alpha0p01.

## Chronology

### Fixed Control And Baseline

| Stage | Trial | Status | Order | RMS | Elapsed s | Peak MiB | Reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| fixed-order control | `fixed-order-order100` | FAIL | 100 | 0.01496172037 | 6.061134000075981 | 91.60546875 | pre_rms_above_target |
| old adaptive observation | `baseline-adaptive` | ERROR | N/A | N/A | 1301.5000721998513 | 67.33984375 | adaptive_fit_failed |

[FACT] Fixed-order order100 and internal adaptive are distinct: fixed-order used a fixed `order100` request, while internal adaptive used `orderMin=4`, `orderStep=2`, `orderMax=100`, target-driven IdEM refinement.

[STRONG INFERENCE] The old order58 stall was an initial observation. Later cap56/cap58/cap60 bounded diagnostics under the pipe-draining watchdog all completed fitting, so old runner pipe backpressure is more likely than a persistent fitting-engine stall. This report does not claim a private IdEM algorithm fault.

### Order58 Diagnostic

[FACT] Decision: `stop_order58_diagnostic_original_stall_not_stably_reproduced`; stable reproduction: `false`.

| Trial | Status | Order | RMS | Elapsed s | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| `baseline-cap56` | FAIL | 56 | 0.001452594546 | 65.08048240002245 | pre_rms_above_target |
| `baseline-cap58` | FAIL | 58 | 0.001397860094 | 70.15553370001726 | pre_rms_above_target |
| `baseline-cap60` | FAIL | 60 | 0.001244555245 | 75.60521820001304 | pre_rms_above_target |

### Single-Variable Stage

[FACT] Completed adaptive trials before stop: `6`.
[FACT] Stop rule: `splitting_none_trial_met_final_contract` at `stagnation-alpha0p01`.

| Trial | Status | Order | Final RMS | Elapsed s | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| `baseline-adaptive` | FAIL | 70 | 0.001025020608 | 102.36535029998049 | pre_rms_above_target |
| `enhanced-placement` | FAIL | 70 | 0.001025020608 | 102.41792710009031 | pre_rms_above_target |
| `postadding-2` | FAIL | 56 | 0.001613013068 | 74.53832280007191 | pre_rms_above_target |
| `postadding-3` | FAIL | 68 | 0.001037690482 | 136.67226220015436 | final_rms_above_target |
| `iterations-initial5-final3` | FAIL | 66 | 0.001050172197 | 92.20848479983397 | pre_rms_above_target |
| `stagnation-alpha0p01` | PASS | 74 | 0.0009369159680584244 | 118.46026999992318 | N/A |

### Combinations

[FACT] Task 7 root-local B is not the overall best. Root-local best was `combination-b-alpha0p01-initial5-final3`, but overall accepted remains `stagnation-alpha0p01`.
[FACT] Combination decision: A improves `false`, B improves `false`, run C `false`.

| Trial | Status | Order | Final RMS | Elapsed s | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| `combination-a-alpha0p01-postadding3` | FAIL | 68 | 0.001037690482 | 136.75867230002768 | final_rms_above_target |
| `combination-b-alpha0p01-initial5-final3` | PASS | 74 | 0.0009970539140490779 | 123.74417429999448 | N/A |

### Residual And Weighting

[FACT] Residual band rule: choose the worst above-mean contiguous segment where per-frequency aggregate squared error is above the mean threshold.
[FACT] Worst segment indices `117`..`195`, frequency `4786.30092322638`..`6309573.44480193` Hz, selection rule `aggregate_squared_error_gt_mean`, contribution `47.70137038847629%` < `50%`; weighting trials were skipped.
[FACT] Weighting eligibility: `false`, reason `worst_band_below_50_percent`, skip `weighting_not_justified`.
[FACT] S19 reciprocity: splitting `disallowed`, split_type `none`.

## Reproducible Commands

```powershell
python scripts/sparam_idem_s19_tuning.py run-stage --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p --output-root runs-sparam/idem-s19-adaptive-v1-pipe-drain --stage single-variable --no-resume
agent-spice run-stall-diagnostic --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p --output-root runs-sparam/idem-s19-order58-diagnostic --no-resume
python scripts/sparam_idem_s19_tuning.py run-stage --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p --output-root runs-sparam/idem-s19-combinations-v1 --stage combination --no-resume
python scripts/sparam_idem_s19_tuning.py run-stage --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p --output-root runs-sparam/idem-s19-weighting-v1 --stage weighting --no-resume
agent-spice report-idem-s19-tuning --output docs/sparam-idem-s19-tuning.md
```

[FACT] Resume behavior: completed PASS trials are reused only when fingerprint, contract, provenance, and required artifacts match; non-PASS terminal trials rerun on resume.

## Evidence Classification

- [FACT] `stagnation-alpha0p01` is the accepted model and satisfies target RMS plus authoritative passivity.
- [FACT] Task 7 combination B PASSed locally but did not improve RMS or elapsed time versus the accepted baseline.
- [FACT] Task 8 skipped weighting because `47.70137038847629%` is below the 50% gate.
- [STRONG INFERENCE] The old order58 observation is better explained by the old runner's pipe/backpressure behavior after bounded cap diagnostics completed under pipe-draining telemetry.
- [HYPOTHESIS] Additional IdEM private heuristics may affect order history, but this report makes no unsupported implementation claim.
