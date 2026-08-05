from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ContractViolation(ValueError):
    """A stable, machine-readable contract validation failure."""

    schema_id: str
    code: str
    json_pointer: str
    message: str

    def __str__(self) -> str:
        location = self.json_pointer or "/"
        return f"{self.schema_id}:{self.code} at {location}: {self.message}"
