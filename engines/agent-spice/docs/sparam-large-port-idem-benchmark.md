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

The native/lightweight path no longer shows a consistent speed or memory disadvantage. On all three cases above it is faster and lower-memory than IdEM at the lowest order that reaches the target.

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

`Test13.s60p` with the current IdEM-fast fit and low-memory passivity enabled:

| Run | Selected order | Mean RMS | Passive before | Passive after | Violation bands before | Violation bands after | Time | Peak memory |
|---|---:|---:|---|---|---:|---:|---:|---:|
| check only | 9 | 0.000593962 | false | false | 169 | 169 | 8.08 s | 177.9 MB |
| sparse enforce, 8 samples, rollback | 9 | 0.000593962 | false | false | 169 | 169 | 15.94 s | 181.1 MB |

Interpretation:

- The memory target is now in the right range: `Test13.s60p` passivity check/enforce peaks around `181 MB`, comparable to or below the IdEM order-6 run's `155.5 MB`.
- The enforcement algorithm is not yet effective: sparse residue perturbation did not reduce the 169 Hamiltonian violation bands on `Test13.s60p`.
- A rollback guard is required and now active: if a residue perturbation worsens passivity score, the model keeps the best seen residues rather than silently destroying fit accuracy. Before this guard, the same sparse enforcement path could degrade mean RMS from `0.000593962` to `0.0673212` while still remaining non-passive.

Next target:

- Replace the current all-pole residue perturbation with a genuinely local violation-band QP: choose the worst few singular vectors, restrict residue variables to the poles with highest sensitivity at those frequencies, and accept updates only when both passivity score improves and mean RMS damage stays bounded.

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
