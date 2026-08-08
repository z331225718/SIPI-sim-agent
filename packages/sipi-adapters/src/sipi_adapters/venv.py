"""Isolated-venv execution of attested wheel bundles (M2-02b/M2-09 follow-up).

An attested wheel is installed with ``--no-deps`` into a per-run venv; third
party dependencies are supplied by the managed dependency lock (``bundle_manifest``
entries with ``role == "dependency"``), each pinned by sha256, so resolution never
hits a floating index.  The engine.lock extension ``sipi.m2.console-script`` names
the console script that the adapter invokes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class BundleExecutionError(RuntimeError):
    """Raised when an attested wheel cannot be installed or resolved."""


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def console_script_path(venv_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / (name + suffix)


def install_wheel(wheel_path: Path, venv_dir: Path, *, python: str = sys.executable) -> Path:
    created = subprocess.run([python, "-m", "venv", str(venv_dir)], capture_output=True, text=True, env=_clean_env())
    if created.returncode != 0:
        raise BundleExecutionError(f"venv creation failed: {created.stderr[-500:]}")
    _install_into_venv(venv_python(venv_dir), (wheel_path,))
    return venv_python(venv_dir)


def install_wheels_with_dependencies(wheel_path: Path, dependency_wheels: Sequence[Path], venv_dir: Path, *, python: str = sys.executable) -> Path:
    """Create the venv and install the primary wheel plus every managed dependency wheel.

    All wheels are installed with ``--no-deps``; the dependency set is the
    managed lock itself (each wheel already verified against its pinned sha256),
    so no wheel is resolved from a floating index.
    """
    created = subprocess.run([python, "-m", "venv", str(venv_dir)], capture_output=True, text=True, env=_clean_env())
    if created.returncode != 0:
        raise BundleExecutionError(f"venv creation failed: {created.stderr[-500:]}")
    _install_into_venv(venv_python(venv_dir), (wheel_path, *dependency_wheels))
    return venv_python(venv_dir)


def _install_into_venv(venv_python_path: Path, wheel_paths: Sequence[Path]) -> None:
    for wheel_path in wheel_paths:
        installed = subprocess.run(
            [str(venv_python_path), "-m", "pip", "install", "--no-deps", "--quiet", str(wheel_path)],
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
        if installed.returncode != 0:
            raise BundleExecutionError(f"wheel install failed: {installed.stderr[-500:]}")


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
