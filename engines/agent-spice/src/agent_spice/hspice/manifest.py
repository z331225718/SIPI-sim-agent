from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass
class CompatReport:
    backend: str
    actions: list[dict[str, str]] = field(default_factory=list)
    unsupported: list[dict[str, str]] = field(default_factory=list)

    def add_action(self, kind: str, source: str, target: str = "") -> None:
        self.actions.append({"kind": kind, "source": source, "target": target})

    def add_unsupported(self, line: str, reason: str) -> None:
        self.unsupported.append({"line": line, "reason": reason})

    def to_json(self) -> str:
        return json.dumps(
            {"backend": self.backend, "actions": self.actions, "unsupported": self.unsupported},
            ensure_ascii=False,
            indent=2,
        )
