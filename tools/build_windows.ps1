#requires -Version 5.1
<#
.SYNOPSIS
Check Windows prerequisites, then build and smoke the default native SIPI CLI.
.DESCRIPTION
This is a source-development build, not a release or capability certification.
No system tools are installed and no persistent PATH settings are changed.
.PARAMETER Check
Check installed prerequisite files only; do not download or build anything.
#>
[CmdletBinding()]
param([switch]$Check)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target = 'x86_64-pc-windows-msvc'
$targetDir = Join-Path $root 'target'
$problems = @()

try {
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    if ($env:OS -ne 'Windows_NT' -or $architecture -ne 'AMD64') {
        throw 'This source-build entry supports Windows x64 only.'
    }
    foreach ($file in @('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', 'crates/sipi-cli/Cargo.toml')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) {
            throw "Incomplete SIPI checkout: missing $file. Clone the complete repository."
        }
    }

    $cargo = Get-Command cargo.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $cargoPath = if ($cargo) { $cargo.Source } else { $null }
    if (-not $cargoPath) {
        $cargoHome = $env:CARGO_HOME
        if (-not $cargoHome) { $cargoHome = Join-Path $env:USERPROFILE '.cargo' }
        $candidate = Join-Path $cargoHome 'bin/cargo.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $cargoPath = $candidate }
    }
    if (-not $cargoPath) {
        $problems += 'Cargo/Rust not found. Install Rust via https://rust-lang.org/tools/install/ then reopen PowerShell.'
    } else {
        Write-Host "Cargo: $cargoPath"
    }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $vs = $null
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0) { $vs = $null }
    }
    if (-not $vs -or -not (Test-Path -LiteralPath (Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat') -PathType Leaf)) {
        $problems += 'MSVC C++ Build Tools not found. In Visual Studio Installer select Desktop development with C++, including MSVC x64/x86 tools and a Windows SDK.'
    } else {
        Write-Host "MSVC: $vs"
    }

    $kits = Get-ItemProperty -LiteralPath 'HKLM:/SOFTWARE/Microsoft/Windows Kits/Installed Roots' -Name KitsRoot10 -ErrorAction SilentlyContinue
    $sdk = @()
    if ($kits -and $kits.KitsRoot10) {
        $sdk = @(Get-ChildItem -LiteralPath (Join-Path $kits.KitsRoot10 'Lib') -Directory -ErrorAction SilentlyContinue | Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/kernel32.lib') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'ucrt/x64/ucrt.lib') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $kits.KitsRoot10 "Include/$($_.Name)/um/Windows.h") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $kits.KitsRoot10 "Include/$($_.Name)/ucrt/stdio.h") -PathType Leaf)
        })
    }
    if ($sdk.Count -eq 0) {
        $problems += 'Windows SDK x64 headers/libraries not found. Add a Windows 10/11 SDK using Visual Studio Installer.'
    } else {
        Write-Host "Windows SDK: $($sdk.Name -join ', ')"
    }
    if ($problems.Count -gt 0) { throw ($problems -join [Environment]::NewLine) }
    if ($Check) {
        Write-Host 'Prerequisite files found. Build selects the toolchain in rust-toolchain.toml; compilation is not checked by -Check.'
        exit 0
    }

    Push-Location -LiteralPath $root
    try {
        & $cargoPath build --locked --release -p sipi-cli --bin sipi --target $target --target-dir $targetDir
        if ($LASTEXITCODE -ne 0) {
            throw "Cargo build failed (exit $LASTEXITCODE). See the compiler error above. The pinned Rust toolchain and crates require network access on first build."
        }
        $exe = Join-Path $targetDir "$target/release/sipi.exe"
        $version = & $exe version --json | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $version.status -ne 'ok') { throw 'Native CLI version smoke failed.' }
        $example = & $exe example channel.run --json | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $example.status -ne 'ok') { throw 'Native channel example smoke failed.' }
        $run = $example.result.request | ConvertTo-Json -Depth 40 -Compress | & $exe channel run --stdin | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $run.status -ne 'ok' -or
            $run.result.kernel_sample_count -ne 2 -or
            $run.result.gain_v_per_v.Count -ne 2 -or
            $run.result.gain_v_per_v[0] -ne 1 -or $run.result.gain_v_per_v[1] -ne 0) {
            throw 'Native channel through-kernel smoke failed; expected [1, 0].'
        }
        Write-Host "Built and channel-smoke-tested: $exe"
        Write-Host 'Scope: default native development CLI, not the separate PyBERT channel bench or an accepted release.'
    } finally {
        Pop-Location
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
