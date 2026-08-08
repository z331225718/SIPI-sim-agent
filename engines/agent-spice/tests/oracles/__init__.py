"""Shared probes for external oracle lanes (ngspice / HSPICE / .NET).

This package intentionally contains no ``test_*`` modules so it is not
collected by pytest (``testpaths = ["tests"]`` would otherwise pick it up).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rust_engine() -> Path | None:
    """Path to the built Rust engine executable, or ``None``."""
    candidates = (
        ROOT / "native" / "agent-spice-sim" / "target" / "release" / "agent-spice-sim.exe",
        ROOT / "native" / "agent-spice-sim" / "target" / "release" / "agent-spice-sim",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def dotnet_dll() -> Path | None:
    """Path to the built .NET engine DLL, or ``None`` if SDK/DLL absent."""
    dll = ROOT / "native" / "AgentSpice.Engine" / "bin" / "Release" / "net8.0" / "AgentSpice.Engine.dll"
    if not dll.is_file():
        return None
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return None
    result = subprocess.run(
        [dotnet, "--list-sdks"], capture_output=True, text=True, check=False
    )
    if not result.stdout.strip():
        return None
    return dll


def ngspice_executable() -> str | None:
    return shutil.which("ngspice")


def hspice_executable() -> str | None:
    candidate = os.environ.get("AGENT_SPICE_HSPICE")
    if candidate:
        return candidate
    return shutil.which("hspice")
