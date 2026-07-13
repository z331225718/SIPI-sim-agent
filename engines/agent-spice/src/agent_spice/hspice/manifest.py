from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass
class CompatReport:
    backend: str
    schema_version: int = 1
    deck: dict[str, str] = field(default_factory=dict)
    case: dict[str, str | None] = field(default_factory=dict)
    audit: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)
    actions: list[dict[str, str]] = field(default_factory=list)
    unsupported: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)

    def add_action(self, kind: str, source: str, target: str = "") -> None:
        self.actions.append({"kind": kind, "source": source, "target": target})

    def add_unsupported(self, line: str, reason: str) -> None:
        self.unsupported.append({"line": line, "reason": reason})

    def set_deck(self, deck_id: str, source: str, sha256: str) -> None:
        self.deck = {"id": deck_id, "source": source, "sha256": sha256}

    def set_case(self, name: str, kind: str, alter_label: str | None) -> None:
        self.case = {"name": name, "kind": kind, "alter_label": alter_label}

    def set_audit(
        self,
        directive_counts: dict[str, int],
        includes: list[str],
        libraries: list[tuple[str, str | None]],
        unsupported_directives: list[str],
    ) -> None:
        self.audit = {
            "directive_counts": directive_counts,
            "includes": includes,
            "libraries": [list(library) for library in libraries],
            "unsupported_directives": list(unsupported_directives),
        }

    def set_outputs(self, probes: list[str], measures: list[dict[str, str]]) -> None:
        self.outputs = {"probes": probes, "measures": measures}

    def finalize_summary(self) -> None:
        rewrites = sum(1 for action in self.actions if action["kind"].startswith("rewrite"))
        drops = sum(1 for action in self.actions if action["kind"].startswith("drop"))
        unsupported = len(self.unsupported)
        if unsupported:
            status = "blocked"
        elif self.actions:
            status = "auto_converted"
        else:
            status = "compatible"
        self.summary = {
            "status": status,
            "rewrites": rewrites,
            "drops": drops,
            "unsupported": unsupported,
        }

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "backend": self.backend,
                "deck": self.deck,
                "case": self.case,
                "audit": self.audit,
                "outputs": self.outputs,
                "actions": self.actions,
                "unsupported": self.unsupported,
                "summary": self.summary,
            },
            ensure_ascii=False,
            indent=2,
        )
