from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import skrf as rf


@dataclass(frozen=True)
class TouchstoneMetadata:
    ports: int
    frequency_points: int
    reference_impedance: list[float]
    reference_impedance_by_frequency: list[list[float]]


_PORT_SUFFIX_RE = re.compile(r"\.s(?P<ports>\d+)p$", re.IGNORECASE)


def _ports_from_suffix(path: Path) -> int | None:
    match = _PORT_SUFFIX_RE.search(path.name)
    if match is None:
        return None
    return int(match.group("ports"))


def _reference_impedance_from_option_line(line: str, ports: int) -> list[float] | None:
    tokens = line.strip().split()
    for index, token in enumerate(tokens):
        if token.upper() == "R" and index + 1 < len(tokens):
            try:
                value = float(tokens[index + 1])
            except ValueError:
                return None
            return [value] * ports
    return None


def _load_touchstone_metadata_fast(path: Path) -> TouchstoneMetadata | None:
    ports = _ports_from_suffix(path)
    if ports is None:
        return None

    reference_impedance: list[float] | None = None
    values_per_frequency = 1 + (2 * ports * ports)
    data_token_count = 0

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("!"):
                continue
            if stripped.startswith("["):
                return None
            if stripped.startswith("#"):
                reference_impedance = _reference_impedance_from_option_line(stripped, ports)
                continue

            data = stripped.split("!", 1)[0].strip()
            if not data:
                continue
            data_token_count += len(data.split())

    if reference_impedance is None or data_token_count == 0:
        return None
    frequency_points, remainder = divmod(data_token_count, values_per_frequency)
    if frequency_points == 0 or remainder != 0:
        return None
    return TouchstoneMetadata(
        ports=ports,
        frequency_points=frequency_points,
        reference_impedance=reference_impedance,
        reference_impedance_by_frequency=[reference_impedance] * frequency_points,
    )


def load_touchstone_metadata(path: Path) -> TouchstoneMetadata:
    try:
        metadata = _load_touchstone_metadata_fast(path)
    except OSError:
        metadata = None
    if metadata is not None:
        return metadata

    network = rf.Network(str(path))
    z0_by_frequency = [[float(value.real) for value in row] for row in network.z0]
    return TouchstoneMetadata(
        ports=network.nports,
        frequency_points=len(network.f),
        reference_impedance=z0_by_frequency[0],
        reference_impedance_by_frequency=z0_by_frequency,
    )
