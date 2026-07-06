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
