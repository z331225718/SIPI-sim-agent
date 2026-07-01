from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.backend.base import ProcessBackend


@dataclass(frozen=True)
class XyceBackend(ProcessBackend):
    executable: str = "Xyce"
    xdm_executable: str = "xdm_bdl"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, str(deck_path)]

    def xdm_command_for(self, hspice_path: Path, output_path: Path) -> list[str]:
        return [
            self.xdm_executable,
            "-s",
            "hspice",
            "-d",
            "xyce",
            "-o",
            str(output_path),
            str(hspice_path),
        ]
