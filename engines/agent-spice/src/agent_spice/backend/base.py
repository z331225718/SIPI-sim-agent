from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class BackendResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ProcessBackend:
    executable: str

    def command_for(self, deck_path: Path) -> list[str]:
        raise NotImplementedError

    def run(self, deck_path: Path, cwd: Path | None = None) -> BackendResult:
        command = self.command_for(deck_path.resolve())
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return BackendResult(
                returncode=127,
                stdout="",
                stderr=f"Failed to start backend command {command[0]!r}: {exc}\n",
            )
        return BackendResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
