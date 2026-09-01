# AS RFM Kernel Performance Observation

Status: observed only. This record is not a release or product performance
acceptance gate.

## Scope

This observation compares the existing Agent-Spice RFM pole/residue response
kernel on the same `channel.rfm` input. It does not compare SPICE solvers and
does not exercise S-parameter fitting, Xyce/XDM, or a new simulation path.
MATLAB R2024b uses the repository harness to evaluate the same RFM formula;
MATLAB has no native RFM importer in this comparison.

Input: `examples/circuit/rfm-deck/models/channel.rfm`

- Bytes: 296
- SHA-256: `a19731614f0ea63ff5bd0500b7301cb7daede2679c74652bb6a3464e27ac71ce`
- NPORT: 1; responses: 1; stored poles: 2; effective order: 3
- Frequency grid: 65,536 points from 0 to 200,000,000,000 Hz
- Warm-up runs: 2; timed runs: 5
- Host logical CPUs: 16; Rust Rayon workers: 16

## Final Measurement

The final run was made after the `evaluate_s_many` optimization, with MATLAB
R2024b launched using an isolated `MATLAB_PREFDIR` and
`MW_DISABLE_CONNECTOR=1`.

| Engine | Timed durations (ns) | Median (ns) |
| --- | --- | ---: |
| Rust | 1076900, 950300, 517700, 403100, 421200 | 517700 |
| MATLAB R2024b | 3005200, 805300, 1859500, 661600, 1061900 | 1061900 |
| Pinned upstream Python | 3024800, 3104400, 3135000, 3318000, 3002600 | 3104400 |

Observed ratios:

- Rust / MATLAB kernel: `0.48752236557114603`
- MATLAB / Rust kernel: `2.0511879466872704`
- Rust / upstream Python kernel: `0.16676330369797707`

The Rust kernel was faster than the MATLAB harness in this run. This is a
single-host observation, not a universal performance claim.

The Rust and MATLAB checksum deltas were within the harness tolerance:

```text
first_im          0
first_re          1.1102230246251565e-16
sum_abs_squared   7.503331289626658e-12
sum_imag          1.4779288903810084e-12
sum_real          2.091837814077735e-11
```

The complete diagnostic files remain outside the repository at
`C:\Users\z3312\AppData\Local\Temp\as-rfm-performance-root-verify-20260902012851`:

- `comparison.json` SHA-256: `410559d92f7cea33cc156a0805a9dec91ff8c9fa8dbf9c97a7e3852b12ca0c94`
- `rust.json` SHA-256: `152c95bf762c8ac640fbd143ccc9ee37fe02779a586de5ef45086430369e2c8c`
- `matlab.json` SHA-256: `d1a7c26b6b79e8a237ea146d9e24ebfa5c60a04300a7744b9f4b5073a25600f6`
- `upstream-python.json` SHA-256: `63b317ed628d1c0ca5d0b6cd84e70df6f3f0b02fa8fee1c2509d99107a0c801f`

The source hashes recorded by that run include:

- `crates/sipi-agent-spice-direct/src/as06_run_rfm.rs`: `9341a0f0e8679e43b8d2f4679f9119954d5c28fc9cd2bb83b3d475d952a72672`
- `tools/benchmark_as_rfm_matlab.py`: `a97114e65e8375e742a2c6e523c016dbc7a75f205ec757b4ec35a0168f4d31ad`
- `tools/as_performance_rfm_kernel_bench/src/main.rs`: `35f478ca8fde925b6c487c77578d05b3bb531ac8e9213e9f8e2c8df58b88cb13`

## Change Under Test

`RfmModel::evaluate_s_many` retains its public signature, finite-input checks,
response-major shape, frequency order, and scalar operation order. Calls with
at least 4,096 frequencies use Rayon (already used elsewhere in the workspace)
to evaluate
independent frequencies in parallel. Short calls use a preallocated nested
output and explicit loops to avoid one intermediate collection per frequency.
Each parallel result still comes from the existing `evaluate_s` evaluator, so
the 65,536-point regression compares every real and imaginary value by exact
`f64::to_bits()` against the scalar kernel.

The pre-optimization diagnostic (same fixture and workload) measured Rust at a
2,538,200 ns median versus MATLAB at an 800,300 ns median. That result exposed
the frequency-by-frequency allocation/dispatch bottleneck and motivated the
bounded parallel path; it is retained here only as diagnostic context.

## Reproduction

From the repository root, using the configured Rust toolchain and MATLAB R2024b:

```powershell
python tools/benchmark_as_rfm_matlab.py `
  --output-root C:\Users\z3312\AppData\Local\Temp\as-rfm-performance-rerun `
  --frequency-count 65536 --warmups 2 --repetitions 5

C:\Users\z3312\.cargo\bin\cargo.exe test `
  --manifest-path crates/sipi-agent-spice-direct/Cargo.toml --lib
C:\Users\z3312\.cargo\bin\cargo.exe clippy `
  --manifest-path crates/sipi-agent-spice-direct/Cargo.toml --all-targets -- -D warnings
C:\Users\z3312\.cargo\bin\cargo.exe fmt `
  --manifest-path crates/sipi-agent-spice-direct/Cargo.toml -- --check
python -m unittest tools.test_benchmark_as_rfm_matlab
```

The benchmark reports kernel time only; parsing, process startup, filesystem,
and JSON serialization are excluded from the kernel medians. Launch time is
reported separately. Results can vary with CPU scheduling, Rayon pool size,
MATLAB configuration, and the selected RFM model.
