# Agent-Spice

Agent-Spice is an early PI simulation middleware prototype focused on HSPICE legacy deck compatibility and future S-parameter/CPM workflows.

Current checkpoint:

- HSPICE project manifest parsing.
- HSPICE deck audit for directives, includes, libraries, and unsupported commands.
- `.alter` expansion into independent cases.
- `.measure/.probe/.print` normalization.
- Compatibility report and basic HSPICE-to-backend conversion.
- Backend command adapters for ngspice, Xyce, and XDM-assisted Xyce translation.
- Target-driven Touchstone fitting with truthful passivity checking and enforcement.

Install and verify local solver tools:

```powershell
git lfs pull
.\tools\install-solvers.ps1
.\tools\doctor-solvers.ps1 -Smoke
```

Open a new terminal after installation, or refresh the current shell:

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

## Verify The MVP

Run the unit and smoke suite:

```powershell
python -m pytest -v
```

Generate HSPICE case artifacts without running a simulator:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-smoke
Test-Path runs-smoke/simple_pi/simple_pi__base/case.cir
Test-Path runs-smoke/simple_pi/simple_pi__base/compat_report.json
```

Verify `.alter` case expansion:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/alter_pi.sp --backend ngspice --output-root runs-smoke-alter
Test-Path runs-smoke-alter/alter_pi/alter_pi__base/case.cir
Test-Path runs-smoke-alter/alter_pi/alter_pi__alter_001_high_decap/case.cir
Test-Path runs-smoke-alter/alter_pi/alter_pi__alter_002_low_decap/case.cir
```

Verify the synthetic-real HSPICE corpus golden reports:

```powershell
python -m pytest tests/test_hspice_corpus_golden.py -v
```

## S-Parameter Fitting

`fit-sparam` is a target-driven workflow based on the local IdEM-fast/native VF implementation. The user supplies a final mean S-RMS target and chooses how passivity is handled. The tool searches for the lowest accepted effective common-pole order up to `--max-order`.

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity check `
  --max-order 24 `
  --output runs-sparam\model.sp `
  --report runs-sparam\model.json `
  --html-report runs-sparam\model.html `
  --log runs-sparam\model.log
```

The RMS target is:

```text
sqrt(mean(abs(S_fit - S_raw) ** 2))
```

It is evaluated over every original frequency point and every S-parameter channel, so it does not grow with port count.

Effective order is reported as:

```text
real pole count + 2 * complex pole-pair count
```

### Passivity Policies

`--passivity check` is the default.

- `off`: fit and evaluate RMS without passivity work.
- `check`: select order from RMS, run the Hamiltonian/adaptive full-frequency checker, and emit a non-passive model as `PASS_WITH_PASSIVITY_WARNING`.
- `enforce`: run enforcement only for orders whose pre-enforcement RMS can meet the target. An order passes only when the post-enforcement model meets both the RMS target and `max_sigma <= 1 + 1e-6`.

Example requiring a passive final model:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 24 `
  --output runs-sparam\model_passive.sp
```

Enforcement is judged from the final model. A good pre-enforcement RMS does not satisfy the target if passivity repair pushes the final RMS above the requested value.

### Order Search

Vector-fitting error is not strictly monotonic in order, so the production scheduler does not use binary search. It evaluates an ascending even-order ladder and, after the first passing order, backfills the adjacent untested integer orders. Every requested order is evaluated at most once.

Defaults:

- `--max-order 24` for 60 or more ports.
- `--max-order 40` below 60 ports.
- Full original frequency grid for fitting and final evaluation.
- Native vector fitting and the IdEM-fast topology/pole-relocation profile.

### Success And Failure

On success, the requested SPICE output and JSON/HTML reports are written. On failure, trial reports and the top-level audit report remain available, but the requested production SPICE output is absent. The tool never promotes the closest failed model as a successful result.

The JSON report includes:

- `rms_target`, `passivity_policy`, and `max_order`.
- `selected_effective_order`, `target_met`, and `target_stop_reason`.
- Per-order pre/final RMS and pre/final max sigma.
- Fit, check, enforcement, total time, and peak RSS.
- Requested/effective order and pole topology counts.
- `rms_formula=mean_s_rms_v1` and `order_formula=real_plus_twice_complex_v1`.

Top-level time covers every attempted order in the target search, and top-level peak RSS is the maximum across those trials. Per-order costs remain available in `order_trials`.

For CI or signoff, add the quality gate:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 24 `
  --output runs-sparam\model.sp `
  --quality-profile signoff `
  --fail-on-quality
```

Historical candidate-list and passivity flags remain hidden compatibility aliases. New automation should use only `--rms-target`, `--passivity`, and `--max-order`.

The canonical Native/IdEM comparison is recorded in `docs/sparam-idem-full-benchmark.md`.
