from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


VALID_BACKENDS = {"ngspice", "xyce"}


def _required_non_empty_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manifest field '{field}' must be a non-empty string")
    return value


def _optional_mapping(data: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = data.get(field, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"Manifest field '{field}' must be a mapping")
    return value


@dataclass(frozen=True)
class ProjectManifest:
    name: str
    hspice_deck: Path | None
    backend: str
    output_root: Path

    @classmethod
    def from_yaml(cls, path: Path) -> "ProjectManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest {path} must contain a mapping")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProjectManifest":
        name = _required_non_empty_string(data, "name")
        backend = str(data.get("backend", "ngspice")).lower()
        if backend not in VALID_BACKENDS:
            raise ValueError(f"Unsupported backend '{backend}'. Expected one of {sorted(VALID_BACKENDS)}")
        inputs = _optional_mapping(data, "inputs")
        outputs = _optional_mapping(data, "outputs")
        hspice_deck = inputs.get("hspice_deck")
        return cls(
            name=name,
            hspice_deck=Path(hspice_deck) if hspice_deck else None,
            backend=backend,
            output_root=Path(outputs.get("root", "runs")),
        )


def prepare_run_directory(root: Path, project_name: str, case_name: str) -> Path:
    run_dir = root / project_name / case_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
