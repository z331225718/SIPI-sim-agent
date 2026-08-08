from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from collections.abc import Mapping


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

    def run(
        self,
        deck_path: Path,
        cwd: Path | None = None,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> BackendResult:
        command = self.command_for(deck_path.resolve())
        process_environment = None
        if environment is not None:
            process_environment = os.environ.copy()
            process_environment.update(environment)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=process_environment,
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
