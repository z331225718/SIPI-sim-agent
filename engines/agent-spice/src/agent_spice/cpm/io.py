from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class CpmBump:
    name: str
    node: str
    return_node: str
    waveform: list[tuple[float, float]]


@dataclass(frozen=True)
class CpmLiteModel:
    model: str
    bumps: list[CpmBump]


def load_cpm_lite(path: Path) -> CpmLiteModel:
    data = json.loads(path.read_text(encoding="utf-8"))
    bumps = [
        CpmBump(
            name=item["name"],
            node=item["node"],
            return_node=item.get("return_node", "0"),
            waveform=[(float(time), float(current)) for time, current in item["waveform"]],
        )
        for item in data["bumps"]
    ]
    return CpmLiteModel(model=data["model"], bumps=bumps)
