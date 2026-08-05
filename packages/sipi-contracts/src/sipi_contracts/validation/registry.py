from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ..errors import ContractViolation
from ..json_types import freeze_json


def _find_schema_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schemas"
        if candidate.is_dir() and (parent / ".git").exists():
            return candidate
    bundled = Path(__file__).resolve().parents[1] / "_schemas"
    if bundled.is_dir():
        return bundled
    raise RuntimeError("cannot locate repository schema directory")


SCHEMA_ROOT = _find_schema_root()


@lru_cache
def _schemas() -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(SCHEMA_ROOT).as_posix(): json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_ROOT.rglob("*.json")
    }


@lru_cache
def _registry() -> Registry:
    resources = []
    for path in SCHEMA_ROOT.rglob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        resources.append((path.as_uri(), resource))
        resources.append((path.relative_to(SCHEMA_ROOT).as_posix(), resource))
        if "$id" in schema:
            resources.append((schema["$id"], resource))
    return Registry().with_resources(resources)


def schema_id_for(schema_name: str) -> str:
    return _schemas()[schema_name].get("$id", schema_name.removesuffix(".schema.json"))


def validate_wire(schema_name: str, value: Any) -> None:
    schema = _schemas()[schema_name]
    schema_id = schema_id_for(schema_name)
    freeze_json(value, schema_id)
    try:
        Draft202012Validator(schema, registry=_registry()).validate(value)
    except ValidationError as error:
        pointer = "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)
        raise ContractViolation(schema_id, "schema", pointer if pointer != "/" else "", error.message) from error


def validate_definition(schema_name: str, definition: str, value: Any, schema_id: str) -> None:
    freeze_json(value, schema_id)
    reference = f"{(SCHEMA_ROOT / schema_name).as_uri()}#/$defs/{definition}"
    try:
        Draft202012Validator({"$ref": reference}, registry=_registry()).validate(value)
    except ValidationError as error:
        pointer = "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)
        raise ContractViolation(schema_id, "schema", pointer if pointer != "/" else "", error.message) from error
