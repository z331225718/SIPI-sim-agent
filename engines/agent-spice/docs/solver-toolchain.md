# Solver Toolchain

Agent-Spice treats external simulators as a pinned toolchain, not as Python package code.
The repository stores installer metadata and scripts; large binaries are downloaded into a user-local tools directory.

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
.\tools\install-solvers.ps1
```

The installer:

- downloads the exact archives named in `third_party/solvers.lock.json`;
- verifies SHA256 before installing;
- extracts or installs into the user-local install root;
- creates stable command shims for `ngspice`, `Xyce`, and `xdm_bdl`;
- adds the solver directories to the user PATH.

Open a new shell after installation, or run:

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

## Verify

```powershell
.\tools\doctor-solvers.ps1
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
Until then, keep solver binaries out of the main repository and pin the toolchain through `solvers.lock.json`.

## License Notes

This is not legal advice.

- ngspice is primarily Modified BSD, but its source tree includes components under LGPL, GPL, MPL, MIT, and public-domain terms.
- XDM is GPL-3.0-or-later.
- Xyce source is GPL-3.0. The Windows `XyceNF` installer carries Sandia/NTESS non-free and export-control notices.

Because of size and license/export-control constraints, do not commit downloaded solver binaries into this repository.
