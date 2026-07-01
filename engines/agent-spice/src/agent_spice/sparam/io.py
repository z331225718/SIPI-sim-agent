from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import skrf as rf


@dataclass(frozen=True)
class TouchstoneMetadata:
    ports: int
    frequency_points: int
    reference_impedance: list[float]
    reference_impedance_by_frequency: list[list[float]]


def load_touchstone_metadata(path: Path) -> TouchstoneMetadata:
    network = rf.Network(str(path))
    z0_by_frequency = [[float(value.real) for value in row] for row in network.z0]
    return TouchstoneMetadata(
        ports=network.nports,
        frequency_points=len(network.f),
        reference_impedance=z0_by_frequency[0],
        reference_impedance_by_frequency=z0_by_frequency,
    )
