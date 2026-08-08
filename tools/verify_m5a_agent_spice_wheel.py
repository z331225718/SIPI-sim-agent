"""Build and smoke-test the Windows x64 Agent-Spice compatibility wheel.

This is a source-tree gate, not a promotion or cross-platform certification.
It stages the Rust executable outside the worktree, so release artifacts never
become tracked package input by accident.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "engines" / "agent-spice"
CRATE_MANIFEST = ROOT / "native" / "crates" / "sipi-circuit" / "Cargo.toml"
RUST_TOOLCHAIN = "1.97.0-x86_64-pc-windows-msvc"
RID = "win-x64"
PLATFORM_TAG = "win_amd64"
ENGINE_NAME = "agent-spice-sim.exe"
WHEEL_ENGINE = f"agent_spice/lib/native/{RID}/{ENGINE_NAME}"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def rust_command() -> list[str]:
    cargo = shutil.which("cargo")
    if cargo:
        return [cargo]
    rustup = shutil.which("rustup")
    if not rustup:
        candidate = Path.home() / ".cargo" / "bin" / "rustup.exe"
        if candidate.is_file():
            rustup = str(candidate)
    if not rustup:
        raise RuntimeError("cargo or rustup is required to build the Agent-Spice wheel")
    return [rustup, "run", RUST_TOOLCHAIN, "cargo"]


def native_engine_path(stage: Path) -> Path:
    return stage / "src" / "agent_spice" / "lib" / "native" / RID / ENGINE_NAME


def main() -> int:
    if not sys.platform.startswith("win"):
        raise SystemExit("M5A wheel verification currently supports Windows x64 only")
    if not shutil.which("uv"):
        raise SystemExit("uv is required to build and install the isolated wheel")

    run(
        [*rust_command(), "build", "--locked", "--release", "--manifest-path", str(CRATE_MANIFEST)],
        cwd=ROOT,
    )
    built_engine = CRATE_MANIFEST.parent / "target" / "release" / ENGINE_NAME
    if not built_engine.is_file():
        raise SystemExit(f"Rust release engine was not produced: {built_engine}")

    with tempfile.TemporaryDirectory(prefix="sipi-m5a-wheel-") as temporary:
        temporary_root = Path(temporary)
        stage = temporary_root / "agent-spice"
        dist = temporary_root / "dist"
        venv = temporary_root / "venv"
        shutil.copytree(
            SOURCE_ROOT,
            stage,
            ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", ".pytest_cache"),
        )
        staged_engine = native_engine_path(stage)
        staged_engine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_engine, staged_engine)

        environment = os.environ.copy()
        environment["AGENT_SPICE_WHEEL_RID"] = RID
        environment["AGENT_SPICE_WHEEL_PLATFORM_TAG"] = PLATFORM_TAG
        # ``uv build`` may create an sdist first, which deliberately omits a
        # staged binary not present in source control. Build the wheel directly
        # from the disposable stage so the package-data contract is exercised.
        run(
            [
                "uv",
                "run",
                "--no-project",
                "--with",
                "wheel",
                "--with",
                "setuptools",
                "python",
                "setup.py",
                "bdist_wheel",
                "--dist-dir",
                str(dist),
            ],
            cwd=stage,
            env=environment,
        )
        wheels = sorted(dist.glob("agent_spice-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected exactly one Agent-Spice wheel, found: {wheels}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            members = set(archive.namelist())
            has_engine = WHEEL_ENGINE in members or any(
                name.endswith(f".data/purelib/{WHEEL_ENGINE}") for name in members
            )
            if not has_engine:
                native_members = [name for name in archive.namelist() if "/native/" in name]
                raise SystemExit(
                    f"wheel does not include staged native engine: {WHEEL_ENGINE}; "
                    f"native members: {native_members}"
                )

        run(["uv", "venv", "--seed", str(venv)], cwd=ROOT)
        python = venv / "Scripts" / "python.exe"
        run(["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)], cwd=ROOT)
        package_root = Path(
            run(
                [str(python), "-c", "import agent_spice, pathlib; print(pathlib.Path(agent_spice.__file__).parent)"],
                cwd=ROOT,
            ).strip()
        )
        packaged_engine = package_root / "lib" / "native" / RID / ENGINE_NAME
        if not packaged_engine.is_file():
            raise SystemExit(f"installed wheel does not contain native engine: {packaged_engine}")
        build_info = json.loads(run([str(packaged_engine), "build-info", "--json"], cwd=ROOT))
        if build_info.get("schema") != "agent-spice.build-info.v1":
            raise SystemExit(f"unexpected build-info schema: {build_info}")
        if build_info.get("profile") != "release" or not build_info.get("target"):
            raise SystemExit(f"incomplete release build-info: {build_info}")

        output = temporary_root / "native-smoke.json"
        fixture = stage / "native" / "AgentSpice.Engine" / "fixtures" / "rc.cir"
        run([str(packaged_engine), str(fixture), "--output-json", str(output)], cwd=ROOT)
        result = json.loads(output.read_text(encoding="utf-8"))
        if len(result.get("points", [])) != 8:
            raise SystemExit(f"unexpected native smoke result: {result}")
        print(
            json.dumps(
                {
                    "schema": "sipi.m5a.agent-spice-wheel-check.v1",
                    "rid": RID,
                    "wheel": wheel.name,
                    "buildInfo": build_info,
                    "smokePointCount": len(result["points"]),
                    "certification": "not_claimed",
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
