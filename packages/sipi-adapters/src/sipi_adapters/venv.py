"""Isolated-venv execution of attested wheel bundles (M2-02b/M2-09 follow-up).

An attested wheel is installed with ``--no-deps`` into a per-run venv; third
party dependencies must be supplied by a managed lock in a later slice.  The
engine.lock extension ``sipi.m2.console-script`` names the console script that
the adapter invokes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class BundleExecutionError(RuntimeError):
    """Raised when an attested wheel cannot be installed or resolved."""


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def console_script_path(venv_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / (name + suffix)


def install_wheel(wheel_path: Path, venv_dir: Path, *, python: str = sys.executable) -> Path:
    created = subprocess.run([python, "-m", "venv", str(venv_dir)], capture_output=True, text=True)
    if created.returncode != 0:
        raise BundleExecutionError(f"venv creation failed: {created.stderr[-500:]}")
    venv_python_path = venv_python(venv_dir)
    installed = subprocess.run(
        [str(venv_python_path), "-m", "pip", "install", "--no-deps", "--quiet", str(wheel_path)],
        capture_output=True,
        text=True,
    )
    if installed.returncode != 0:
        raise BundleExecutionError(f"wheel install failed: {installed.stderr[-500:]}")
    return venv_python_path


def required_console_script(engine_entry: Mapping[str, Any]) -> str:
    script = engine_entry.get("extensions", {}).get("sipi.m2.console-script")
    if not isinstance(script, str) or not script:
        raise BundleExecutionError("wheel bundle does not declare sipi.m2.console-script")
    return script


def resolve_console_script(engine_entry: Mapping[str, Any], venv_dir: Path) -> Path:
    script = required_console_script(engine_entry)
    candidate = console_script_path(venv_dir, script)
    if not candidate.is_file():
        raise BundleExecutionError(f"console script missing after install: {script}")
    return candidate
