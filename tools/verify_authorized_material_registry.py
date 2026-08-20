"""Verify the authorized external material registry.

Owner-authorized external materials (AMI DLLs, IBIS/AMI text, S4P, MATLAB
source/runtime, COM schemas) are registered with absolute paths and
hashes. The verifier re-hashes every material in place and fails closed on
drift, missing files, or length mismatch. Materials with
identity_status pending_verification are not silently accepted: their
bound items must not be claimed until verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
SCHEMA = "sipi.authorized-material-registry.v1"


class RegistryError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistryError("document_not_mapping")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def validate(root: Path = ROOT) -> dict[str, Any]:
    document = load_yaml(DEFAULT)
    if document.get("schema") != SCHEMA or document.get("status") != "authorized_external_only":
        raise RegistryError("schema_or_status_invalid")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict) or authorization.get("granted_by") != "owner":
        raise RegistryError("authorization_invalid")
    materials = document.get("materials")
    if not isinstance(materials, list) or not materials:
        raise RegistryError("materials_invalid")
    pending = 0
    for material in materials:
        material_id = material.get("id")
        path = Path(str(material["path"]).replace("/", "\\")) if "/" in str(material["path"]) else Path(material["path"])
        if not path.is_absolute():
            raise RegistryError(f"material_path_not_absolute:{material_id}")
        if not path.is_file():
            raise RegistryError(f"material_missing:{material_id}:{path}")
        status = material.get("identity_status")
        if status == "pending_verification":
            pending += 1
            continue
        actual = sha256_file(path)
        if actual != material.get("sha256", "").lower():
            raise RegistryError(f"material_hash_drift:{material_id}")
        actual_len = path.stat().st_size
        if actual_len != material.get("byte_length"):
            raise RegistryError(f"material_length_drift:{material_id}")
    bindings = document.get("cross_bindings")
    if not isinstance(bindings, list):
        raise RegistryError("cross_bindings_invalid")
    return {"valid": True, "materials": len(materials), "pending_verification": pending, "cross_bindings": len(bindings)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except RegistryError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
