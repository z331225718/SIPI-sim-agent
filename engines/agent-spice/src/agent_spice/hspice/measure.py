from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputRequest:
    probes: list[str]
    measures: list[dict[str, str]]


def normalize_outputs(text: str) -> OutputRequest:
    probes: list[str] = []
    measures: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        directive = parts[0].lower()
        if directive in {".probe", ".print"} and len(parts) >= 3:
            probes.extend(parts[2:])
        if directive in {".measure", ".meas"} and len(parts) >= 5:
            measures.append(
                {
                    "analysis": parts[1].lower(),
                    "name": parts[2],
                    "operation": parts[3].lower(),
                    "target": parts[4],
                    "raw": line,
                }
            )
    return OutputRequest(probes=probes, measures=measures)
