from __future__ import annotations

import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from .errors import ContractViolation

JsonValue = None | bool | int | float | str | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


def reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def load_json(text: str, schema_id: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text, parse_constant=reject_non_finite_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ContractViolation(schema_id, "invalid_json", "", str(error)) from error
    if not isinstance(value, dict):
        raise ContractViolation(schema_id, "type", "", "contract root must be an object")
    return value


def freeze_json(value: Any, schema_id: str, pointer: str = "") -> JsonValue:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractViolation(schema_id, "non_finite", pointer, "NaN and infinity are forbidden")
        return value
    if isinstance(value, Mapping):
        frozen = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractViolation(schema_id, "key_type", pointer, "object keys must be strings")
            child_pointer = f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            frozen[key] = freeze_json(child, schema_id, child_pointer)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(child, schema_id, f"{pointer}/{index}") for index, child in enumerate(value))
    raise ContractViolation(schema_id, "json_type", pointer, f"unsupported JSON value: {type(value).__name__}")


def thaw_json(value: JsonValue) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value
