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
.\tools\install-solvers.ps1
.\tools\doctor-solvers.ps1
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

After installing solvers, run the ngspice execution smoke:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-exec-ngspice --execute
Test-Path runs-exec-ngspice/simple_pi/simple_pi__base/stdout.log
```

For Xyce today, run XDM explicitly before Xyce:

```powershell
New-Item -ItemType Directory -Force xdm-smoke | Out-Null
xdm_bdl -s hspice -d xdm-smoke -o xyce tests/fixtures/hspice/simple_pi.sp
Xyce xdm-smoke/simple_pi.sp
```

Solver toolchain details are in `docs/solver-toolchain.md`.

The project spec is in `docs/pi-spice-simulator-spec.md`.

