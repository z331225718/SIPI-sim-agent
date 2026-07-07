# Agent-Spice

Agent-Spice is an early PI simulation middleware prototype focused on HSPICE legacy deck compatibility and future S-parameter/CPM workflows.

Current checkpoint:

- HSPICE project manifest parsing.
- HSPICE deck audit for directives, includes, libraries, and unsupported commands.
- `.alter` expansion into independent cases.
- `.measure/.probe/.print` normalization.
- Compatibility report and basic HSPICE-to-backend conversion.
- Backend command adapters for ngspice, Xyce, and XDM-assisted Xyce translation.
- Thin Touchstone metadata, VectorFitting, and CPM-lite/PWL entry points.

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

`fit-sparam` is now centered on the local IdEM-fast baseline. Older `compact` and
`high-accuracy` S-parameter presets are retired from this command path because
the active direction is native vector fitting with low-order common poles,
streaming reciprocal relocation, lightweight Touchstone loading, and targeted
high-frequency pole repair.

The normal command is intentionally short:

```powershell
python -m agent_spice.cli fit-sparam tests/fixtures/sparam/simple_through.s2p --output runs-sparam/simple_through.sp --report runs-sparam/fit_report.json --html-report runs-sparam/fit_report.html --log runs-sparam/fit.log
Test-Path runs-sparam/simple_through.sp
Test-Path runs-sparam/fit_report.json
Test-Path runs-sparam/fit_report.html
Test-Path runs-sparam/fit.log
```

For large-port Touchstone files (`.s60p`, `.s91p`, `.s163p`, etc.) the default
expands to the current IdEM-fast large-port recipe:

- native vector fitting backend
- manual low-order pole topology with log-spaced initialization
- two high-frequency complex pole pairs with damping `0.03`
- streaming reciprocal pole relocation
- lightweight Touchstone parsing
- at most 256 fit frequency points
- 14 vector-fit iterations per trial
- auto-order candidates `9,10,12,14,17,20`
- target mean S-domain RMS `0.002`
- passivity check/enforcement skipped by default for fitting speed

Example for a large package model:

```powershell
python -m agent_spice.cli fit-sparam .\user_input\spara\Test16.s91p `
  --output runs-sparam\Test16_s91p\model.sp `
  --report runs-sparam\Test16_s91p\fit_report.json `
  --html-report runs-sparam\Test16_s91p\fit_report.html `
  --log runs-sparam\Test16_s91p\fit.log
```

The JSON report records the selected order in `auto_model_order_selected`, every
trial in `auto_model_order_trials`, the stop reason in
`auto_model_order_stop_reason`, peak memory in `peak_memory_mb`, and elapsed
time in `elapsed_seconds`.

Recent validation against IdEM-aligned large-port cases:

| Case | Selected order | Mean S RMS | Trial time | Peak memory |
| --- | ---: | ---: | ---: | ---: |
| `Test13.s60p` | 9 | 0.000593962 | 5.47 s | 132.5 MB |
| `Test16.s91p` | 10 | 0.001819411 | 32.25 s total trial time | 251.3 MB |

The defaults are tuned for the current large-port path, not for exhaustive
accuracy sweeps. Override only the auto-order boundary first:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --output runs-sparam\model.sp `
  --auto-model-order-candidates 9,10,12,14,17,20,24 `
  --auto-target-mean-rms-error 0.0015
```

Passivity is deliberately off by default in the fast fitting path because the
current bottleneck work is algorithmic fitting order, speed, and memory. To run
passivity diagnostics or enforcement explicitly:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --output runs-sparam\model_passive.sp `
  --check-passivity `
  --enforce-passivity
```

Use the report's `quality.status`, `quality.blocking_reasons`, and `diagnostics[]`
to decide whether the model is only for exploration or is a transient handoff
candidate. For CI/signoff, enable the quality gate explicitly:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --output runs-sparam\model.sp `
  --report runs-sparam\fit_report.json `
  --html-report runs-sparam\fit_report.html `
  --log runs-sparam\fit.log `
  --quality-profile signoff `
  --fail-on-quality
```

During exploration, add `--allow-quality-warnings` if WARN diagnostics should still return exit code 0 while remaining visible in the reports.

When using Python module execution, use the underscore package name `agent_spice.cli`. The hyphenated `agent-spice` name is only for the installed console script.

More historical tuning notes are in `docs/sparam-fit-performance.md`. Some older
sections mention retired presets and should be treated as experiment logs rather
than the current recommended CLI path. The next-stage quality gate plan is in
`docs/sparam-quality-gate-plan.md`.

After installing solvers, run the ngspice execution smoke:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-exec-ngspice --execute
Test-Path runs-exec-ngspice/simple_pi/simple_pi__base/stdout.log
```

After installing solvers, run the XDM-assisted Xyce execution smoke:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend xyce-xdm --output-root runs-exec-xyce-xdm --execute
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/case.sp
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/xdm-out/case.sp
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/case.cir
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/xdm.stdout.log
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/xdm.stderr.log
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/xyce.stdout.log
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/xyce.stderr.log
Test-Path runs-exec-xyce-xdm/simple_pi/simple_pi__base/run_summary.json
```

To inspect the raw solver toolchain directly, run XDM explicitly before Xyce:

```powershell
New-Item -ItemType Directory -Force xdm-smoke | Out-Null
xdm_bdl -s hspice -d xdm-smoke -o xyce tests/fixtures/hspice/simple_pi.sp
Xyce xdm-smoke/simple_pi.sp
```

Solver toolchain details are in `docs/solver-toolchain.md`.

For remote Windows machines without administrator rights, use the repo-local portable solver package:

```powershell
git lfs pull
.\tools\install-solvers.ps1 -SkipPathUpdate
.\tools\doctor-solvers.ps1 -Smoke
```

When `third_party/solver-packages/agent-spice-solvers-win64.zip` exists, `install-solvers.ps1` uses that repo-local package directly. Use `-PreferDownload` to rebuild from official downloads, or `-PackagePortable .\third_party\solver-packages\agent-spice-solvers-win64.zip` to refresh the committed package from a working local install.

The project spec is in `docs/pi-spice-simulator-spec.md`.

