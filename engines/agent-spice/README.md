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

