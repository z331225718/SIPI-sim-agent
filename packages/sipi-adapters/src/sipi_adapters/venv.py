"""Isolated-venv execution of attested wheel bundles (M2-02b/M2-09 follow-up).

An attested wheel is installed with ``--no-deps`` into a per-run venv; third
party dependencies are supplied by the managed dependency lock (``bundle_manifest``
entries with ``role == "dependency"``), each pinned by sha256, so resolution never
hits a floating index.  The engine.lock extension ``sipi.m2.console-script`` names
the console script that the adapter invokes.
"""

from __future__ import annotations

import os
import re
import shutil
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


def resolve_interpreter(python_abi: str | None = None) -> str:
    """Resolve a Python executable matching the requested ABI.

    Falls back to ``sys.executable`` when no ABI is requested or no candidate
    is found.  Candidate sources: ``py`` launcher (Windows) and ``uv``-managed
    Python installations.
    """
    if not python_abi:
        return sys.executable
    requested = python_abi
    candidates: list[str] = []
    if os.name == "nt":
        try:
            py_exe = shutil.which("py")
        except Exception:  # noqa: BLE001
            py_exe = None
        if py_exe:
            try:
                listing = subprocess.run([py_exe, "-0p"], capture_output=True, text=True, env=_clean_env(), timeout=10).stdout
            except (OSError, subprocess.TimeoutExpired):  # pragma: no cover
                listing = ""
            for line in listing.splitlines():
                match = re.search(r"-V:([^ ]+)\s+(\S+)", line)
                if match:
                    tag, path = match.groups()
                    version = re.search(r"(3\.\d+)", tag)
                    if version and version.group(1).startswith(requested[:3] if len(requested) >= 3 else requested):
                        candidates.append(path)
    uv_candidates: list[Path] = []
    for base in (Path.home() / ".local" / "share" / "uv" / "python", Path.home() / "AppData" / "Roaming" / "uv" / "python"):
        if base.is_dir():
            uv_candidates.append(base)
    abi_digits = re.sub(r"[^0-9]", "", requested)  # cp312 -> 312
    version_spec = f"{abi_digits[0]}.{abi_digits[1:]}" if abi_digits else ""
    for base in uv_candidates:
        for candidate in sorted(base.iterdir()):
            exe = candidate / ("python.exe" if os.name == "nt" else "bin" / "python3")
            if exe.is_file() and (version_spec in candidate.name or requested[:3] in candidate.name):
                candidates.append(str(exe))
    if candidates:
        # Prefer an exact-version directory (cpython-3.12.13) over a loose
        # alias directory (cpython-3.12); both sort deterministically.
        return min(candidates, key=lambda path: (len(Path(path).name), path))
    return sys.executable


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


def install_pip_dependencies(venv_dir: Path, requirements: Sequence[str], *, python: str = sys.executable) -> None:
    """Install the engine's pinned third-party dependencies into the venv.

    ``requirements`` are exact pins (``name==version``) declared by the managed
    dependency lock extension ``sipi.m2.pip-dependencies``; pip resolves them
    from its configured index.  This is a deliberate, auditable dependency set
    -- the engine wheel itself is always installed with ``--no-deps`` so its
    metadata never drags in unmanaged floating versions.
    """
    venv_python_path = venv_python(venv_dir)
    installed = subprocess.run(
        [str(venv_python_path), "-m", "pip", "install", "--quiet", *requirements],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    if installed.returncode != 0:
        raise BundleExecutionError(f"pip dependency install failed: {installed.stderr[-500:]}")


def required_pip_dependencies(engine_entry: Mapping[str, Any]) -> tuple[str, ...]:
    dependencies = engine_entry.get("extensions", {}).get("sipi.m2.pip-dependencies")
    if dependencies is None:
        return ()
    if not isinstance(dependencies, (list, tuple)) or not all(isinstance(item, str) and item for item in dependencies):
        raise BundleExecutionError("sipi.m2.pip-dependencies must be a list of requirement strings")
    return tuple(dependencies)


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
