"""M2-08 clean-install smoke.

Builds every workspace package into wheels, installs them into a fresh
isolated venv (no sibling repo imports), and verifies:
  - the packaged ``_schemas`` bundle is complete (engine-lock parses);
  - contracts/runtime/artifacts/adapters/cli all import;
  - ``sipi capabilities`` and ``sipi doctor`` behave fail-closed without a
    source checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "python.exe" if os.name == "nt" else "python"


def run(argv: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / PYTHON


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sipi-clean-install-") as directory:
        tmp = Path(directory)
        wheels_dir = tmp / "wheels"
        wheels_dir.mkdir()
        print("building workspace wheels...")
        build = run(["uv", "build", "--all-packages", "--wheel", "-o", str(wheels_dir)], cwd=ROOT)
        if build.returncode != 0:
            print(build.stdout + build.stderr)
            print("FAIL: wheel build failed")
            return 1
        wheels = sorted(wheels_dir.glob("*.whl"))
        if len(wheels) < 5:
            print(f"FAIL: expected at least 5 wheels, found {len(wheels)}")
            return 1

        venv_dir = tmp / "venv"
        print("creating isolated venv...")
        created = run([sys.executable, "-m", "venv", str(venv_dir)], cwd=tmp)
        if created.returncode != 0:
            print(created.stdout + created.stderr)
            print("FAIL: venv creation failed")
            return 1
        python = venv_python(venv_dir)

        print("installing wheels into isolated venv...")
        installed = run([str(python), "-m", "pip", "install", "--quiet", *map(str, wheels)], cwd=tmp)
        if installed.returncode != 0:
            print(installed.stdout + installed.stderr)
            print("FAIL: wheel installation failed")
            return 1

        checks: list[tuple[str, list[str]]] = [
            (
                "all packages import",
                [
                    str(python),
                    "-c",
                    "import sipi_contracts, sipi_runtime, sipi_artifacts, sipi_adapters, sipi_cli",
                ],
            ),
            (
                "packaged engine-lock schema parses",
                [
                    str(python),
                    "-c",
                    "from sipi_contracts import parse_engine_lock; parse_engine_lock('{\"schema\":\"sipi.engine-lock.v1\",\"engines\":[],\"operation_defaults\":{},\"extensions\":{}}')",
                ],
            ),
            (
                "adapter SPI imports",
                [
                    str(python),
                    "-c",
                    "from sipi_adapters import execute_backend, AgentSpiceHspiceAdapter, PyBertNativeAdapter, AgentComRunAdapter",
                ],
            ),
            (
                "sipi capabilities fails open on absent catalog",
                [str(python), "-m", "sipi_cli", "capabilities", "--format", "json"],
            ),
            (
                "sipi doctor uses packaged schema bundle",
                [str(python), "-m", "sipi_cli", "doctor", "--format", "json"],
            ),
        ]
        failures: list[str] = []
        for name, argv in checks:
            result = run(argv, cwd=tmp, check=False)
            ok = result.returncode in (0, 1) if name == "sipi doctor uses packaged schema bundle" else result.returncode == 0
            detail = ""
            if ok and name == "sipi capabilities fails open on absent catalog":
                payload = json.loads(result.stdout)
                ok = payload["advertised"] == [] and payload["source"]["status"] == "absent"
            if ok and name == "sipi doctor uses packaged schema bundle":
                payload = json.loads(result.stdout)
                schemas = next(item for item in payload["checks"] if item["id"] == "schemas")
                ok = schemas["status"] == "ok" and schemas["details"]["active_schema_root"] == "packaged" and schemas["details"]["bundled_missing"] == []
                detail = f" schemas={schemas['status']} root={schemas['details']['active_schema_root']}"
            status = "PASS" if ok else "FAIL"
            print(f"{status}  {name}{detail}")
            if not ok:
                failures.append(name)
                print(result.stdout[-2000:])
                print(result.stderr[-2000:])
        print(f"\nclean install smoke: {len(checks) - len(failures)}/{len(checks)} passed")
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
