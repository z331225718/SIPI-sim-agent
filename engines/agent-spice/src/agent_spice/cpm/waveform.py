from __future__ import annotations

from agent_spice.cpm.io import CpmLiteModel


def render_pwl_sources(model: CpmLiteModel) -> str:
    lines: list[str] = []
    for bump in model.bumps:
        points = " ".join(f"{time} {current}" for time, current in bump.waveform)
        lines.append(f"I_{bump.name} {bump.node} {bump.return_node} PWL({points})")
    return "\n".join(lines) + "\n"
