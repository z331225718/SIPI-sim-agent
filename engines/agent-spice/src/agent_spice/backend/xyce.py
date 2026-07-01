from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from agent_spice.backend.base import BackendResult, ProcessBackend


@dataclass(frozen=True)
class XyceXdmRunResult:
    xdm: BackendResult
    xyce: BackendResult | None

    @property
    def returncode(self) -> int:
        if not self.xdm.ok:
            return self.xdm.returncode
        if self.xyce is None:
            return 1
        return self.xyce.returncode

    @property
    def ok(self) -> bool:
        return self.xdm.ok and self.xyce is not None and self.xyce.ok


@dataclass(frozen=True)
class XyceBackend(ProcessBackend):
    executable: str = "Xyce"
    xdm_executable: str = "xdm_bdl"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, str(deck_path)]

    def xdm_command_for(self, hspice_path: Path, output_dir: Path) -> list[str]:
        return [
            self.xdm_executable,
            "-s",
            "hspice",
            "-d",
            str(output_dir),
            "-o",
            "xyce",
            str(hspice_path),
        ]

    def run_hspice_via_xdm(self, hspice_path: Path, xyce_path: Path, cwd: Path) -> XyceXdmRunResult:
        cwd = cwd.resolve()
        hspice_path = hspice_path.resolve()
        xyce_path = xyce_path.resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        xdm_dir = cwd / "xdm-out"
        xdm_dir.mkdir(parents=True, exist_ok=True)
        generated_path = xdm_dir / hspice_path.name
        for stale_path in (generated_path, xyce_path, cwd / "xyce.stdout.log", cwd / "xyce.stderr.log"):
            if stale_path.exists():
                stale_path.unlink()

        xdm_completed = subprocess.run(
            self.xdm_command_for(hspice_path, xdm_dir),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        xdm_result = BackendResult(
            returncode=xdm_completed.returncode,
            stdout=xdm_completed.stdout,
            stderr=xdm_completed.stderr,
        )
        (cwd / "xdm.stdout.log").write_text(xdm_result.stdout, encoding="utf-8")
        (cwd / "xdm.stderr.log").write_text(xdm_result.stderr, encoding="utf-8")
        if not xdm_result.ok:
            return XyceXdmRunResult(xdm=xdm_result, xyce=None)

        if not generated_path.exists():
            missing_output = BackendResult(
                returncode=1,
                stdout=xdm_result.stdout,
                stderr=xdm_result.stderr + f"\nXDM did not create expected output: {generated_path}\n",
            )
            (cwd / "xdm.stderr.log").write_text(missing_output.stderr, encoding="utf-8")
            return XyceXdmRunResult(xdm=missing_output, xyce=None)

        shutil.copyfile(generated_path, xyce_path)
        xyce_completed = subprocess.run(
            self.command_for(xyce_path),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        xyce_result = BackendResult(
            returncode=xyce_completed.returncode,
            stdout=xyce_completed.stdout,
            stderr=xyce_completed.stderr,
        )
        (cwd / "xyce.stdout.log").write_text(xyce_result.stdout, encoding="utf-8")
        (cwd / "xyce.stderr.log").write_text(xyce_result.stderr, encoding="utf-8")
        return XyceXdmRunResult(xdm=xdm_result, xyce=xyce_result)
