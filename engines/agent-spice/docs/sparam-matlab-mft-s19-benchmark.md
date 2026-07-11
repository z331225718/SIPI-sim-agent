# MATLAB Reference MFT-NNLS S19 Benchmark

## Question

Does the original MATLAB MFT-NNLS toolbox meet the S19 `RMS <= 0.001` target,
or is the Python port failure only a porting artifact?

## Important Scope

The raw Touchstone file has 826 points including exact DC. MATLAB
`VFdriver` logarithmic pole initialization produces non-finite results at
exact DC, so this reference run excludes that one point and uses the remaining
825 positive-frequency samples. This is therefore favorable to MATLAB and is
not a direct replacement for the Python 826-point Gate B.

RMS below is always recomputed against the raw Touchstone S matrix; MATLAB
RPdriver's printed `rmserr` is instead its perturbation from the pre-RP model.

## Results

### Port-parity profile

`weightparam=1`, `Niter1/Niter2=1/1`, `passive_DE=0`, `Niter_out=4`.

| Order | Raw RMS after RP | Input-grid max sigma |
| ---: | ---: | ---: |
| 8 | 0.035721 | 1.000002 |
| 10 | 0.026946 | 1.001472 |
| 12 | 0.021182 | 1.008031 |
| 14 | 0.020503 | 1.002439 |
| 16 | 0.023851 | 1.070052 |

### MATLAB reference-strength profile

`weightparam=2`, `Niter1/Niter2=7/4`, `passive_DE=1`, `Niter_out=20`,
`alpha=1.01`. RPdriver achieved its own passivity stopping criterion for all
listed orders, but the raw-data RMS target still failed.

| Order | Raw RMS after RP | Input-grid max sigma |
| ---: | ---: | ---: |
| 16 | 0.047375 | 0.999999 |
| 20 | 0.042406 | 0.999999 |
| 24 | 0.037897 | 0.999999 |
| 32 | 0.024129 | 1.000000 |
| 40 | 0.015292 | 0.999999 |
| 50 | 0.007653 | 0.999999 |
| 64 | 0.008551 | 0.999999 |
| 80 | 0.004539 | 1.000067 |

## Conclusion

On this S19 data, the MATLAB reference itself does not meet `RMS <= 0.001`
through order 80, even under a more favorable no-DC fit and its stronger
example-style configuration. The Python Gate B failure is consequently not
explained solely by the Python port or its RP-NNLS implementation.

This does not prove no higher MATLAB order can ever pass. It does prove that
the claimed low-order, faster, lower-memory advantage is absent across the
tested range, so there is no basis to continue promotion work.

The local artifacts are:

- `runs-sparam/matlab-mft-s19-benchmark.json`
- `runs-sparam/matlab-mft-s19-reference-benchmark.json`
- `runs-sparam/matlab-mft-s19-reference-highorder.json`
- `runs-sparam/matlab-mft-s19-reference-veryhighorder.json`

The reproducible MATLAB harness is
[`matlab_mft_s19_benchmark.m`](../scripts/matlab_mft_s19_benchmark.m).
