# Solver Toolchain

Agent-Spice treats external simulators as a pinned toolchain, not as Python package code.
The repository stores installer metadata, scripts, and a Git LFS portable runtime package for no-admin Windows installs.

## Included Tools

The pinned toolchain is declared in `third_party/solvers.lock.json`.

| Tool | Pinned version | Purpose |
|---|---:|---|
| ngspice | 46 | Fast local SPICE execution for MVP smoke and regression work. |
| XyceNF | 7.10.0 | Xyce Windows executable for single-process validation. |
| XDM | 2.6.0 | HSPICE-to-Xyce netlist translation via `xdm_bdl`. |

Default installation root:

```powershell
$env:USERPROFILE\tools\agent-spice-solvers
```

## Install

From the repository root:

```powershell
git lfs pull
.\tools\install-solvers.ps1
.\tools\doctor-solvers.ps1 -Smoke
```

The installer:

- first uses `third_party/solver-packages/agent-spice-solvers-win64.zip` when that repo-local portable package is present;
- otherwise downloads the exact archives named in `third_party/solvers.lock.json`;
- verifies SHA256 before installing downloaded archives;
- extracts or installs into the user-local install root;
- creates stable command shims for `ngspice`, `Xyce`, and `xdm_bdl`;
- adds the solver directories to the user PATH.

Open a new shell after installation, or run:

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

To ignore the repo-local portable package and rebuild from official downloads:

```powershell
.\tools\install-solvers.ps1 -PreferDownload
```

## Portable Install Without Admin Rights

Some remote Windows machines cannot run installers or do not grant administrator rights.
Do not run the Xyce installer there. Pull the repo-local portable package and let the script unpack it into the remote user's profile:

```powershell
git lfs pull
.\tools\install-solvers.ps1 -SkipPathUpdate
.\tools\doctor-solvers.ps1 -Smoke
```

If the package is outside the repository, pass it explicitly:

```powershell
.\tools\install-solvers.ps1 -PortableZip .\agent-spice-solvers-win64.zip -SkipPathUpdate
.\tools\doctor-solvers.ps1 -Smoke
```

If the remote environment does allow writing the user PATH, omit `-SkipPathUpdate`.

To refresh the package, build from an already-installed solver runtime on a machine where all tools work:

On the machine with solvers installed:

```powershell
.\tools\install-solvers.ps1 -PackagePortable .\third_party\solver-packages\agent-spice-solvers-win64.zip
```

This package is generated as a runtime-only zip: solver `bin` directories, ngspice `lib` and `share`, plus Xyce/XDM documentation or license files needed for redistribution review.

After refreshing it, validate the repository-default path in a clean install root:

```powershell
$testRoot = Join-Path $env:TEMP "agent-spice-repo-package-test"
Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
.\tools\install-solvers.ps1 -InstallRoot $testRoot -SkipPathUpdate
.\tools\doctor-solvers.ps1 -InstallRoot $testRoot -Smoke
```

To ignore the repo-local package while doing this validation, pass `-PreferDownload`.

The default install extracts the portable runtime under:

```powershell
$env:USERPROFILE\tools\agent-spice-solvers
```

If the remote environment does not allow writing the user PATH, refresh the current shell manually:

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

Then verify with an executable smoke check through ngspice, XDM, and Xyce:

```powershell
.\tools\doctor-solvers.ps1 -Smoke
```

## Verify

```powershell
.\tools\doctor-solvers.ps1 -Smoke
```

Manual checks:

```powershell
ngspice -v
Xyce -v
xdm_bdl -h
```

Project smoke:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-exec-ngspice --execute
```

For Xyce, the current code path does not yet invoke XDM automatically. Use XDM explicitly:

```powershell
New-Item -ItemType Directory -Force xdm-smoke | Out-Null
xdm_bdl -s hspice -d xdm-smoke -o xyce tests/fixtures/hspice/simple_pi.sp
Xyce xdm-smoke/simple_pi.sp
```

## Source Availability

These projects do have source code:

- ngspice source: <https://ngspice.sourceforge.io/gitaccess.html>
- Xyce source: <https://github.com/Xyce/Xyce>
- XDM source: <https://github.com/Xyce/XDM>

If Agent-Spice needs to patch a solver, prefer a fork or submodule under `third_party/src/`.
Until then, pin upstream artifacts through `solvers.lock.json` and keep the repo-local runtime package limited to `third_party/solver-packages/agent-spice-solvers-win64.zip`.

## License Notes

This is not legal advice.

- ngspice is primarily Modified BSD, but its source tree includes components under LGPL, GPL, MPL, MIT, and public-domain terms.
- XDM is GPL-3.0-or-later.
- Xyce source is GPL-3.0. The Windows `XyceNF` installer carries Sandia/NTESS non-free and export-control notices.

Because of size and license/export-control constraints, store solver runtime packages with Git LFS and confirm the repository visibility and redistribution constraints before pushing them.
