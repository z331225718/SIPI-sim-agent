from __future__ import annotations

import csv
from pathlib import Path
import re


_MEASUREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z_][\w.$-]*)\s*=\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
    r"(?:\s+at=\s*(?P<at>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?))?\s*$",
    re.MULTILINE,
)


def parse_ngspice_measurements(stdout: str) -> list[dict[str, float | str]]:
    """Extract ngspice `.measure` values from its batch transcript."""
    measurements: list[dict[str, float | str]] = []
    for match in _MEASUREMENT.finditer(stdout):
        entry: dict[str, float | str] = {
            "name": match.group("name"),
            "value": float(match.group("value")),
        }
        if match.group("at") is not None:
            entry["at"] = float(match.group("at"))
        measurements.append(entry)
    return measurements


def write_ngspice_waveform_csv(stdout: str, path: Path) -> int:
    """Extract ngspice batch `.print` tables into a portable CSV waveform."""
    columns: list[str] | None = None
    rows: list[list[float]] = []
    for line in stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == "Index" and len(fields) >= 3:
            candidate = fields[1:]
            if columns is None:
                columns = candidate
            elif candidate != columns:
                columns = None
                rows.clear()
            continue
        if columns is None or len(fields) != len(columns) + 1 or not fields[0].isdigit():
            continue
        try:
            rows.append([float(value) for value in fields[1:]])
        except ValueError:
            continue
    if columns is None or not rows:
        return 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)
