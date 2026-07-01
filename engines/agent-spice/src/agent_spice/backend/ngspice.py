from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.backend.base import ProcessBackend


@dataclass(frozen=True)
class NgspiceBackend(ProcessBackend):
    executable: str = "ngspice"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, "-b", str(deck_path)]
