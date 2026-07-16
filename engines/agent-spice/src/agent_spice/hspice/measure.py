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
        if directive in {".measure", ".meas"} and len(parts) >= 4:
            operation_token = parts[3]
            operation = operation_token.lower()
            target: str | None = None
            if operation.startswith("param="):
                operation = "param"
                target = operation_token.split("=", 1)[1]
            elif operation == "param":
                if len(parts) >= 6 and parts[4] == "=":
                    target = parts[5]
                elif len(parts) >= 5:
                    target = parts[4]
            elif len(parts) >= 5:
                target = parts[4]
            if target is None:
                continue
            measures.append(
                {
                    "analysis": parts[1].lower(),
                    "name": parts[2],
                    "operation": operation,
                    "target": target,
                    "raw": line,
                }
            )
    return OutputRequest(probes=probes, measures=measures)
