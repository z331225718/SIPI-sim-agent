from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from typing import Any

from sipi_contracts import EngineLockV1, parse_engine_lock


class EngineLockLoadError(ValueError):
    pass


class UnknownEngineInstance(LookupError):
    pass


def load_engine_lock(path: str | Path) -> EngineLockV1:
    try:
        contents = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise EngineLockLoadError("engine lock is missing") from error
    except UnicodeDecodeError as error:
        raise EngineLockLoadError("engine lock is not UTF-8") from error
    try:
        return parse_engine_lock(contents)
    except ValueError as error:
        raise EngineLockLoadError("engine lock is malformed") from error


class EngineRegistry:
    """Exact lookup over a parsed lock; it performs no discovery or bundle loading."""

    def __init__(self, lock: EngineLockV1) -> None:
        if not isinstance(lock, EngineLockV1):
            raise TypeError("lock must be an EngineLockV1")
        self._lock = parse_engine_lock(lock.to_wire())
        self._by_instance = {entry["instance_id"]: entry for entry in self._lock.wire["engines"]}

    def lookup(self, instance_id: str) -> Mapping[str, Any]:
        try:
            return self._by_instance[instance_id]
        except KeyError as error:
            raise UnknownEngineInstance(instance_id) from error

    def default_for(self, operation: str) -> Mapping[str, Any] | None:
        return self._lock.wire["operation_defaults"].get(operation)
